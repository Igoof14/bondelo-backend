import datetime
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Row, Select, Text, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession

from app.portfolio.models import BotUser, MoexBond, MoexBondOffer, UserBond

# A cancelled offer is not an upcoming event, so it never belongs in a reminder.
# MOEX encodes the state in offertype itself ("Оферта (отменено)").
EXCLUDED_OFFERTYPE_PATTERNS = ("%отменено%",)


async def get_bot_user_id(session: AsyncSession, telegram_id: int) -> int | None:
    return await session.scalar(select(BotUser.id).where(BotUser.telegram_id == telegram_id))


def _upcoming_offers_query(bot_user_id: int, limit: int, today: datetime.date) -> Select[Any]:
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
    positions = (
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

    query = (
        select(
            MoexBond.secid,
            MoexBond.isin,
            MoexBond.shortname,
            MoexBond.name,
            MoexBond.facevalue,
            MoexBond.faceunit,
            MoexBond.matdate,
            MoexBondOffer.offerdate,
            MoexBondOffer.offertype,
            MoexBondOffer.offerdatestart,
            MoexBondOffer.offerdateend,
            MoexBondOffer.price,
            MoexBondOffer.value,
            MoexBondOffer.agent,
            positions.c.quantity,
            positions.c.accounts,
        )
        .select_from(positions)
        # ISIN is de-facto unique in moex_bonds, so this join does not fan out rows.
        .join(MoexBond, MoexBond.isin == positions.c.isin)
        .join(MoexBondOffer, MoexBondOffer.secid == MoexBond.secid)
        .where(MoexBondOffer.offerdate >= today)
        .order_by(MoexBondOffer.offerdate, MoexBond.secid)
        .limit(limit)
    )
    for pattern in EXCLUDED_OFFERTYPE_PATTERNS:
        query = query.where(~MoexBondOffer.offertype.ilike(pattern))
    return query


async def get_upcoming_offers(
    session: AsyncSession, bot_user_id: int, limit: int, today: datetime.date
) -> Sequence[Row[Any]]:
    result = await session.execute(_upcoming_offers_query(bot_user_id, limit, today))
    return result.all()
