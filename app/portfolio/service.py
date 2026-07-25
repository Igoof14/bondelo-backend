import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.portfolio import repository
from app.portfolio.schemas import (
    AccountPosition,
    BondInfo,
    OfferInfo,
    OfferItem,
    UpcomingOffersResponse,
)


async def get_upcoming_offers(
    session: AsyncSession, telegram_id: int, limit: int
) -> UpcomingOffersResponse:
    """Nearest upcoming offers for the bonds the user currently holds.

    An unknown telegram_id is a 404; a known user with no positions (or no offers
    ahead) is an empty list — the bot needs to tell those two cases apart.
    """
    bot_user_id = await repository.get_bot_user_id(session, telegram_id)
    if bot_user_id is None:
        raise NotFoundError(f"User with telegram_id={telegram_id} not found")

    today = datetime.date.today()
    rows = await repository.get_upcoming_offers(session, bot_user_id, limit, today)

    items = [
        OfferItem(
            bond=BondInfo(
                secid=row.secid,
                isin=row.isin,
                shortname=row.shortname,
                name=row.name,
                facevalue=row.facevalue,
                faceunit=row.faceunit,
                matdate=row.matdate,
            ),
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
            accounts=[AccountPosition.model_validate(a) for a in row.accounts],
        )
        for row in rows
    ]
    return UpcomingOffersResponse(telegram_id=telegram_id, items=items)
