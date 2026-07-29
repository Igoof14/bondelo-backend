from typing import Annotated

from fastapi import APIRouter, Path

from app.api.deps import DbSession, TelegramId
from app.notifications import service
from app.notifications.schemas import (
    DisclosureSettings,
    DisclosureSettingsUpdate,
    NotificationSettings,
    OfferSettings,
    OfferSettingsUpdate,
    PriceSettings,
    PriceSettingsUpdate,
    ToggleResponse,
)

# Path params in the prefix: everything here hangs off one user.
router = APIRouter(prefix="/users/{telegram_id}/notifications", tags=["notifications"])

Agency = Annotated[str, Path(min_length=1, max_length=16, description="Rating agency code")]


@router.get("", response_model=NotificationSettings)
async def get_settings(session: DbSession, telegram_id: TelegramId) -> NotificationSettings:
    """State of every section at once — one call per notifications hub render.

    Never creates rows: an untouched user reads back the defaults.
    """
    return await service.get_all(session, telegram_id)


@router.post("/offers/toggle", response_model=ToggleResponse)
async def toggle_offers(session: DbSession, telegram_id: TelegramId) -> ToggleResponse:
    """Flip offer reminders and return the new state."""
    return await service.toggle_offers(session, telegram_id)


@router.patch("/offers", response_model=OfferSettings)
async def update_offers(
    session: DbSession, telegram_id: TelegramId, payload: OfferSettingsUpdate
) -> OfferSettings:
    """Change reminder lead times or delivery time. Omitted fields stay as they are."""
    return await service.update_offers(session, telegram_id, payload)


@router.post("/prices/toggle", response_model=ToggleResponse)
async def toggle_prices(session: DbSession, telegram_id: TelegramId) -> ToggleResponse:
    """Flip price alerts and return the new state."""
    return await service.toggle_prices(session, telegram_id)


@router.patch("/prices", response_model=PriceSettings)
async def update_prices(
    session: DbSession, telegram_id: TelegramId, payload: PriceSettingsUpdate
) -> PriceSettings:
    """Change price thresholds. Omitted fields stay as they are."""
    return await service.update_prices(session, telegram_id, payload)


@router.post("/fns/toggle", response_model=ToggleResponse)
async def toggle_fns(session: DbSession, telegram_id: TelegramId) -> ToggleResponse:
    """Flip FNS blocking alerts and return the new state."""
    return await service.toggle_fns(session, telegram_id)


@router.post("/disclosure/toggle", response_model=ToggleResponse)
async def toggle_disclosure(session: DbSession, telegram_id: TelegramId) -> ToggleResponse:
    """Flip issuer disclosure alerts and return the new state."""
    return await service.toggle_disclosure(session, telegram_id)


@router.patch("/disclosure", response_model=DisclosureSettings)
async def update_disclosure(
    session: DbSession, telegram_id: TelegramId, payload: DisclosureSettingsUpdate
) -> DisclosureSettings:
    """Change the lowest risk level that still gets delivered. Omitted fields stay put."""
    return await service.update_disclosure(session, telegram_id, payload)


@router.post("/ratings/{agency}/toggle", response_model=ToggleResponse)
async def toggle_agency(
    session: DbSession, telegram_id: TelegramId, agency: Agency
) -> ToggleResponse:
    """Flip the subscription to one rating agency.

    The set of agencies is owned by the bot and the scrapers, so the code is taken
    as given rather than validated against an enum that would need updating here.
    """
    return await service.toggle_agency(session, telegram_id, agency)
