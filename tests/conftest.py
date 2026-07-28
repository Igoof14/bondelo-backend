"""Shared fixtures.

The tests run against a real Postgres: the queries rely on `ON CONFLICT`, `xmax` and
`json_agg`, so sqlite is not a substitute. Bring the database up with
`docker compose -f docker-compose.test.yml up -d`.
"""

import os
from collections.abc import AsyncIterator

# App settings are read at import time, so the URL is overridden before those imports.
DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/bondelo_test"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.session import get_session  # noqa: E402
from app.main import create_app  # noqa: E402

# Tables wiped between tests: exactly the ones the tests write to.
_TABLES = (
    "bot_users",
    "offer_alert_settings",
    "price_alert_settings",
    "rating_alert_settings",
    "fns_alert_settings",
)


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Migrate the test database once per session."""
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        for table in _TABLES:
            await conn.execute(text(f"TRUNCATE {table} RESTART IDENTITY CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """HTTP client over the ASGI app, wired to the fixture's session."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
