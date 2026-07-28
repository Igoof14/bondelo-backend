import datetime
from collections.abc import Sequence
from typing import NamedTuple

from sqlalchemy import Row, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import BotUser


class Registration(NamedTuple):
    is_new_user: bool
    token: str | None


async def register(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> Registration:
    """Insert the user, or refresh an existing one — in a single statement.

    In Postgres `xmax = 0` holds exactly for rows this INSERT itself created, so
    ON CONFLICT can tell a first /start from a repeat one without a preceding
    SELECT, and therefore without a race between two concurrent updates.
    """
    now = datetime.datetime.now(datetime.UTC)
    stmt = (
        insert(BotUser)
        .values(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            last_activity=now,
        )
        .on_conflict_do_update(
            index_elements=[BotUser.telegram_id],
            set_={"last_activity": now, "is_active": True},
        )
        .returning(BotUser.tinvest_token, literal_column("(xmax = 0)").label("is_new"))
    )
    row = (await session.execute(stmt)).one()
    await session.commit()
    return Registration(is_new_user=row.is_new, token=row.tinvest_token)


async def get_token(session: AsyncSession, telegram_id: int) -> Row[tuple[str | None]] | None:
    """The row holding the token, or None when there is no such user.

    Returns a Row rather than the token itself: a null token and a missing user
    are different cases, and only the second one is a 404.
    """
    return (
        await session.execute(
            select(BotUser.tinvest_token).where(BotUser.telegram_id == telegram_id)
        )
    ).one_or_none()


async def _update_returning_id(session: AsyncSession, telegram_id: int, **values: object) -> bool:
    """UPDATE by telegram_id; True when a row matched.

    The match is taken from RETURNING rather than rowcount, whose type SQLAlchemy
    does not promise on the generic Result.
    """
    updated = await session.scalar(
        update(BotUser)
        .where(BotUser.telegram_id == telegram_id)
        .values(**values)
        .returning(BotUser.id)
    )
    await session.commit()
    return updated is not None


async def set_token(session: AsyncSession, telegram_id: int, token: str | None) -> bool:
    """Set or clear the token. False means the user was not found."""
    return await _update_returning_id(session, telegram_id, tinvest_token=token)


async def deactivate(session: AsyncSession, telegram_id: int) -> bool:
    """Mark the user inactive. False means the user was not found."""
    return await _update_returning_id(session, telegram_id, is_active=False)


async def get_active_telegram_ids(session: AsyncSession) -> Sequence[int]:
    result = await session.execute(
        select(BotUser.telegram_id).where(BotUser.is_active).order_by(BotUser.id)
    )
    return result.scalars().all()
