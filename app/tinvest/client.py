"""Minimal T-Invest client, built on the official SDK (`t-tech-investments`).

Only one call is needed so far: `UsersService/GetInfo`, the cheapest the API offers — it
needs neither a brokerage account nor trading rights, so a read-only token answers it.
That makes it the right probe for "is this token alive".

https://developer.tbank.ru/invest/api/users-service-get-info

The channel is built by hand from `create_channel` + `AsyncServices` rather than through
`AsyncClient`: entering that context manager calls `sentry_sdk.init()` on every use, which
would take over the process-wide Sentry client and ship our tracebacks to T-Bank's error
hub. Everything else about the call is what `AsyncClient` would have done.

TLS: T-Invest is served under the Russian Trusted Root CA, which is in no default trust
store. The SDK carries that root and uses it only when `SSL_TBANK_VERIFY=true` is set in
the environment — without it every connection fails at the handshake.
"""

import asyncio
from collections.abc import Awaitable, Callable

import grpc
import structlog
from t_tech.invest.async_services import AsyncServices
from t_tech.invest.channels import create_channel
from t_tech.invest.exceptions import AioRequestError, InvestError

from app.core.exceptions import InvalidTokenError, UpstreamUnavailableError

log = structlog.get_logger(__name__)

# `validate_token` with the target and timeout already bound — what the service gets.
TokenValidatorFn = Callable[[str], Awaitable[None]]

# A verdict on the token itself. Every other status means we failed to check, which is not
# the same as the token being bad — the caller is told to retry, not to fix the token.
_REJECTS_THE_TOKEN = frozenset({grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED})


async def validate_token(target: str, timeout_seconds: float, token: str) -> None:
    """Return quietly when the token works; raise otherwise.

    No retries: the user is waiting on this call, and retrying is the bot's job.

    The token never reaches the logs — it is a live credential, and the whole codebase
    keeps it out of tracebacks (`repr=False` on the schemas) and out of log lines.
    """
    # gRPC metadata is ASCII-only, and a token that breaks that rule dies deep inside
    # cygrpc as an opaque "Illegal header value". Schema validation rejects such tokens
    # first; this is the backstop that keeps the failure a 400 rather than a 500.
    if not (token.isascii() and token.isprintable()):
        raise InvalidTokenError("The token contains characters that are not allowed")

    try:
        async with asyncio.timeout(timeout_seconds):
            async with create_channel(target=target, force_async=True) as channel:
                await AsyncServices(channel, token=token).users.get_info()
    except AioRequestError as exc:
        log.warning("tinvest.getinfo.failed", code=exc.code.name, detail=exc.details)
        if exc.code in _REJECTS_THE_TOKEN:
            raise InvalidTokenError("T-Invest rejected the token") from exc
        raise UpstreamUnavailableError(f"T-Invest API answered with {exc.code.name}") from exc
    except (TimeoutError, InvestError, grpc.aio.AioRpcError, grpc.aio.BaseError) as exc:
        # Timeouts, TLS failures and DNS/connection errors all land here.
        log.warning("tinvest.getinfo.failed", error=type(exc).__name__, detail=str(exc))
        raise UpstreamUnavailableError("T-Invest API is unreachable") from exc

    log.info("tinvest.getinfo.ok")
