"""Alembic environment.

This service owns the schema of exactly one table, `bot_users` (see
:data:`OWNED_TABLES`). Everything else in `Base.metadata` is a read-only mapping of
someone else's table, and the database holds further tables we do not model at all
(`bot_events`, `*_alert_settings`, ...). Autogenerate is therefore restricted to a
whitelist — without it, it would propose dropping half the database.
"""

import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.base import Base

# Imported for the side effect of registering the models on Base.metadata.
from app.notifications import models as notification_models  # noqa: F401
from app.portfolio import models as portfolio_models  # noqa: F401
from app.users import models as users_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Tables whose schema this service manages. Autogenerate ignores everything else.
OWNED_TABLES = {
    "bot_users",
    "offer_alert_settings",
    "price_alert_settings",
    "rating_alert_settings",
    "fns_alert_settings",
}


def include_object(
    object_: Any, name: str | None, type_: str, _reflected: bool, _compare_to: Any
) -> bool:
    if type_ == "table":
        return name in OWNED_TABLES
    # Columns, indexes and constraints are filtered by the table they belong to.
    table = getattr(object_, "table", None)
    return getattr(table, "name", None) in OWNED_TABLES


def _url() -> str:
    # Taken from the app settings so the URL is not duplicated in alembic.ini.
    return str(get_settings().database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        version_table="alembic_version_bondelo_api",
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
        # Own version table: several services share this database, and if another
        # one adopts Alembic, the default `alembic_version` would collide.
        version_table="alembic_version_bondelo_api",
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _url()
    connectable = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
