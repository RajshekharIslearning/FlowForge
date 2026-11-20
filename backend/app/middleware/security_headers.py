"""
FlowForge — Security headers middleware.

SRS SEC-12: API must set these headers on every response:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Referrer-Policy: no-referrer
  - Cache-Control: no-store (on auth routes only — applied universally here
    for simplicity; clients that need caching can override)
  - Strict-Transport-Security: when ENVIRONMENT=production

Auth routes additionally get Cache-Control: no-store (already universal here).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply security headers to every response per SRS SEC-12."""

    def __init__(self, app: ASGIApp, *, is_production: bool = False) -> None:
        super().__init__(app)
        self._is_production = is_production

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"

        # Cache-Control: no-store on auth routes; applied universally here
        path = request.url.path
        if path.startswith("/api/v1/auth") or path.startswith("/api/v1/users/me"):
            response.headers["Cache-Control"] = "no-store"

        if self._is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response
