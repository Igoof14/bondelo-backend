"""The real T-Invest check, with the network replaced by an httpx MockTransport.

`conftest.client` stubs the check out entirely; here the genuine `validate_token` runs,
only against a transport that answers in place of the broker.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import partial
from http import HTTPStatus

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_token_validator
from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app
from app.tinvest.client import GET_INFO_PATH, validate_token

TELEGRAM_ID = 1825344258
TOKEN = "t.real-looking-token"

# What the fake broker answers with, given the request the app sent.
Handler = Callable[[Request], Response]
ApiFactory = Callable[[Handler], AbstractAsyncContextManager[AsyncClient]]


def _answers(*statuses: HTTPStatus) -> Handler:
    """A broker that returns each status in turn, one per call."""
    remaining = iter(statuses)
    return lambda _request: Response(next(remaining))


@pytest.fixture
def broker_calls() -> list[Request]:
    """Requests the app made to the broker, for asserting on the outgoing call."""
    return []


@pytest.fixture
def api(session: AsyncSession, broker_calls: list[Request]) -> ApiFactory:
    """Factory: an API client whose token check talks to `handler` instead of T-Invest."""

    @asynccontextmanager
    async def build(handler: Handler) -> AsyncIterator[AsyncClient]:
        def record(request: Request) -> Response:
            broker_calls.append(request)
            return handler(request)

        app = create_app()
        app.dependency_overrides[get_session] = lambda: session
        async with AsyncClient(transport=MockTransport(record)) as broker:
            app.dependency_overrides[get_token_validator] = lambda: partial(
                validate_token, broker, get_settings().tinvest_api_url
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield client

    return build


async def _put_token(client: AsyncClient, token: str = TOKEN) -> httpx.Response:
    return await client.put(f"/api/v1/users/{TELEGRAM_ID}/token", json={"token": token})


async def _register(client: AsyncClient) -> None:
    await client.post("/api/v1/users/register", json={"telegram_id": TELEGRAM_ID})


async def _stored_token(client: AsyncClient) -> str | None:
    return (await client.get(f"/api/v1/users/{TELEGRAM_ID}/token")).json()["token"]


async def test_valid_token_is_stored(api: ApiFactory, broker_calls: list[Request]) -> None:
    async with api(_answers(HTTPStatus.OK)) as client:
        await _register(client)
        response = await _put_token(client)

        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"has_token": True}
        assert await _stored_token(client) == TOKEN

    # The outgoing call is the documented one, carrying the token as a bearer credential.
    (call,) = broker_calls
    assert call.method == "POST"
    assert call.url.path.endswith(GET_INFO_PATH)
    assert call.headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize("status", [HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN])
async def test_rejected_token_is_not_stored(api: ApiFactory, status: HTTPStatus) -> None:
    async with api(_answers(status)) as client:
        await _register(client)
        response = await _put_token(client)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json()["code"] == "invalid_token"
        assert await _stored_token(client) is None


@pytest.mark.parametrize(
    "status", [HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.BAD_REQUEST]
)
async def test_an_unusable_answer_does_not_store_the_token(
    api: ApiFactory, status: HTTPStatus
) -> None:
    """Anything but 200/401/403 means we failed to check — not a verdict on the token."""
    async with api(_answers(status)) as client:
        await _register(client)
        response = await _put_token(client)

        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json()["code"] == "upstream_unavailable"
        assert await _stored_token(client) is None


async def test_broker_timeout_does_not_store_the_token(api: ApiFactory) -> None:
    def time_out(request: Request) -> Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    async with api(time_out) as client:
        await _register(client)
        response = await _put_token(client)

        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json()["code"] == "upstream_unavailable"
        assert await _stored_token(client) is None


async def test_a_broken_token_does_not_replace_a_working_one(api: ApiFactory) -> None:
    """The check runs before the write, so a rejected token leaves the old one alone."""
    async with api(_answers(HTTPStatus.OK, HTTPStatus.UNAUTHORIZED)) as client:
        await _register(client)
        assert (await _put_token(client)).status_code == HTTPStatus.OK

        replaced = await _put_token(client, "t.broken")

        assert replaced.status_code == HTTPStatus.BAD_REQUEST
        assert await _stored_token(client) == TOKEN
