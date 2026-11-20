"""
FlowForge — SQLAlchemy declarative base and common model mixins.

SRS §12.1 conventions:
- Primary keys are UUID (uuid4, server default gen_random_uuid()).
- Timestamps are TIMESTAMPTZ stored in UTC.
- created_at defaults to now(); updated_at maintained by ORM onupdate.
- Enums are VARCHAR with CHECK constraints (simpler to migrate than native enums).
- Exception: execution_logs.id is BIGINT identity — handled in that model directly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Shared declarative base for all FlowForge ORM models.

    All models inherit from this base so that Alembic autogenerate can
    discover them by importing their modules in alembic/env.py.
    """

    def __init__(self, **kwargs: Any) -> None:
        cls_ = self.__class__
        if hasattr(cls_, "__table__"):
            for col in cls_.__table__.columns:
                if col.key not in kwargs and col.default is not None:
                    if col.default.is_scalar:
                        kwargs[col.key] = col.default.arg
                    elif col.default.is_callable:
                        kwargs[col.key] = col.default.arg(None)
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class UUIDPrimaryKeyMixin:
    """
    Adds a UUID primary key with a PostgreSQL server-side default.

    SRS §12.1: Primary keys are UUID (uuid4, server default gen_random_uuid()).
    gen_random_uuid() is built into PostgreSQL 13+; PG 16 is required.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid.uuid4,
    )


class TimestampMixin:
    """
    Adds created_at and updated_at TIMESTAMPTZ columns.

    SRS §12.1: All timestamps are TIMESTAMPTZ stored in UTC.
    updated_at is maintained by the ORM onupdate; it is NOT a DB trigger.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class CreatedAtMixin:
    """Adds only created_at (for append-only tables like audit_logs, tokens)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=lambda: datetime.now(UTC),
    )
