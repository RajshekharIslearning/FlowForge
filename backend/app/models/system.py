"""
FlowForge — SystemSetting and AuditLog models.

SRS §12.2 tables: system_settings, audit_logs.

system_settings:
  - Key-value store for platform configuration.
  - Seeded by app/scripts/seed.py (not by migration).
  - Updated only via /admin/settings endpoint.

audit_logs:
  - Append-only audit trail.
  - Written in the same transaction as the state change (SRS §18.4).
  - Failure policy: if audit insert fails, the whole transaction fails.
  - Retention: rows older than audit_retention_days are deleted nightly.
  - Metadata contains IDs and non-sensitive attributes ONLY (SRS §18.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class SystemSetting(Base):
    """
    Platform configuration key-value store.

    SRS §12.2 — system_settings table.
    PK is VARCHAR key (not UUID). Seeded with initial values in seed.py.
    """

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        onupdate=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )

    # ── Relationships ──────────────────────────────────────────────────────
    updated_by_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[updated_by],
    )


class AuditLog(Base):
    """
    Append-only audit log entry.

    SRS §12.2 — audit_logs table.
    SRS §18.4: Written in the same transaction as the change.
    PK is UUID (unlike execution_logs which uses BIGINT identity).
    No code path updates or deletes rows except the retention cleanup task.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_al_actor_created_at", "actor_user_id", text("created_at DESC")),
        Index("ix_al_action_created_at", "action", text("created_at DESC")),
        Index("ix_al_resource", "resource_type", "resource_id"),
        CheckConstraint("outcome IN ('success', 'failure')", name="ck_al_outcome"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid.uuid4,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_role: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Action name e.g. 'auth.login', 'workflow.create' (SRS §18.4)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Metadata: IDs and non-sensitive attributes only (SRS §18.3)
    # Python attribute named metadata_ to avoid collision with Base.metadata
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'"),
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )

    # ── Relationships ──────────────────────────────────────────────────────
    actor: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[actor_user_id],
    )
