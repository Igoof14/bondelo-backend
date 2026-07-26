from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import DbSession
from app.portfolio import service
from app.portfolio.schemas import UpcomingMaturitiesResponse, UpcomingOffersResponse

router = APIRouter(prefix="/users", tags=["portfolio"])

TelegramId = Annotated[int, Path(description="Telegram user id")]


@router.get("/{telegram_id}/offers", response_model=UpcomingOffersResponse)
async def upcoming_offers(
    session: DbSession,
    telegram_id: TelegramId,
    limit: Annotated[int, Query(ge=1, le=50, description="How many nearest offers to return")] = 5,
) -> UpcomingOffersResponse:
    """Nearest offers, from today onwards, for bonds held in the user's portfolio."""
    return await service.get_upcoming_offers(session, telegram_id, limit)


@router.get("/{telegram_id}/maturities", response_model=UpcomingMaturitiesResponse)
async def upcoming_maturities(
    session: DbSession,
    telegram_id: TelegramId,
    limit: Annotated[
        int, Query(ge=1, le=50, description="How many nearest maturities to return")
    ] = 5,
) -> UpcomingMaturitiesResponse:
    """Nearest maturity dates, from today onwards, for bonds held in the user's portfolio."""
    return await service.get_upcoming_maturities(session, telegram_id, limit)
