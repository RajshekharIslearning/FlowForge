"""
FlowForge — Request ID middleware.

SRS §18.1: RequestIDMiddleware accepts or generates X-Request-ID (UUID4),
stores it in a contextvars variable, and returns it in the response.

The request_id is accessible via get_request_id() throughout the request
lifecycle, including in services, repositories, and Celery tasks (passed
via execution.request_id).
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Context variable: accessible within the request's thread/coroutine
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_MAX_REQUEST_ID_LENGTH = 64


def get_request_id() -> str:
    """Return the current request's ID, or empty string if not in a request."""
    return _request_id_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware: assign or accept a request ID for every request.

    - Accepts `X-Request-ID` from the client (if ≤64 chars).
    - Generates a UUID4 if none is provided or if the provided one is too long.
    - Stores the ID in a ContextVar for use throughout the request.
    - Adds `X-Request-ID` to the response.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        if incoming and len(incoming) <= _MAX_REQUEST_ID_LENGTH:
            request_id = incoming
        else:
            request_id = str(uuid.uuid4())

        token = _request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response
