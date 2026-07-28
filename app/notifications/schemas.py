import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.notifications import models


def _threshold() -> Any:
    """Optional percent threshold, bounded the same way the bot's UI bounds it.

    A fresh Field per attribute: one shared FieldInfo would be reused across them.
    """
    return Field(default=None, gt=0, lt=100)


class OfferSettings(BaseModel):
    alerts_enabled: bool = False
    first_alert: int = models.DEFAULT_FIRST_ALERT_DAYS
    second_alert: int = models.DEFAULT_SECOND_ALERT_DAYS
    notification_time: datetime.time = models.DEFAULT_NOTIFICATION_TIME


class OfferSettingsUpdate(BaseModel):
    """Partial update: only the fields present in the body are written."""

    first_alert: int | None = Field(default=None, ge=1, le=365)
    second_alert: int | None = Field(default=None, ge=1, le=365)
    notification_time: datetime.time | None = None


class PriceSettings(BaseModel):
    alerts_enabled: bool = False
    drop_warning_threshold: float = models.DEFAULT_DROP_WARNING
    drop_critical_threshold: float = models.DEFAULT_DROP_CRITICAL
    rise_warning_threshold: float = models.DEFAULT_RISE_WARNING
    rise_critical_threshold: float = models.DEFAULT_RISE_CRITICAL


class PriceSettingsUpdate(BaseModel):
    """Partial update: only the fields present in the body are written."""

    drop_warning_threshold: float | None = _threshold()
    drop_critical_threshold: float | None = _threshold()
    rise_warning_threshold: float | None = _threshold()
    rise_critical_threshold: float | None = _threshold()


class FnsSettings(BaseModel):
    alerts_enabled: bool = False


class RatingSettings(BaseModel):
    """Agencies the user is subscribed to. Anything absent is off."""

    enabled_agencies: list[str] = Field(default_factory=list)


class NotificationSettings(BaseModel):
    """Everything the notifications hub needs, in one response."""

    telegram_id: int
    offers: OfferSettings
    prices: PriceSettings
    ratings: RatingSettings
    fns: FnsSettings


class ToggleResponse(BaseModel):
    alerts_enabled: bool
