"""
FlowForge — Database session factory.

SRS §12.1 connection pool settings:
  API:    pool_size=10, max_overflow=10, pool_pre_ping=True, pool_recycle=1800
  Worker: pool_size=5,  max_overflow=5  (set via WORKER_DB_* env vars or defaults)

Session-per-request pattern: get_db() yields a Session that is closed after
the request completes. Services own transaction boundaries via session.begin();
repositories never commit.

SRS §20.1: DATABASE_URL must use postgresql+psycopg:// (psycopg3 driver).
SQLite is explicitly forbidden (SRS §19.1).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine = None
_SessionLocal = None


def _get_engine() -> Any:  # noqa: ANN401
    """
    Lazily create and return the shared SQLAlchemy engine.

    The engine is a singleton; it is initialised once with the settings from
    the environment. Tests may patch this by creating a new engine before
    calling get_db().
    """
    global _engine  # noqa: PLW0603
    if _engine is None:
        settings = get_settings()

        # Guard: reject SQLite (SRS §19.1, D-01)
        if "sqlite" in settings.database_url.lower():
            raise RuntimeError(
                "SQLite is explicitly forbidden by the SRS. "
                "Use PostgreSQL with DATABASE_URL=postgresql+psycopg://..."
            )

        _engine = create_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"connect_timeout": 3},
            # Echo SQL at DEBUG level only
            echo=False,
        )

        @event.listens_for(_engine, "connect")
        def _set_timezone(dbapi_conn: Any, connection_record: Any) -> None:  # noqa: ANN401
            """Ensure all connections use UTC timezone."""
            with dbapi_conn.cursor() as cursor:
                cursor.execute("SET TIME ZONE 'UTC'")

    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the shared sessionmaker, creating it if necessary."""
    global _SessionLocal  # noqa: PLW0603
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=_get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,  # Avoid lazy-load after commit
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency: yield a database Session per request.

    The session is always closed in the finally block, returning the
    connection to the pool. Services call session.begin() explicitly;
    this dependency does not begin a transaction itself.
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def ping_database() -> bool:
    """
    Check database connectivity. Returns True if reachable, False otherwise.
    Never raises; used by /health/ready.
    """
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("database.ping_failed", error=str(exc))
        return False
