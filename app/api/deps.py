from functools import partial
from typing import Annotated

from fastapi import Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.tinvest.client import TokenValidatorFn, validate_token

DbSession = Annotated[AsyncSession, Depends(get_session)]

# Shared by every router under the /users prefix, so the description stays identical.
TelegramId = Annotated[int, Path(description="Telegram user id")]


def get_token_validator(request: Request) -> TokenValidatorFn:
    """The broker check, bound to the configured endpoint and timeout.

    A dependency rather than a direct import so tests can swap the network call out
    through `dependency_overrides`.
    """
    settings = request.app.state.settings
    return partial(
        validate_token,
        settings.tinvest_grpc_target,
        settings.tinvest_timeout_seconds,
    )


TokenValidator = Annotated[TokenValidatorFn, Depends(get_token_validator)]
