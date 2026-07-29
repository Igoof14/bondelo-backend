"""add disclosure_alert_settings

The fifth settings table: subscriptions to issuer disclosure alerts, produced by
disclosure-parsing-worker (bankruptcy filings, seizures, missed coupons). Unlike the
other sections it carries a per-user severity floor, `min_risk_level`, so a user can
keep the section on but only hear about the serious events.

The table is new, so every existing user is backfilled — both audiences, not just the
tokenless one b4e1c7f20a91 dealt with: holders are matched through `user_bonds` and
still need a row to be visible to the worker at all.

`DO NOTHING`, as always: re-running must not resurrect a section someone turned off.

Revision ID: c7f3a1d95e02
Revises: b4e1c7f20a91
Create Date: 2026-07-29 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7f3a1d95e02"
down_revision: str | Sequence[str] | None = "b4e1c7f20a91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Value from notifications.models, inlined: a migration has to keep describing the
# schema as it was, even after the constant moves on.
_DEFAULT_MIN_RISK_LEVEL = "low"


def upgrade() -> None:
    """Create the table and switch it on for everyone already registered."""
    op.create_table(
        "disclosure_alert_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("alerts_enabled", sa.Boolean(), nullable=False),
        sa.Column("min_risk_level", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disclosure_alert_settings")),
    )
    op.create_index(
        op.f("ix_disclosure_alert_settings_telegram_id"),
        "disclosure_alert_settings",
        ["telegram_id"],
        unique=True,
    )

    # The default is declared Python-side on the model, so the column has no DDL
    # default and raw SQL has to spell it out.
    op.execute(
        f"""
        INSERT INTO disclosure_alert_settings
            (telegram_id, alerts_enabled, min_risk_level, created_at)
        SELECT telegram_id, TRUE, '{_DEFAULT_MIN_RISK_LEVEL}', now()
        FROM bot_users
        WHERE is_active IS TRUE
        ON CONFLICT (telegram_id) DO NOTHING
        """
    )


def downgrade() -> None:
    """Drop the table — nothing else references it."""
    op.drop_index(
        op.f("ix_disclosure_alert_settings_telegram_id"),
        table_name="disclosure_alert_settings",
    )
    op.drop_table("disclosure_alert_settings")
