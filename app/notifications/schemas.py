import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.notifications import models

# The disclosure severity scale, mirrored from disclosure-parsing-worker's `RiskLevel`.
# Only the levels that can carry an alert are offered: the two below `low` mean the
# worker never emits a notification at all, so picking them would be a second "off".
RiskLevel = Literal["low", "medium", "high", "critical"]


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


class DisclosureSettings(BaseModel):
    alerts_enabled: bool = False
    min_risk_level: RiskLevel = models.DEFAULT_MIN_RISK_LEVEL


class DisclosureSettingsUpdate(BaseModel):
    """Partial update: only the fields present in the body are written."""

    min_risk_level: RiskLevel | None = None


class NotificationSettings(BaseModel):
    """Everything the notifications hub needs, in one response."""

    telegram_id: int
    offers: OfferSettings
    prices: PriceSettings
    ratings: RatingSettings
    fns: FnsSettings
    disclosure: DisclosureSettings


class ToggleResponse(BaseModel):
    alerts_enabled: bool
