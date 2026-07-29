"""backfill: create settings rows for every active user

b4e1c7f20a91 gave settings rows to users without a token, on the reasoning that only
they needed them: they have no portfolio, so the monitoring services match them against
the whole market, which reaches nobody without rows. Token holders were left out — but a
missing row means "off" for them too, so a holder who never opened the notifications hub
is invisible to price/offer/fns/rating monitoring just the same.

`users.service.register` now calls `ensure_defaults` for everyone rather than for the
tokenless only. This revision does the same for everyone already in `bot_users`.

Includes `disclosure_alert_settings`, which did not exist when b4e1c7f20a91 was written.
c7f3a1d95e02 already backfilled that table for all active users, so those inserts are a
no-op here — spelled out anyway so this revision describes one complete settings set.

`DO NOTHING` on every insert: an existing row is a choice the user made in the UI, and a
backfill must not switch a section they turned off back on. That also makes the revision
safe to re-run.

Like b4e1c7f20a91, this one DOES run against production.

Revision ID: e2f9a4c81d63
Revises: c7f3a1d95e02
Create Date: 2026-07-29 18:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f9a4c81d63"
down_revision: str | Sequence[str] | None = "c7f3a1d95e02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Both audiences this time — no token predicate, unlike b4e1c7f20a91.
_ACTIVE = """
    SELECT telegram_id FROM bot_users WHERE is_active IS TRUE
"""

# Values from notifications.models, inlined: a migration has to keep describing the
# schema as it was, even after those constants move on.
_DEFAULT_AGENCIES = ("nra", "nkr")

# Every default on these tables is declared Python-side (`default=` in the model), so
# the columns are NOT NULL with no DDL default. Raw SQL has to spell them out — an
# INSERT that names only telegram_id fails on first_alert.
_SINGLE_ROW_TABLES = {
    "offer_alert_settings": {
        "first_alert": "14",
        "second_alert": "5",
        "notification_time": "TIME '10:00'",
    },
    "price_alert_settings": {
        "drop_warning_threshold": "4.0",
        "drop_critical_threshold": "7.0",
        "rise_warning_threshold": "6.0",
        "rise_critical_threshold": "8.0",
    },
    "fns_alert_settings": {},
    "disclosure_alert_settings": {"min_risk_level": "'low'"},
}


def upgrade() -> None:
    """Create switched-on settings rows for every active user missing them."""
    for table, defaults in _SINGLE_ROW_TABLES.items():
        columns = "".join(f", {name}" for name in defaults)
        values = "".join(f", {value}" for value in defaults.values())
        op.execute(
            f"""
            INSERT INTO {table} (telegram_id, alerts_enabled, created_at{columns})
            SELECT telegram_id, TRUE, now(){values} FROM ({_ACTIVE}) AS active
            ON CONFLICT (telegram_id) DO NOTHING
            """
        )

    agencies = ", ".join(f"('{agency}')" for agency in _DEFAULT_AGENCIES)
    op.execute(
        f"""
        INSERT INTO rating_alert_settings (telegram_id, agency, alerts_enabled, created_at)
        SELECT active.telegram_id, agency.code, TRUE, now()
        FROM ({_ACTIVE}) AS active
        CROSS JOIN (VALUES {agencies}) AS agency(code)
        ON CONFLICT ON CONSTRAINT uq_rating_alert_settings_user_agency DO NOTHING
        """
    )


def downgrade() -> None:
    """Irreversible on purpose.

    The inserted rows are indistinguishable from ones a user created by tapping a
    toggle, so deleting them would take real settings with them.
    """
