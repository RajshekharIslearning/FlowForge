"""
FlowForge — Schedule and WebhookConfig models.

SRS §12.2 tables: schedules, webhook_configs.

Design:
- One schedule row per workflow (one-to-one).
- One webhook_config row per workflow (one-to-one).
- Webhook secret is Fernet-encrypted (must be recoverable for HMAC — SRS §9.2).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.workflow import Workflow


class Schedule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    DB-driven schedule record for scheduled workflow triggers.

    SRS §12.2 — schedules table.
    SRS D-12: Scheduling uses a DB-driven poller (scheduler.tick every 15s,
    FOR UPDATE SKIP LOCKED), not Celery's in-memory schedule.
    """

    __tablename__ = "schedules"
    __table_args__ = (
        # Enforce one schedule per workflow
        # (UNIQUE on workflow_id handles this)
        CheckConstraint("mode IN ('once', 'cron')", name="ck_schedules_mode"),
        Index(
            "ix_schedules_next_run_at",
            "next_run_at",
            postgresql_where=text("is_active = true"),
        ),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One schedule per workflow
    )
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    cron_expression: Mapped[str | None] = mapped_column(String(100), nullable=True)
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'UTC'"),
        default="UTC",
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        default=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    workflow: Mapped[Workflow] = relationship(
        "Workflow",
        back_populates="schedule",
    )


class WebhookConfig(UUIDPrimaryKeyMixin, Base):
    """
    Webhook configuration for a workflow.

    SRS §12.2 — webhook_configs table.
    The webhook secret is shown once (on creation/rotation) and stored
    Fernet-encrypted (must be recoverable for HMAC verification — SRS §9.2).
    The secret_prefix (first 6 chars) is stored plaintext for identification.
    """

    __tablename__ = "webhook_configs"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One webhook config per workflow
    )
    # Fernet-encrypted webhook secret (SRS SEC-14, §9.2)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # First 6 characters of the raw secret, stored plaintext for identification
    secret_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        default=True,
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )

    # ── Relationships ──────────────────────────────────────────────────────
    workflow: Mapped[Workflow] = relationship(
        "Workflow",
        back_populates="webhook_config",
    )
