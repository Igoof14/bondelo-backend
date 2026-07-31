"""The token check: what the API does with each verdict, and what `validate_token` decides.

`conftest.client` stubs the check out entirely. Here it is present — either as a stand-in
that returns the verdict a test needs, or, for `validate_token` itself, as the real thing
with the SDK's channel replaced.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from http import HTTPStatus
from typing import Any

import grpc
import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession
from t_tech.invest.exceptions import AioRequestError

from app.api.deps import get_token_validator
from app.core.exceptions import AppError, InvalidTokenError, UpstreamUnavailableError
from app.db.session import get_session
from app.main import create_app
from app.tinvest import client as tinvest_client
from app.tinvest.client import validate_token

TELEGRAM_ID = 1825344258
TOKEN = "t.real-looking-token"

# The verdict the broker check gives, in place of a network call: None means the token works.
Verdict = AppError | None
ApiFactory = Callable[..., AbstractAsyncContextManager[AsyncClient]]


@pytest.fixture
def checked_tokens() -> list[str]:
    """Tokens the app put through the broker check, for asserting on the outgoing call."""
    return []


@pytest.fixture
def api(session: AsyncSession, checked_tokens: list[str]) -> ApiFactory:
    """Factory: an API client whose token check answers with `verdicts`, one per call."""

    @asynccontextmanager
    async def build(*verdicts: Verdict) -> AsyncIterator[AsyncClient]:
        remaining = iter(verdicts)

        async def check(token: str) -> None:
            checked_tokens.append(token)
            if verdict := next(remaining):
                raise verdict

        app = create_app()
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[get_token_validator] = lambda: check
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client

    return build


async def _put_token(client: AsyncClient, token: str = TOKEN) -> Response:
    return await client.put(f"/api/v1/users/{TELEGRAM_ID}/token", json={"token": token})


async def _register(client: AsyncClient) -> None:
    await client.post("/api/v1/users/register", json={"telegram_id": TELEGRAM_ID})


async def _stored_token(client: AsyncClient) -> str | None:
    return (await client.get(f"/api/v1/users/{TELEGRAM_ID}/token")).json()["token"]


async def test_valid_token_is_stored(api: ApiFactory, checked_tokens: list[str]) -> None:
    async with api(None) as client:
        await _register(client)
        response = await _put_token(client)

        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"has_token": True}
        assert await _stored_token(client) == TOKEN

    # The token reached the broker check unchanged before anything was written.
    assert checked_tokens == [TOKEN]


async def test_rejected_token_is_not_stored(api: ApiFactory) -> None:
    async with api(InvalidTokenError("rejected")) as client:
        await _register(client)
        response = await _put_token(client)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json()["code"] == "invalid_token"
        assert await _stored_token(client) is None


async def test_an_unreachable_broker_does_not_store_the_token(api: ApiFactory) -> None:
    """Failing to check is not a verdict on the token — nothing is written either way."""
    async with api(UpstreamUnavailableError("unreachable")) as client:
        await _register(client)
        response = await _put_token(client)

        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json()["code"] == "upstream_unavailable"
        assert await _stored_token(client) is None


async def test_a_broken_token_does_not_replace_a_working_one(api: ApiFactory) -> None:
    """The check runs before the write, so a rejected token leaves the old one alone."""
    async with api(None, InvalidTokenError("rejected")) as client:
        await _register(client)
        assert (await _put_token(client)).status_code == HTTPStatus.OK

        replaced = await _put_token(client, "t.broken")

        assert replaced.status_code == HTTPStatus.BAD_REQUEST
        assert await _stored_token(client) == TOKEN


# A token pasted into a chat arrives with whatever the chat put around it. Anything that
# cannot be sent as a bearer credential has to be refused here, at the edge: it used to
# reach the transport and die there with an encoding error, which the user saw as a 500.
@pytest.mark.parametrize(
    "token",
    [
        pytest.param("т.кириллица", id="cyrillic-lookalikes"),
        pytest.param("t.abc\ndef", id="newline"),
        pytest.param("t.abc​def", id="zero-width-space"),
        pytest.param("   ", id="whitespace-only"),
    ],
)
async def test_a_token_that_is_not_ascii_is_refused(
    api: ApiFactory, checked_tokens: list[str], token: str
) -> None:
    async with api(None) as client:
        await _register(client)
        response = await _put_token(client, token)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json()["code"] == "validation_error"
        assert await _stored_token(client) is None

    # Refused before the broker was ever asked.
    assert checked_tokens == []


async def test_surrounding_whitespace_is_trimmed(
    api: ApiFactory, checked_tokens: list[str]
) -> None:
    async with api(None) as client:
        await _register(client)
        assert (await _put_token(client, f"  {TOKEN}\n")).status_code == HTTPStatus.OK

        assert await _stored_token(client) == TOKEN

    assert checked_tokens == [TOKEN]


@asynccontextmanager
async def _no_channel(**_kwargs: Any) -> AsyncIterator[None]:
    """A channel that connects to nothing — the fake services ignore it anyway."""
    yield None


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch) -> Callable[[BaseException | None], None]:
    """Replace the SDK's transport, so `validate_token` itself runs for real, offline."""

    def set_outcome(outcome: BaseException | None) -> None:
        class FakeServices:
            def __init__(self, _channel: object, token: str) -> None:
                self.users = self
                self.token = token

            async def get_info(self) -> object:
                if outcome:
                    raise outcome
                return object()

        monkeypatch.setattr(tinvest_client, "create_channel", _no_channel, raising=True)
        monkeypatch.setattr(tinvest_client, "AsyncServices", FakeServices, raising=True)

    return set_outcome


def _rpc_error(code: grpc.StatusCode) -> AioRequestError:
    """What the SDK raises: it turns every gRPC error into this before we see it."""
    return AioRequestError(code, "details", None)


@pytest.mark.parametrize(
    "code",
    [grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED],
)
async def test_validate_token_reads_a_refusal_as_a_bad_token(
    broker: Callable[[BaseException | None], None], code: grpc.StatusCode
) -> None:
    broker(_rpc_error(code))

    with pytest.raises(InvalidTokenError):
        await validate_token("localhost:1", 5.0, TOKEN)


@pytest.mark.parametrize(
    "code",
    [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.RESOURCE_EXHAUSTED, grpc.StatusCode.INTERNAL],
)
async def test_validate_token_reads_anything_else_as_a_failed_check(
    broker: Callable[[BaseException | None], None], code: grpc.StatusCode
) -> None:
    """We could not check — which is not the same as the token being bad."""
    broker(_rpc_error(code))

    with pytest.raises(UpstreamUnavailableError):
        await validate_token("localhost:1", 5.0, TOKEN)


async def test_validate_token_refuses_a_non_ascii_token_without_calling_the_broker(
    broker: Callable[[BaseException | None], None],
) -> None:
    """The backstop behind schema validation: gRPC metadata cannot carry these at all."""
    broker(AssertionError("the broker must not be reached"))

    with pytest.raises(InvalidTokenError):
        await validate_token("localhost:1", 5.0, "т.кириллица")


async def test_validate_token_gives_up_when_the_broker_is_slow(
    broker: Callable[[BaseException | None], None],
) -> None:
    broker(TimeoutError())

    with pytest.raises(UpstreamUnavailableError):
        await validate_token("localhost:1", 0.01, TOKEN)
