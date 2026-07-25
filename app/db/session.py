from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    str(settings.database_url),
    echo=settings.db_echo,
    # Managed Postgres (Neon/Supabase) drops idle connections; without pre-ping the
    # first request after a quiet period fails.
    pool_pre_ping=True,
    pool_recycle=300,
    # Cloud Run scales to many instances against a finite connection limit.
    pool_size=5,
    max_overflow=0,
)

session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
