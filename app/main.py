import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.v1 import health
from app.core.config import Settings, get_settings
from app.core.context import RequestContextMiddleware
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import engine

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings)
    # The SDK reads this from the environment when it builds the channel, so the setting
    # has to travel back out — otherwise a value from `.env` would never reach it.
    os.environ["SSL_TBANK_VERIFY"] = str(settings.ssl_tbank_verify).lower()
    # The broker endpoint is logged so a misconfigured deployment is visible at startup —
    # a wrong target only surfaces later, as an opaque connection failure.
    log.info("app.startup", env=settings.app_env, tinvest_target=settings.tinvest_grpc_target)
    yield
    await engine.dispose()
    log.info("app.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Bondelo API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
    )
    app.state.settings = settings

    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    # Health lives at the root so Cloud Run probes do not depend on the API version.
    app.include_router(health.router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
