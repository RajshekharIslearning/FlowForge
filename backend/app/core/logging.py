"""
FlowForge — Structured logging configuration.

Uses structlog for JSON-structured logs (production) or coloured console
output (development). Every log line includes: timestamp, level, event,
logger, service name, and request_id from context when bound.

SRS §18.1–18.3: logs must never contain passwords, tokens, API keys,
integration credentials, webhook secrets, request/response bodies, or
step outputs. A redaction processor is applied as a safety net.

Usage
-----
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("execution.started", execution_id=str(ex_id))
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Keys that must never appear in log output (SRS §18.3)
# ---------------------------------------------------------------------------

_REDACTED_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "hashed_password",
        "token",
        "access_token",
        "refresh_token",
        "reset_token",
        "api_key",
        "apikey",
        "secret",
        "secret_key",
        "webhook_secret",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "encrypted",
    }
)


def _redact_sensitive(
    logger: Any,  # noqa: ANN401
    method: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Structlog processor: replace values whose keys match _REDACTED_KEYS
    with '***'. Applied recursively one level deep (top-level keys only;
    nested structures in payloads/bodies should never be logged at all).

    SRS §18.3: This is a safety net; the real rule is not to pass such
    values into the logger in the first place.
    """
    for key in list(event_dict.keys()):
        if key.lower() in _REDACTED_KEYS:
            event_dict[key] = "***"
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog and the stdlib logging bridge.

    Call once at application startup (app/main.py lifespan).
    """
    settings = get_settings()

    # Shared processors for all renderers
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact_sensitive,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "console":
        # Human-readable coloured output for development
        renderer: Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON for production / structured log aggregation
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.log_level)

    # Quieten noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "celery"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger with the given name."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
