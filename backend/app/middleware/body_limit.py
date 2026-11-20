"""
FlowForge — Body size limit middleware.

SRS §13.1: Global request body cap 1 MB; webhook 256 KB; workflow definition 128 KB.
The per-endpoint limits (256 KB, 128 KB) are enforced in route handlers.
This middleware enforces the global 1 MB cap as a hard backstop.

SRS NFR-06: Request bodies ≤1 MB.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

# 1 MB global cap (SRS §13.1)
_GLOBAL_BODY_LIMIT_BYTES = 1 * 1024 * 1024  # 1 MB


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Reject requests whose body exceeds the global cap.

    Returns 413 PAYLOAD_TOO_LARGE before the body is fully read.
    Per-endpoint stricter limits are applied inside route handlers.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int = _GLOBAL_BODY_LIMIT_BYTES) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                length = 0
            if length > self._max_bytes:
                limit_mb = self._max_bytes // (1024 * 1024)
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "PAYLOAD_TOO_LARGE",
                            "message": f"Request body exceeds the {limit_mb} MB limit.",
                            "details": None,
                            "request_id": None,
                        }
                    },
                )
        return await call_next(request)
