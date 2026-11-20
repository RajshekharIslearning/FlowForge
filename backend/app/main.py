"""
FlowForge — FastAPI application factory and entry point.

SRS §13: REST API conventions, base path /api/v1, JSON only, request_id,
security headers, error envelope, health endpoints, OpenAPI documentation.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.exceptions import HTTPException

from app.api.errors import (
    app_error_handler,
    db_error_handler,
    http_exception_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.middleware.access_log import AccessLogMiddleware
from app.middleware.body_limit import BodySizeLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Configures logging, validates configuration, and cleans up resources
    on shutdown.
    """
    configure_logging()
    settings = get_settings()
    logger.info(
        "app.startup",
        environment=settings.environment,
        log_format=settings.log_format,
        log_level=settings.log_level,
        version="1.0.0",
    )
    yield
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    """
    FastAPI application factory.

    Instantiates and configures the FastAPI app with middleware,
    routers, exception handlers, and lifespan management.
    """
    settings = get_settings()

    app = FastAPI(
        title="FlowForge API",
        description="A Python-based workflow automation and background job processing platform",
        version="1.0.0",
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
        lifespan=lifespan,
    )

    # ── Exception handlers (SRS §13.2) ────────────────────────────────────
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(OperationalError, db_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DBAPIError, db_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    # ── Middleware stack (executed in reverse order of addition) ──────────
    # 5. Access logging (innermost)
    app.add_middleware(AccessLogMiddleware)
    # 4. Global body size limit (1 MB backstop)
    app.add_middleware(BodySizeLimitMiddleware)
    # 3. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    # 2. Security headers (SRS SEC-12)
    app.add_middleware(
        SecurityHeadersMiddleware,
        is_production=settings.is_production,
    )
    # 1. Request ID (outermost: generates/binds request_id first)
    app.add_middleware(RequestIDMiddleware)

    # ── Routers ───────────────────────────────────────────────────────────
    # Root path health checks: /health (liveness), /health/ready (readiness)
    app.include_router(health_router)
    # Also mount under /api/v1 for API prefix consistency
    app.include_router(health_router, prefix="/api/v1")

    return app


app = create_app()
