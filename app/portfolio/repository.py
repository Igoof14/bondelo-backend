import datetime
from collections.abc import Sequence
from typing import Any

from sqlalchemy import CTE, Row, Select, Text, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession

from app.portfolio.models import (
    BotUser,
    DisclosurePayment,
    MoexBond,
    MoexBondCoupon,
    MoexBondOffer,
    UserBond,
)

# The disclosure feed splits payments by kind; only coupons matter here.
COUPON_PAYMENT_CATEGORY = "coupon_income"

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


def _coupon_disclosure_cte(on_date: datetime.date) -> CTE:
    """The most recent coupon disclosure per ISIN for the given due date.

    An issuer can publish several messages about the same payment (corrections,
    re-publications); without DISTINCT ON the outer join would duplicate coupon rows.
    """
    return (
        select(
            DisclosurePayment.isin.label("isin"),
            DisclosurePayment.total_payment_amount,
            DisclosurePayment.payment_per_security_value,
            DisclosurePayment.event_url,
        )
        .where(
            cast(DisclosurePayment.payment_category, Text) == COUPON_PAYMENT_CATEGORY,
            DisclosurePayment.obligation_due_date == on_date,
            DisclosurePayment.isin.is_not(None),
        )
        .distinct(DisclosurePayment.isin)
        .order_by(
            DisclosurePayment.isin,
            DisclosurePayment.event_date.desc().nullslast(),
            DisclosurePayment.id.desc(),
        )
        .cte("coupon_disclosure")
    )


def _coupon_payments_query(bot_user_id: int, on_date: datetime.date) -> Select[Any]:
    disclosure = _coupon_disclosure_cte(on_date)
    return (
        _held_bonds_query(bot_user_id)
        .add_columns(
            MoexBondCoupon.coupondate,
            MoexBondCoupon.startdate,
            MoexBondCoupon.value_rub,
            # Presence of this column is what tells the service a disclosure exists.
            disclosure.c.isin.label("disclosure_isin"),
            disclosure.c.total_payment_amount,
            disclosure.c.payment_per_security_value,
            disclosure.c.event_url,
        )
        .join(MoexBondCoupon, MoexBondCoupon.secid == MoexBond.secid)
        .outerjoin(disclosure, disclosure.c.isin == MoexBond.isin)
        .where(MoexBondCoupon.coupondate == on_date)
        .order_by(MoexBond.shortname, MoexBond.secid)
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


async def get_coupon_payments(
    session: AsyncSession, bot_user_id: int, on_date: datetime.date
) -> Sequence[Row[Any]]:
    result = await session.execute(_coupon_payments_query(bot_user_id, on_date))
    return result.all()
