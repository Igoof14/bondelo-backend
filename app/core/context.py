"""Request context: trace id and caller identity, bound to structlog contextvars."""

import base64
import binascii
import json
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_TRACE_HEADER = "X-Cloud-Trace-Context"


def _trace_id(request: Request) -> str:
    # Cloud Run sets "TRACE_ID/SPAN_ID;o=1" on every incoming request.
    header = request.headers.get(_TRACE_HEADER)
    if header:
        return header.split("/", 1)[0]
    return uuid.uuid4().hex


def _caller(request: Request) -> str | None:
    """Email of the calling service account, for logs only.

    Cloud Run has already verified the ID token's signature and audience before the
    request reaches this process (the service is deployed with
    --no-allow-unauthenticated), so we only decode the payload here. This is NOT an
    authorization check and must never be used as one.
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    parts = header.removeprefix("Bearer ").split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    try:
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        claims = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        return None
    email = claims.get("email")
    return email if isinstance(email, str) else None


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        trace_id = _trace_id(request)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            caller=_caller(request),
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = trace_id
        return response
