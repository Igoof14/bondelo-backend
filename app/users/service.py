from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.notifications import repository as notifications_repository
from app.users import repository
from app.users.schemas import (
    ActiveUsersResponse,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    TokenStateResponse,
)


def _has_token(token: str | None) -> bool:
    # An empty string historically means "no token": that is how it used to be cleared.
    return bool(token)


async def register(session: AsyncSession, payload: RegisterRequest) -> RegisterResponse:
    """Register the user, or record the return of a known one.

    Idempotent: a repeated /start creates no duplicate, it refreshes activity and
    undoes a previous deactivation.

    Every user also gets their notification settings created, switched on. A missing
    row means "off" to the monitoring services, so a user without rows is invisible to
    them no matter which audience they belong to — token holders are matched through
    their portfolio, users without one against the whole market. `ensure_defaults` only
    fills the gaps, so this never overrides a choice made in the UI.
    """
    result = await repository.register(
        session,
        payload.telegram_id,
        payload.username,
        payload.first_name,
        payload.last_name,
    )
    await notifications_repository.ensure_defaults(session, payload.telegram_id)
    await session.commit()
    return RegisterResponse(
        telegram_id=payload.telegram_id,
        is_new_user=result.is_new_user,
        has_token=_has_token(result.token),
    )


async def get_token(session: AsyncSession, telegram_id: int) -> TokenResponse:
    row = await repository.get_token(session, telegram_id)
    if row is None:
        raise NotFoundError(f"User with telegram_id={telegram_id} not found")
    return TokenResponse(token=row.tinvest_token or None)


async def set_token(session: AsyncSession, telegram_id: int, token: str) -> TokenStateResponse:
    if not await repository.set_token(session, telegram_id, token):
        raise NotFoundError(f"User with telegram_id={telegram_id} not found")
    return TokenStateResponse(has_token=True)


async def remove_token(session: AsyncSession, telegram_id: int) -> None:
    if not await repository.set_token(session, telegram_id, None):
        raise NotFoundError(f"User with telegram_id={telegram_id} not found")


async def deactivate(session: AsyncSession, telegram_id: int) -> None:
    if not await repository.deactivate(session, telegram_id):
        raise NotFoundError(f"User with telegram_id={telegram_id} not found")


async def get_active_users(session: AsyncSession) -> ActiveUsersResponse:
    telegram_ids = list(await repository.get_active_telegram_ids(session))
    return ActiveUsersResponse(telegram_ids=telegram_ids, count=len(telegram_ids))
