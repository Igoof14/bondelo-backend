import datetime
from collections.abc import Sequence
from typing import Any

from sqlalchemy import CTE, Row, Select, Text, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession

from app.portfolio.models import BotUser, MoexBond, MoexBondOffer, UserBond

# A cancelled offer is not an upcoming event, so it never belongs in a reminder.
# MOEX encodes the state in offertype itself ("Оферта (отменено)").
EXCLUDED_OFFERTYPE_PATTERNS = ("%отменено%",)

_BOND_COLUMNS = (
    MoexBond.secid,
    MoexBond.isin,
    MoexBond.shortname,
    MoexBond.name,
    MoexBond.facevalue,
    MoexBond.faceunit,
    MoexBond.matdate,
)


async def get_bot_user_id(session: AsyncSession, telegram_id: int) -> int | None:
    return await session.scalar(select(BotUser.id).where(BotUser.telegram_id == telegram_id))


def _positions_cte(bot_user_id: int) -> CTE:
    """One row per ISIN the user holds: total quantity plus the per-account breakdown."""
    account = func.json_build_object(
        "broker",
        UserBond.broker,
        "account_id",
        UserBond.account_id,
        "account_name",
        UserBond.account_name,
        # Cast to text so the Decimal survives JSON without a float round-trip.
        "quantity",
        cast(UserBond.quantity, Text),
    )
    return (
        select(
            UserBond.isin.label("isin"),
            func.sum(UserBond.quantity).label("quantity"),
            func.json_agg(
                aggregate_order_by(account, UserBond.broker, UserBond.account_id), type_=JSONB
            ).label("accounts"),
        )
        .where(UserBond.bot_user_id == bot_user_id, UserBond.isin.is_not(None))
        .group_by(UserBond.isin)
        .cte("positions")
    )


def _held_bonds_query(bot_user_id: int) -> Select[Any]:
    """Bonds from the user's portfolio joined to MOEX reference data."""
    positions = _positions_cte(bot_user_id)
    return (
        select(*_BOND_COLUMNS, positions.c.quantity, positions.c.accounts)
        .select_from(positions)
        # ISIN is de-facto unique in moex_bonds, so this join does not fan out rows.
        .join(MoexBond, MoexBond.isin == positions.c.isin)
    )


def _upcoming_offers_query(bot_user_id: int, limit: int, today: datetime.date) -> Select[Any]:
    query = (
        _held_bonds_query(bot_user_id)
        .add_columns(
            MoexBondOffer.offerdate,
            MoexBondOffer.offertype,
            MoexBondOffer.offerdatestart,
            MoexBondOffer.offerdateend,
            MoexBondOffer.price,
            MoexBondOffer.value,
            MoexBondOffer.agent,
        )
        .join(MoexBondOffer, MoexBondOffer.secid == MoexBond.secid)
        .where(MoexBondOffer.offerdate >= today)
        .order_by(MoexBondOffer.offerdate, MoexBond.secid)
        .limit(limit)
    )
    for pattern in EXCLUDED_OFFERTYPE_PATTERNS:
        query = query.where(~MoexBondOffer.offertype.ilike(pattern))
    return query


def _upcoming_maturities_query(bot_user_id: int, limit: int, today: datetime.date) -> Select[Any]:
    return (
        _held_bonds_query(bot_user_id)
        .where(MoexBond.matdate.is_not(None), MoexBond.matdate >= today)
        .order_by(MoexBond.matdate, MoexBond.secid)
        .limit(limit)
    )


async def get_upcoming_offers(
    session: AsyncSession, bot_user_id: int, limit: int, today: datetime.date
) -> Sequence[Row[Any]]:
    result = await session.execute(_upcoming_offers_query(bot_user_id, limit, today))
    return result.all()


async def get_upcoming_maturities(
    session: AsyncSession, bot_user_id: int, limit: int, today: datetime.date
) -> Sequence[Row[Any]]:
    result = await session.execute(_upcoming_maturities_query(bot_user_id, limit, today))
    return result.all()
