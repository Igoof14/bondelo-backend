from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness. Deliberately does not touch the database: a Cloud Run startup
    probe must not fail because an external Postgres is briefly unavailable."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(session: DbSession) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
