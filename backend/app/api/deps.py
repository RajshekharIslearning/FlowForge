"""
FlowForge — FastAPI dependencies.

Phase 1 provides only:
  - get_db: database session per request
  - get_redis: Redis client (shared pool)

Authentication dependencies (get_current_user, require_admin) are
implemented in Phase 2.
"""

from __future__ import annotations

from collections.abc import Generator

from redis import Redis
from sqlalchemy.orm import Session

from app.core.redis import get_redis as _get_redis_client
from app.db.session import get_db as _get_db_session


def get_db() -> Generator[Session, None, None]:
    """Yield a database session per request (Phase 1 foundation)."""
    yield from _get_db_session()


def get_redis() -> Generator[Redis, None, None]:
    """Yield the shared Redis client."""
    yield from _get_redis_client()
