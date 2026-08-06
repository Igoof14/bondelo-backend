import datetime
from typing import Any

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.portfolio import repository
from app.portfolio.schemas import (
    AccountPosition,
    BondInfo,
    CouponInfo,
    CouponPaymentItem,
    CouponPaymentsResponse,
    DisclosureInfo,
    MaturityInfo,
    MaturityItem,
    NsdInfo,
    OfferInfo,
    OfferItem,
    UpcomingMaturitiesResponse,
    UpcomingOffersResponse,
)


async def _resolve_user(session: AsyncSession, telegram_id: int) -> int:
    bot_user_id = await repository.get_bot_user_id(session, telegram_id)
    if bot_user_id is None:
        raise NotFoundError(f"User with telegram_id={telegram_id} not found")
    return bot_user_id


def _bond(row: Row[Any]) -> BondInfo:
    return BondInfo(
        secid=row.secid,
        isin=row.isin,
        shortname=row.shortname,
        name=row.name,
        facevalue=row.facevalue,
        faceunit=row.faceunit,
        matdate=row.matdate,
    )


def _accounts(row: Row[Any]) -> list[AccountPosition]:
    return [AccountPosition.model_validate(a) for a in row.accounts]


async def get_upcoming_offers(
    session: AsyncSession, telegram_id: int, limit: int
) -> UpcomingOffersResponse:
    """Nearest upcoming offers for the bonds the user currently holds.

    An unknown telegram_id is a 404; a known user with no positions (or no offers
    ahead) is an empty list — the bot needs to tell those two cases apart.
    """
    bot_user_id = await _resolve_user(session, telegram_id)

    today = datetime.date.today()
    rows = await repository.get_upcoming_offers(session, bot_user_id, limit, today)

    items = [
        OfferItem(
            bond=_bond(row),
            offer=OfferInfo(
                date=row.offerdate,
                type=row.offertype,
                date_start=row.offerdatestart,
                date_end=row.offerdateend,
                price=row.price,
                value=row.value,
                agent=row.agent,
                days_left=(row.offerdate - today).days,
            ),
            quantity=row.quantity,
            accounts=_accounts(row),
        )
        for row in rows
    ]
    return UpcomingOffersResponse(telegram_id=telegram_id, items=items)


async def get_upcoming_maturities(
    session: AsyncSession, telegram_id: int, limit: int
) -> UpcomingMaturitiesResponse:
    """Nearest maturity dates for the bonds the user currently holds.

    Same contract as offers: unknown telegram_id is a 404, no upcoming maturities
    is an empty list.
    """
    bot_user_id = await _resolve_user(session, telegram_id)

    today = datetime.date.today()
    rows = await repository.get_upcoming_maturities(session, bot_user_id, limit, today)

    items = [
        MaturityItem(
            bond=_bond(row),
            maturity=MaturityInfo(date=row.matdate, days_left=(row.matdate - today).days),
            quantity=row.quantity,
            accounts=_accounts(row),
        )
        for row in rows
    ]
    return UpcomingMaturitiesResponse(telegram_id=telegram_id, items=items)


def _disclosure(row: Row[Any]) -> DisclosureInfo | None:
    if row.disclosure_isin is None:
        return None
    return DisclosureInfo(
        total_payment_amount=row.total_payment_amount,
        payment_per_security_value=row.payment_per_security_value,
        event_url=row.event_url,
    )


async def get_coupon_payments(
    session: AsyncSession, telegram_id: int, on_date: datetime.date | None
) -> CouponPaymentsResponse:
    """Coupons paid on `on_date` for the bonds the user holds, with the disclosure status.

    Same contract as offers: unknown telegram_id is a 404, no coupons that day is an
    empty list.
    """
    bot_user_id = await _resolve_user(session, telegram_id)

    on_date = on_date or datetime.date.today()
    rows = await repository.get_coupon_payments(session, bot_user_id, on_date)

    items = [
        CouponPaymentItem(
            bond=_bond(row),
            coupon=CouponInfo(
                date=row.coupondate,
                start_date=row.startdate,
                value_rub=row.value_rub,
            ),
            quantity=row.quantity,
            total_value_rub=None if row.value_rub is None else row.value_rub * row.quantity,
            is_disclosure=row.disclosure_isin is not None,
            disclosure=_disclosure(row),
            # NSD settlement data is not collected yet; the defaults are a placeholder so
            # the response shape stays the same once it is.
            nsd=NsdInfo(),
            accounts=_accounts(row),
        )
        for row in rows
    ]
    return CouponPaymentsResponse(telegram_id=telegram_id, date=on_date, items=items)
