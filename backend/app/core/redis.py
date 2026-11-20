"""
FlowForge — Redis client pool.

The Redis client is constructed once and shared across the application.
SRS §11.4 and §8.8 define the fail-open policy: when Redis is unavailable,
operations that depend on it (rate limiting, token denylist, webhook dedupe)
MUST log a WARNING and continue; they must never cause the API to return 5xx
when the core operation (e.g. creating an execution) would otherwise succeed.

The client uses db 1 by default (REDIS_URL). Celery uses db 0 (CELERY_BROKER_URL).
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from redis import Redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    """
    Return a cached Redis connection pool.

    The pool is not created until the first call. In tests, call
    ``get_redis_client.cache_clear()`` after patching settings.
    """
    settings = get_settings()
    client: Redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
        retry_on_timeout=True,
    )
    return client


def ping_redis() -> bool:
    """
    Check Redis connectivity. Returns True if reachable, False otherwise.
    Never raises; used by /health/ready.
    """
    try:
        client = get_redis_client()
        return bool(client.ping())
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis.ping_failed", error=str(exc))
        return False


def get_redis() -> Generator[Redis, None, None]:
    """
    FastAPI dependency: yield the shared Redis client.

    Does not manage the lifecycle per-request because Redis uses a
    connection pool (not individual connections per request).
    """
    yield get_redis_client()
