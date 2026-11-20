"""
FlowForge — Access logging middleware.

SRS §18.1: Every request completion is logged at INFO with:
  method, path template, status, duration, request_id.

Bodies, query parameters, and headers are NOT logged (SRS §18.3).
Path templates (not actual paths) are used to avoid logging UUIDs
and other PII embedded in paths.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.types import ASGIApp

from app.core.logging import get_logger
from app.middleware.request_id import get_request_id

logger = get_logger(__name__)


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log every request at INFO level with timing and request ID."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        # Resolve path template (e.g. /api/v1/workflows/{id}) if possible
        path_template = request.url.path
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                path_template = getattr(route, "path", path_template)
                break

        # Skip health endpoint access logs (too noisy in prod)
        if path_template in {"/health", "/health/ready"}:
            return response

        logger.info(
            "http.request",
            method=request.method,
            path=path_template,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=get_request_id(),
        )
        return response
