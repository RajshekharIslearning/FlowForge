"""
FlowForge — Database seed script.

Seeds initial platform settings into `system_settings` idempotently.
SRS §12.2:
  - registration_enabled = true
  - max_workflows_per_user = 100
  - max_active_workflows_per_user = 25
  - execution_retention_days = 90
  - audit_retention_days = 365

Executed by the migrate service: `alembic upgrade head && python -m app.scripts.seed`.
Safe to run repeatedly; uses INSERT ... ON CONFLICT (key) DO NOTHING.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert

from app.core.logging import configure_logging, get_logger
from app.db.session import get_session_factory
from app.models.system import SystemSetting

logger = get_logger(__name__)

# Default system settings per SRS §12.2
DEFAULT_SETTINGS: dict[str, Any] = {
    "registration_enabled": True,
    "max_workflows_per_user": 100,
    "max_active_workflows_per_user": 25,
    "execution_retention_days": 90,
    "audit_retention_days": 365,
}


def seed_system_settings() -> None:
    """Insert default system settings if they do not already exist."""
    session_factory = get_session_factory()
    with session_factory() as session:
        for key, value in DEFAULT_SETTINGS.items():
            stmt = (
                insert(SystemSetting)
                .values(key=key, value={"value": value})
                .on_conflict_do_nothing(index_elements=["key"])
            )
            session.execute(stmt)
        session.commit()
        logger.info("seed.system_settings_completed", count=len(DEFAULT_SETTINGS))


def main() -> None:
    """Entry point for python -m app.scripts.seed."""
    configure_logging()
    logger.info("seed.starting")
    seed_system_settings()
    logger.info("seed.finished")


if __name__ == "__main__":
    main()
