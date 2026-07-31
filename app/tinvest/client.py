"""Minimal T-Invest REST client.

Only one method is needed so far: `UsersService/GetInfo`, the cheapest call the API
offers — it needs neither a brokerage account nor trading rights, so a read-only token
answers it. That makes it the right probe for "is this token alive".

https://developer.tbank.ru/invest/api/users-service-get-info
"""

from collections.abc import Awaitable, Callable

import httpx
import structlog

from app.core.exceptions import InvalidTokenError, UpstreamUnavailableError

log = structlog.get_logger(__name__)

GET_INFO_PATH = "/tinkoff.public.invest.api.contract.v1.UsersService/GetInfo"

# `validate_token` with the client and base url already bound — what the service gets.
TokenValidatorFn = Callable[[str], Awaitable[None]]


async def validate_token(http: httpx.AsyncClient, base_url: str, token: str) -> None:
    """Return quietly when the token works; raise otherwise.

    No retries: the user is waiting on this call, and retrying is the bot's job.

    The token never reaches the logs — it is a live credential, and the whole codebase
    keeps it out of tracebacks (`repr=False` on the schemas) and out of log lines.
    """
    url = f"{base_url.rstrip('/')}{GET_INFO_PATH}"
    try:
        response = await http.post(url, json={}, headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        # Timeouts, DNS and connection failures all land here.
        log.warning("tinvest.getinfo.failed", error=type(exc).__name__)
        raise UpstreamUnavailableError("T-Invest API is unreachable") from exc

    log.info("tinvest.getinfo", status=response.status_code)

    if response.status_code == httpx.codes.OK:
        return
    if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
        raise InvalidTokenError("T-Invest rejected the token")
    # 429, any 5xx, and anything unexpected: we failed to check, which is not the same
    # as the token being bad — so the caller is told to try again, not to fix the token.
    raise UpstreamUnavailableError(
        f"T-Invest API answered with an unexpected status {response.status_code}"
    )
