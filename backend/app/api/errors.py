"""
FlowForge — API exception handlers.

SRS §13.2: Every 4xx/5xx uses the error envelope:
  { "error": { "code": "...", "message": "...", "details": null, "request_id": "..." } }

Stack traces, SQL, file paths, and secrets are NEVER returned in responses
(SRS SEC-20). They are logged at ERROR level server-side only.

Handler registration: these handlers are registered in app/main.py via
`app.add_exception_handler(...)`.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.exceptions import HTTPException

from app.core.errors import (
    AccountLockedError,
    AppError,
    RateLimitedError,
)
from app.core.logging import get_logger
from app.middleware.request_id import get_request_id

logger = get_logger(__name__)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: list | None = None,
    headers: dict | None = None,
) -> JSONResponse:
    """Build the standard error envelope (SRS §13.2)."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": get_request_id() or None,
            }
        },
        headers=headers,
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle FlowForge AppError subclasses → standard error envelope."""
    headers: dict | None = None
    if isinstance(exc, RateLimitedError | AccountLockedError) and exc.retry_after is not None:
        headers = {"Retry-After": str(exc.retry_after)}

    return _error_response(
        status_code=exc.http_status,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        headers=headers,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle Pydantic/FastAPI validation errors → 422 with field-level details.

    SRS §13.2: details is a list of {loc, msg, code}.
    """
    details = []
    for error in exc.errors():
        details.append(
            {
                "loc": list(error.get("loc", [])),
                "msg": error.get("msg", ""),
                "code": "VALIDATION_ERROR",
            }
        )
    return _error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        details=details,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle Starlette HTTPException → standard envelope."""
    return _error_response(
        status_code=exc.status_code,
        code="HTTP_ERROR",
        message=str(exc.detail),
    )


async def db_error_handler(request: Request, exc: OperationalError | DBAPIError) -> JSONResponse:
    """
    Handle SQLAlchemy database errors.

    SRS §8.8: PostgreSQL unavailable → 503 DATABASE_UNAVAILABLE.
    Never leak SQL, table names, or connection strings.
    """
    logger.error(
        "database.error",
        request_id=get_request_id(),
        error_type=type(exc).__name__,
        # Deliberately NOT logging exc.args (may contain SQL/credentials)
    )
    return _error_response(
        status_code=503,
        code="DATABASE_UNAVAILABLE",
        message="Database is temporarily unavailable. Please try again.",
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unexpected exceptions.

    SRS SEC-20: Only a generic message is returned. The full stack trace
    is logged at ERROR level with the request ID for correlation.
    """
    logger.error(
        "unhandled.exception",
        request_id=get_request_id(),
        error_type=type(exc).__name__,
        exc_info=exc,
    )
    return _error_response(
        status_code=500,
        code="INTERNAL_ERROR",
        message="An internal server error occurred.",
    )
