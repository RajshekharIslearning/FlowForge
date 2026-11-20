"""
FlowForge — Execution models.

SRS §12.2 tables: workflow_executions, step_executions, execution_logs.

Important implementation notes:
- execution_logs.id is BIGINT identity (not UUID) for ordered, cheap appends.
  This is an intentional exception to the UUID PK rule (SRS §12.1).
- All compare-and-set transitions use conditional UPDATE...WHERE status IN (...)
  to prevent races (SRS §8.3).
- step_executions rows are pre-created as 'pending' when the execution is
  created (SRS §12.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workflow import Workflow


class WorkflowExecution(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """
    One workflow execution instance.

    SRS §12.2 — workflow_executions table.
    SRS §8.3: Status transitions are conditional UPDATE...WHERE.
    SRS §8.7: Idempotency key uniqueness enforced via partial unique index.
    """

    __tablename__ = "workflow_executions"
    __table_args__ = (
        # For user's execution list view
        Index("ix_we_owner_created_at", "owner_id", text("created_at DESC")),
        # For workflow-specific execution list
        Index("ix_we_workflow_created_at", "workflow_id", text("created_at DESC")),
        # For maintenance tasks (reaper, scheduler)
        Index("ix_we_status_next_attempt", "status", "next_attempt_at"),
        # Sweeper: find queued executions not yet enqueued
        Index(
            "ix_we_queued_at_sweeper",
            "queued_at",
            postgresql_where=text("status = 'queued'"),
        ),
        # Reaper: find stale running executions
        Index(
            "ix_we_heartbeat_reaper",
            "heartbeat_at",
            postgresql_where=text("status = 'running'"),
        ),
        # Idempotency key uniqueness per workflow (SRS §8.7)
        UniqueConstraint(
            "workflow_id",
            "idempotency_key",
            name="uq_we_workflow_idempotency_key",
            # Partial: only when idempotency_key IS NOT NULL
            # NOTE: PostgreSQL allows NULL in unique; this constraint covers
            # only non-NULL values by convention. A partial unique index would
            # be better; added in migration explicitly.
        ),
        CheckConstraint(
            "status IN ('queued','running','waiting_retry','succeeded',"
            "'failed','cancelled','timed_out')",
            name="ck_we_status",
        ),
        CheckConstraint(
            "trigger_type IN ('manual','schedule','webhook')",
            name="ck_we_trigger_type",
        ),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        # Denormalised for authz + filtering (SRS §12.3)
    )
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'"),
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'queued'"),
        default="queued",
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retry_of_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_step_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    failed_step_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        default=0,
    )
    recovery_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        default=0,
    )
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Timing columns (SRS §12.2)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────
    workflow: Mapped[Workflow] = relationship(
        "Workflow",
        back_populates="executions",
    )
    owner: Mapped[User] = relationship(
        "User",
        foreign_keys=[owner_id],
    )
    triggered_by_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[triggered_by_user_id],
    )
    steps: Mapped[list[StepExecution]] = relationship(
        "StepExecution",
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="StepExecution.step_index",
    )
    logs: Mapped[list[ExecutionLog]] = relationship(
        "ExecutionLog",
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="ExecutionLog.id",
    )
    retried_from: Mapped[WorkflowExecution | None] = relationship(
        "WorkflowExecution",
        foreign_keys=[retry_of_execution_id],
        remote_side="WorkflowExecution.id",
    )


class StepExecution(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """
    Per-step execution state within a workflow execution.

    SRS §12.2 — step_executions table.
    Rows are pre-created as 'pending' when the execution is created.
    The unique (execution_id, step_id) constraint serialises state updates.
    """

    __tablename__ = "step_executions"
    __table_args__ = (
        UniqueConstraint("execution_id", "step_id", name="uq_step_executions_exec_step"),
        Index("ix_se_execution_step_index", "execution_id", "step_index"),
        CheckConstraint(
            "status IN ('pending','running','waiting_retry','succeeded',"
            "'failed','timed_out','skipped','cancelled')",
            name="ck_se_status",
        ),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[str] = mapped_column(String(40), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
        default="pending",
    )
    # retry_count = number of additional attempts; total attempts = retry_count + 1
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        default=0,
    )
    # Metadata about the input (no payloads; SRS §12.2)
    input_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Step output (stored raw; redacted in API responses — SRS §8.2)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Metadata about the output (sizes, status codes, key names; no values)
    output_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────
    execution: Mapped[WorkflowExecution] = relationship(
        "WorkflowExecution",
        back_populates="steps",
    )
    logs: Mapped[list[ExecutionLog]] = relationship(
        "ExecutionLog",
        back_populates="step_execution",
    )


class ExecutionLog(Base):
    """
    Ordered execution log entry.

    SRS §12.2 — execution_logs table.
    INTENTIONAL EXCEPTION: id is BIGINT identity (not UUID) for ordered,
    cheap appends. This is the only table in FlowForge with a non-UUID PK.
    See IMPLEMENTATION_DECISIONS.md.
    """

    __tablename__ = "execution_logs"
    __table_args__ = (
        Index("ix_el_execution_id", "execution_id", "id"),
        CheckConstraint(
            "level IN ('DEBUG','INFO','WARNING','ERROR','CRITICAL')",
            name="ck_el_level",
        ),
    )

    # BIGINT GENERATED BY DEFAULT AS IDENTITY (SRS §12.2)
    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("step_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Context contains metadata only (no payloads/secrets) SRS §18.3
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )

    # ── Relationships ──────────────────────────────────────────────────────
    execution: Mapped[WorkflowExecution] = relationship(
        "WorkflowExecution",
        back_populates="logs",
    )
    step_execution: Mapped[StepExecution | None] = relationship(
        "StepExecution",
        back_populates="logs",
    )
