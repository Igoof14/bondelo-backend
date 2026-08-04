"""Per-user notification settings — five tables this service owns.

Rows are written only from here; the monitoring services (price-monitoring,
rating-monitoring, fns-monitoring, disclosure-parsing-worker, bondelo-reminders) read
them directly to resolve
who a given alert should go to. A missing row means "off": every one of them filters
on `alerts_enabled IS TRUE`.

The dedup state those services keep (`rating_releases`, `fns_blocking_records`) is
theirs, not ours, and is deliberately not mapped here.
"""

import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Defaults live on the columns because the monitoring services read these rows
# directly — a value has to be there even if it was never set through the API.
DEFAULT_FIRST_ALERT_DAYS = 14
DEFAULT_SECOND_ALERT_DAYS = 5
DEFAULT_NOTIFICATION_TIME = datetime.time(10, 0)

DEFAULT_DROP_WARNING = 4.0
DEFAULT_DROP_CRITICAL = 7.0
DEFAULT_RISE_WARNING = 6.0
DEFAULT_RISE_CRITICAL = 8.0

# Lowest severity a disclosure alert has to reach to be delivered. "low" is the bottom
# of the scale the parser emits, so the default means "every event"; raising it is an
# opt-out the user makes in the UI.
DEFAULT_MIN_RISK_LEVEL = "low"

# Agencies a user is subscribed to out of the box. Unlike the column defaults above
# this is not a schema default: rating settings are one row per agency, so "which
# agencies" is a decision about which rows to create, not what to put in them.
DEFAULT_AGENCIES = ("nra", "nkr", "acra", "ra")


class _Timestamps:
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )


class OfferAlertSettings(Base, _Timestamps):
    """Reminders about an upcoming put option (оферта)."""

    __tablename__ = "offer_alert_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)

    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # How many days before the offer date the two reminders go out.
    first_alert: Mapped[int] = mapped_column(Integer, default=DEFAULT_FIRST_ALERT_DAYS)
    second_alert: Mapped[int] = mapped_column(Integer, default=DEFAULT_SECOND_ALERT_DAYS)

    # Bare TIME: the bot labels it Moscow time in the UI and bondelo-reminders reads
    # it the same way (see reminders/clock.py) — the column carries no timezone.
    notification_time: Mapped[datetime.time] = mapped_column(
        Time, default=DEFAULT_NOTIFICATION_TIME
    )


class PriceAlertSettings(Base, _Timestamps):
    """Thresholds for bond price movement alerts, in percent."""

    __tablename__ = "price_alert_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)

    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    drop_warning_threshold: Mapped[float] = mapped_column(Float, default=DEFAULT_DROP_WARNING)
    drop_critical_threshold: Mapped[float] = mapped_column(Float, default=DEFAULT_DROP_CRITICAL)
    rise_warning_threshold: Mapped[float] = mapped_column(Float, default=DEFAULT_RISE_WARNING)
    rise_critical_threshold: Mapped[float] = mapped_column(Float, default=DEFAULT_RISE_CRITICAL)


class RatingAlertSettings(Base, _Timestamps):
    """Subscription to one rating agency.

    One row per (telegram_id, agency), so adding an agency needs no migration.
    """

    __tablename__ = "rating_alert_settings"
    __table_args__ = (
        UniqueConstraint("telegram_id", "agency", name="uq_rating_alert_settings_user_agency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    # Free-form on purpose: the set of agencies is owned by the bot and the scrapers.
    agency: Mapped[str] = mapped_column(String(16))

    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class FnsAlertSettings(Base, _Timestamps):
    """Subscription to FNS account-blocking alerts. One row per user."""

    __tablename__ = "fns_alert_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)

    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class DisclosureAlertSettings(Base, _Timestamps):
    """Subscription to issuer disclosure alerts (early default warnings).

    Free-form `min_risk_level` for the same reason `agency` above is free-form: the
    scale belongs to disclosure-parsing-worker, which compares it in Python, and a new
    level there must not need a migration here.
    """

    __tablename__ = "disclosure_alert_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)

    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    min_risk_level: Mapped[str] = mapped_column(String(16), default=DEFAULT_MIN_RISK_LEVEL)
