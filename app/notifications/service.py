from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications import repository
from app.notifications.models import (
    DisclosureAlertSettings,
    FnsAlertSettings,
    OfferAlertSettings,
    PriceAlertSettings,
)
from app.notifications.schemas import (
    DisclosureSettings,
    DisclosureSettingsUpdate,
    FnsSettings,
    NotificationSettings,
    OfferSettings,
    OfferSettingsUpdate,
    PriceSettings,
    PriceSettingsUpdate,
    RatingSettings,
    ToggleResponse,
)


async def get_all(session: AsyncSession, telegram_id: int) -> NotificationSettings:
    """Every section's state in one response — the bot's hub renders them all at once.

    Reading does not create rows: a user who never touched the settings gets the
    defaults back, which is exactly what a missing row means to the monitorings.
    """
    offers = await repository.get(session, OfferAlertSettings, telegram_id)
    prices = await repository.get(session, PriceAlertSettings, telegram_id)
    fns = await repository.get(session, FnsAlertSettings, telegram_id)
    disclosure = await repository.get(session, DisclosureAlertSettings, telegram_id)
    agencies = await repository.get_enabled_agencies(session, telegram_id)

    return NotificationSettings(
        telegram_id=telegram_id,
        offers=OfferSettings.model_validate(offers, from_attributes=True)
        if offers
        else OfferSettings(),
        prices=PriceSettings.model_validate(prices, from_attributes=True)
        if prices
        else PriceSettings(),
        ratings=RatingSettings(enabled_agencies=list(agencies)),
        fns=FnsSettings.model_validate(fns, from_attributes=True) if fns else FnsSettings(),
        disclosure=DisclosureSettings.model_validate(disclosure, from_attributes=True)
        if disclosure
        else DisclosureSettings(),
    )


async def toggle_offers(session: AsyncSession, telegram_id: int) -> ToggleResponse:
    return ToggleResponse(
        alerts_enabled=await repository.toggle(session, OfferAlertSettings, telegram_id)
    )


async def toggle_prices(session: AsyncSession, telegram_id: int) -> ToggleResponse:
    return ToggleResponse(
        alerts_enabled=await repository.toggle(session, PriceAlertSettings, telegram_id)
    )


async def toggle_fns(session: AsyncSession, telegram_id: int) -> ToggleResponse:
    return ToggleResponse(
        alerts_enabled=await repository.toggle(session, FnsAlertSettings, telegram_id)
    )


async def toggle_disclosure(session: AsyncSession, telegram_id: int) -> ToggleResponse:
    return ToggleResponse(
        alerts_enabled=await repository.toggle(session, DisclosureAlertSettings, telegram_id)
    )


async def toggle_agency(session: AsyncSession, telegram_id: int, agency: str) -> ToggleResponse:
    return ToggleResponse(
        alerts_enabled=await repository.toggle_agency(session, telegram_id, agency)
    )


async def update_offers(
    session: AsyncSession, telegram_id: int, payload: OfferSettingsUpdate
) -> OfferSettings:
    """Apply the fields that were sent; an empty body just returns current state."""
    values = payload.model_dump(exclude_none=True)
    if not values:
        return (await get_all(session, telegram_id)).offers
    row = await repository.update_fields(session, OfferAlertSettings, telegram_id, values)
    return OfferSettings.model_validate(row, from_attributes=True)


async def update_prices(
    session: AsyncSession, telegram_id: int, payload: PriceSettingsUpdate
) -> PriceSettings:
    """Apply the fields that were sent; an empty body just returns current state."""
    values = payload.model_dump(exclude_none=True)
    if not values:
        return (await get_all(session, telegram_id)).prices
    row = await repository.update_fields(session, PriceAlertSettings, telegram_id, values)
    return PriceSettings.model_validate(row, from_attributes=True)


async def update_disclosure(
    session: AsyncSession, telegram_id: int, payload: DisclosureSettingsUpdate
) -> DisclosureSettings:
    """Apply the fields that were sent; an empty body just returns current state."""
    values = payload.model_dump(exclude_none=True)
    if not values:
        return (await get_all(session, telegram_id)).disclosure
    row = await repository.update_fields(session, DisclosureAlertSettings, telegram_id, values)
    return DisclosureSettings.model_validate(row, from_attributes=True)
