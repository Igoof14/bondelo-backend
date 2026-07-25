import logging
import sys
from typing import Any

import structlog

from app.core.config import Settings

# Cloud Logging picks up these keys from structured JSON on stdout.
_SEVERITY_KEY = "severity"
_MESSAGE_KEY = "message"


def _rename_for_cloud_logging(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    if "level" in event_dict:
        event_dict[_SEVERITY_KEY] = event_dict.pop("level").upper()
    if "event" in event_dict:
        event_dict[_MESSAGE_KEY] = event_dict.pop("event")
    return event_dict


def configure_logging(settings: Settings) -> None:
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.is_prod:
        renderers: list[structlog.types.Processor] = [
            _rename_for_cloud_logging,
            structlog.processors.JSONRenderer(),
        ]
    else:
        renderers = [structlog.dev.ConsoleRenderer()]

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy) through the same pipeline.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *renderers],
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.DEBUG if settings.debug else logging.INFO)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
