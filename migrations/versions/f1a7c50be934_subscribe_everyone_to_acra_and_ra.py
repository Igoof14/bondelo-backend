"""subscribe every active user to the acra and ra agencies

`DEFAULT_AGENCIES` in notifications.models now lists four agencies instead of two, but
that constant only decides which rows `ensure_defaults` creates at registration — it
says nothing about users already in `bot_users`. Rating settings are one row per
(user, agency) and a missing row means "off", so without this revision everyone
registered before it would silently stay unsubscribed from ACRA and Expert RA.

Both audiences, same as e2f9a4c81d63: token holders are matched through `user_bonds`
and still need a row to be visible to rating-monitoring at all.

`DO NOTHING`: a user who already has a row for one of these codes made that choice in
the UI, and a backfill must not switch a section they turned off back on. That also
makes the revision safe to re-run.

Like e2f9a4c81d63, this one DOES run against production.

Revision ID: f1a7c50be934
Revises: e2f9a4c81d63
Create Date: 2026-08-04 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a7c50be934"
down_revision: str | Sequence[str] | None = "e2f9a4c81d63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Both audiences, as in e2f9a4c81d63 — no token predicate.
_ACTIVE = """
    SELECT telegram_id FROM bot_users WHERE is_active IS TRUE
"""

# The two codes this revision adds, inlined: a migration has to keep describing the
# schema as it was, even after `DEFAULT_AGENCIES` moves on. `nra`/`nkr` are not
# repeated here — e2f9a4c81d63 already covers them.
_NEW_AGENCIES = ("acra", "ra")


def upgrade() -> None:
    """Create switched-on rows for the two new agencies, for every active user."""
    agencies = ", ".join(f"('{agency}')" for agency in _NEW_AGENCIES)
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
