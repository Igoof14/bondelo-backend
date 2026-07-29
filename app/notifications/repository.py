"""Queries over the five settings tables.

Every write is an upsert: the bot's UI lets a user flip a toggle before any row for
them exists, and a missing row is simply "everything off, defaults everywhere".
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import (
    DEFAULT_AGENCIES,
    DisclosureAlertSettings,
    FnsAlertSettings,
    OfferAlertSettings,
    PriceAlertSettings,
    RatingAlertSettings,
)

# The four tables keyed by telegram_id alone; ratings is keyed by (user, agency)
# and so has its own functions below.
type SingleRow = (
    OfferAlertSettings | PriceAlertSettings | FnsAlertSettings | DisclosureAlertSettings
)

_SINGLE_ROW_MODELS: tuple[type[SingleRow], ...] = (
    OfferAlertSettings,
    PriceAlertSettings,
    FnsAlertSettings,
    DisclosureAlertSettings,
)


async def ensure_defaults(session: AsyncSession, telegram_id: int) -> None:
    """Create the user's settings rows, switched on, if they do not exist yet.

    A user without a T-Invest token has no portfolio, so the monitoring services
    match them against the whole market instead. That only works if they have rows
    at all — a missing row means "off" everywhere.

    `DO NOTHING` rather than `DO UPDATE`: an existing row is a choice the user made
    in the UI, and re-running /start must not switch a section back on behind their
    back. Callers commit.
    """
    for model in _SINGLE_ROW_MODELS:
        await session.execute(
            insert(model)
            .values(telegram_id=telegram_id, alerts_enabled=True)
            .on_conflict_do_nothing(index_elements=[model.telegram_id])
        )

    await session.execute(
        insert(RatingAlertSettings)
        .values(
            [
                {"telegram_id": telegram_id, "agency": agency, "alerts_enabled": True}
                for agency in DEFAULT_AGENCIES
            ]
        )
        # Named constraint rather than columns: the unique index is composite.
        .on_conflict_do_nothing(constraint="uq_rating_alert_settings_user_agency")
    )


async def get[S: SingleRow](session: AsyncSession, model: type[S], telegram_id: int) -> S | None:
    return await session.scalar(select(model).where(model.telegram_id == telegram_id))


async def toggle[S: SingleRow](session: AsyncSession, model: type[S], telegram_id: int) -> bool:
    """Flip `alerts_enabled` and return the new value.

    The flip happens inside the statement (`NOT alerts_enabled`), so two taps racing
    each other cannot both read the same old value and write the same new one.
    """
    stmt = (
        insert(model)
        .values(telegram_id=telegram_id, alerts_enabled=True)
        .on_conflict_do_update(
            index_elements=[model.telegram_id],
            set_={"alerts_enabled": ~model.alerts_enabled},
        )
        .returning(model.alerts_enabled)
    )
    enabled = await session.scalar(stmt)
    await session.commit()
    return bool(enabled)


async def update_fields[S: SingleRow](
    session: AsyncSession,
    model: type[S],
    telegram_id: int,
    values: dict[str, Any],
) -> S:
    """Write the given fields, creating the row with defaults if it is missing."""
    row = await session.scalar(
        insert(model)
        .values(telegram_id=telegram_id, **values)
        .on_conflict_do_update(index_elements=[model.telegram_id], set_=values)
        .returning(model)
    )
    await session.commit()
    # RETURNING always yields the row it just wrote, conflict or not.
    assert row is not None
    return row


async def get_enabled_agencies(session: AsyncSession, telegram_id: int) -> Sequence[str]:
    result = await session.execute(
        select(RatingAlertSettings.agency)
        .where(
            RatingAlertSettings.telegram_id == telegram_id,
            RatingAlertSettings.alerts_enabled.is_(True),
        )
        .order_by(RatingAlertSettings.agency)
    )
    return result.scalars().all()


async def toggle_agency(session: AsyncSession, telegram_id: int, agency: str) -> bool:
    """Flip the subscription to one agency and return the new value."""
    stmt = (
        insert(RatingAlertSettings)
        .values(telegram_id=telegram_id, agency=agency, alerts_enabled=True)
        .on_conflict_do_update(
            # Named constraint rather than columns: the unique index is composite.
            constraint="uq_rating_alert_settings_user_agency",
            set_={"alerts_enabled": ~RatingAlertSettings.alerts_enabled},
        )
        .returning(RatingAlertSettings.alerts_enabled)
    )
    enabled = await session.scalar(stmt)
    await session.commit()
    return bool(enabled)
