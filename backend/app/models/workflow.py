"""
FlowForge — Workflow and WorkflowVersion models.

SRS §12.2 tables: workflows, workflow_versions.

Design decision D-03: Workflow definitions (trigger + steps) are stored as an
immutable JSONB snapshot per version in workflow_versions. There is NO
workflow_steps table. Executions pin to a version snapshot.

The `trigger_type` column on workflows is a denormalisation of the current
definition for efficient filtering without JSONB parsing (SRS §12.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.execution import WorkflowExecution
    from app.models.trigger import Schedule, WebhookConfig
    from app.models.user import User


class Workflow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Workflow metadata record.

    SRS §12.2 — workflows table.
    Status lifecycle: draft → active ⇄ inactive; any → deleted (soft delete).
    """

    __tablename__ = "workflows"
    __table_args__ = (
        # SRS §12.2: case-insensitive unique name per owner (excluding soft-deleted)
        Index(
            "ix_workflows_owner_name_unique",
            "owner_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # For efficient listing/filtering
        Index(
            "ix_workflows_owner_status",
            "owner_id",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # For default sort order
        Index(
            "ix_workflows_owner_updated_at",
            "owner_id",
            text("updated_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'inactive')",
            name="ck_workflows_status",
        ),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        # Max 1000 chars enforced at application layer (SRS §7.2.1)
    )
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("'draft'"),
        default="draft",
    )
    # Current version number (incremented on definition change — SRS FR-WF-02)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
        default=1,
    )
    # Denormalised from current definition for filtering (SRS §12.3)
    trigger_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    owner: Mapped[User] = relationship(
        "User",
        foreign_keys=[owner_id],
    )
    versions: Mapped[list[WorkflowVersion]] = relationship(
        "WorkflowVersion",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowVersion.version",
    )
    executions: Mapped[list[WorkflowExecution]] = relationship(
        "WorkflowExecution",
        back_populates="workflow",
    )
    schedule: Mapped[Schedule | None] = relationship(
        "Schedule",
        back_populates="workflow",
        uselist=False,
        cascade="all, delete-orphan",
    )
    webhook_config: Mapped[WebhookConfig | None] = relationship(
        "WebhookConfig",
        back_populates="workflow",
        uselist=False,
        cascade="all, delete-orphan",
    )


class WorkflowVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """
    Immutable JSONB snapshot of a workflow definition at a specific version.

    SRS §12.2 — workflow_versions table.
    SRS D-03: No workflow_steps table; snapshots are the version record.
    Executions reference workflow_version (int) and load this row for the
    definition to run.
    """

    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_wf_version"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Full workflow definition JSON (trigger + variables + settings + steps)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # SHA-256 hex of the canonical JSON serialisation — for fast equality check
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="versions")
    creator: Mapped[User] = relationship(
        "User",
        foreign_keys=[created_by],
    )
