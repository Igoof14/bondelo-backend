from fastapi import APIRouter, status

from app.api.deps import DbSession, TelegramId
from app.users import service
from app.users.schemas import (
    ActiveUsersResponse,
    RegisterRequest,
    RegisterResponse,
    TokenRequest,
    TokenResponse,
    TokenStateResponse,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=RegisterResponse)
async def register(session: DbSession, payload: RegisterRequest) -> RegisterResponse:
    """Register a bot user, or record the return of a known one.

    Idempotent: a repeated call creates no duplicate, it refreshes activity and
    undoes a previous deactivation. `is_new_user` tells a first /start from a repeat.
    """
    return await service.register(session, payload)


# Declared before `/{telegram_id}/...` so the static segment is not swallowed by it.
@router.get("/active", response_model=ActiveUsersResponse)
async def active_users(session: DbSession) -> ActiveUsersResponse:
    """Telegram ids of every active user — used for broadcasts."""
    return await service.get_active_users(session)


@router.get("/{telegram_id}/token", response_model=TokenResponse)
async def get_token(session: DbSession, telegram_id: TelegramId) -> TokenResponse:
    """The user's read-only T-Invest token; null when none is connected."""
    return await service.get_token(session, telegram_id)


@router.put("/{telegram_id}/token", response_model=TokenStateResponse)
async def set_token(
    session: DbSession, telegram_id: TelegramId, payload: TokenRequest
) -> TokenStateResponse:
    """Store the T-Invest token. Validating it is the caller's job."""
    return await service.set_token(session, telegram_id, payload.token)


@router.delete("/{telegram_id}/token", status_code=status.HTTP_204_NO_CONTENT)
async def remove_token(session: DbSession, telegram_id: TelegramId) -> None:
    """Unlink the T-Invest token."""
    await service.remove_token(session, telegram_id)


@router.post("/{telegram_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate(session: DbSession, telegram_id: TelegramId) -> None:
    """Mark the user inactive — e.g. after they blocked the bot."""
    await service.deactivate(session, telegram_id)
