"""
FlowForge — Health endpoints.

SRS §13.3 Health (root path, no auth, not rate limited):

GET /health
  Liveness: process is up.
  200 {"status": "ok"}
  No dependency checks.

GET /health/ready
  Readiness: checks PostgreSQL (SELECT 1), Redis (PING),
  and that Alembic migration revision equals head.
  200 {"status": "ready", "checks": {"database": "ok", "redis": "ok", "migrations": "ok"}}
  503 with the failing check named.
  Worker presence is informational only (never causes 503).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.core.redis import ping_redis
from app.db.session import ping_database

logger = get_logger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health", include_in_schema=True)
async def liveness() -> JSONResponse:
    """
    Liveness check — process is running.

    Never checks external dependencies; always returns 200 while the
    process is alive (SRS §13.3).
    """
    return JSONResponse(status_code=200, content={"status": "ok"})


@router.get("/health/ready", include_in_schema=True)
async def readiness() -> JSONResponse:
    """
    Readiness check — external dependencies are available.

    Checks: PostgreSQL connectivity, Redis connectivity, Alembic migration head.
    Returns 503 if any check fails, with the failing check identified.
    Worker count is informational only (SRS §13.3).
    """
    checks: dict[str, str] = {}
    all_ok = True

    # ── Database check ─────────────────────────────────────────────────────
    db_ok = ping_database()
    checks["database"] = "ok" if db_ok else "unavailable"
    if not db_ok:
        all_ok = False

    # ── Redis check ────────────────────────────────────────────────────────
    redis_ok = ping_redis()
    checks["redis"] = "ok" if redis_ok else "unavailable"
    if not redis_ok:
        all_ok = False

    # ── Migration check ────────────────────────────────────────────────────
    migration_ok = _check_migrations()
    checks["migrations"] = "ok" if migration_ok else "behind"
    if not migration_ok:
        all_ok = False

    if all_ok:
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "checks": checks},
        )
    else:
        logger.warning("health.ready_check_failed", checks=checks)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": checks},
        )


def _check_migrations() -> bool:
    """
    Verify that the current database migration head matches Alembic's head.

    Returns True if current == head, False otherwise or on error.
    """
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine

        from app.core.config import get_settings

        settings = get_settings()

        # Get current DB revision
        engine = create_engine(settings.database_url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

        # Get Alembic head revision
        from pathlib import Path

        ini_path = Path("alembic.ini")
        if not ini_path.exists():
            candidate = Path("backend") / "alembic.ini"
            if candidate.exists():
                ini_path = candidate
            else:
                ini_path = Path(__file__).resolve().parents[3] / "alembic.ini"

        alembic_cfg = Config(str(ini_path))
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()

        return current_rev == head_rev
    except Exception as exc:  # noqa: BLE001
        logger.warning("health.migration_check_failed", error=str(exc))
        return False
