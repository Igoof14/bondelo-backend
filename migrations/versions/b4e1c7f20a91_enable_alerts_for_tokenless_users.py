"""backfill: enable alerts for users without a token

Until now a user only ever received alerts if they had connected a T-Invest token:
the monitoring services resolve recipients through `user_bonds`, and that table is
only populated for token holders. Alerts are now also matched against the whole
market for users without a token — but only for those who have settings rows, since
a missing row means "off" everywhere.

New users get their rows from `users.service.register`. This revision does the same
for everyone already in `bot_users`.

`DO NOTHING` on every insert: an existing row is a choice the user made in the UI,
and a backfill must not switch a section they turned off back on. That also makes
the revision safe to re-run.

Unlike the two baselines before it, this one DOES run against production.

Revision ID: b4e1c7f20a91
Revises: 85a23d76a32d
Create Date: 2026-07-29 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4e1c7f20a91"
down_revision: str | Sequence[str] | None = "85a23d76a32d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Empty string is the legacy marker for "no token" — see users.service._has_token.
_TOKENLESS = """
    SELECT telegram_id FROM bot_users
    WHERE is_active IS TRUE AND COALESCE(tinvest_token, '') = ''
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
}


def upgrade() -> None:
    """Create switched-on settings rows for every active user without a token."""
    for table, defaults in _SINGLE_ROW_TABLES.items():
        columns = "".join(f", {name}" for name in defaults)
        values = "".join(f", {value}" for value in defaults.values())
        op.execute(
            f"""
            INSERT INTO {table} (telegram_id, alerts_enabled, created_at{columns})
            SELECT telegram_id, TRUE, now(){values} FROM ({_TOKENLESS}) AS tokenless
            ON CONFLICT (telegram_id) DO NOTHING
            """
        )

    agencies = ", ".join(f"('{agency}')" for agency in _DEFAULT_AGENCIES)
    op.execute(
        f"""
        INSERT INTO rating_alert_settings (telegram_id, agency, alerts_enabled, created_at)
        SELECT tokenless.telegram_id, agency.code, TRUE, now()
        FROM ({_TOKENLESS}) AS tokenless
        CROSS JOIN (VALUES {agencies}) AS agency(code)
        ON CONFLICT ON CONSTRAINT uq_rating_alert_settings_user_agency DO NOTHING
        """
    )


def downgrade() -> None:
    """Irreversible on purpose.

    The inserted rows are indistinguishable from ones a user created by tapping a
    toggle, so deleting them would take real settings with them.
    """
