"""Initial schema migration covering all 13 FlowForge tables.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-10-31 09:00:00.000000

SRS §12.2 complete schema definition with UUID PKs, TIMESTAMPTZ, foreign keys,
constraints, expression indexes, and partial indexes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=10), server_default=sa.text("'user'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # ── 2. refresh_tokens ─────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["refresh_tokens.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"], unique=False)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)

    # ── 3. password_reset_tokens ──────────────────────────────────────────────
    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"], unique=False
    )

    # ── 4. workflows ──────────────────────────────────────────────────────────
    op.create_table(
        "workflows",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=10), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("trigger_type", sa.String(length=20), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('draft', 'active', 'inactive')", name="ck_workflows_status"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflows_owner_id", "workflows", ["owner_id"], unique=False)
    op.create_index(
        "ix_workflows_owner_name_unique",
        "workflows",
        ["owner_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_workflows_owner_status",
        "workflows",
        ["owner_id", "status"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_workflows_owner_updated_at",
        "workflows",
        ["owner_id", sa.text("updated_at DESC")],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── 5. workflow_versions ──────────────────────────────────────────────────
    op.create_table(
        "workflow_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "version", name="uq_wv_workflow_version"),
    )
    op.create_index(
        "ix_workflow_versions_workflow_id", "workflow_versions", ["workflow_id"], unique=False
    )

    # ── 6. workflow_executions ────────────────────────────────────────────────
    op.create_table(
        "workflow_executions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_type", sa.String(length=20), nullable=False),
        sa.Column(
            "trigger_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("retry_of_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_step_id", sa.String(length=40), nullable=True),
        sa.Column("failed_step_id", sa.String(length=40), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("recovery_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "cancel_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','waiting_retry','succeeded','failed','cancelled','timed_out')",
            name="ck_we_status",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('manual','schedule','webhook')", name="ck_we_trigger_type"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["retry_of_execution_id"], ["workflow_executions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_we_owner_created_at",
        "workflow_executions",
        ["owner_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_we_workflow_created_at",
        "workflow_executions",
        ["workflow_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_we_status_next_attempt",
        "workflow_executions",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_index("ix_we_workflow_id", "workflow_executions", ["workflow_id"], unique=False)
    op.create_index(
        "ix_we_queued_at_sweeper",
        "workflow_executions",
        ["queued_at"],
        unique=False,
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "ix_we_heartbeat_reaper",
        "workflow_executions",
        ["heartbeat_at"],
        unique=False,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "uq_we_workflow_idempotency_key",
        "workflow_executions",
        ["workflow_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # ── 7. step_executions ────────────────────────────────────────────────────
    op.create_table(
        "step_executions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(length=40), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=30), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("input_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("error_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','waiting_retry','succeeded','failed','timed_out','skipped','cancelled')",
            name="ck_se_status",
        ),
        sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_id", "step_id", name="uq_se_execution_step_id"),
    )
    op.create_index("ix_se_execution_id", "step_executions", ["execution_id"], unique=False)
    op.create_index(
        "ix_se_execution_step_index",
        "step_executions",
        ["execution_id", "step_index"],
        unique=False,
    )

    # ── 8. execution_logs ─────────────────────────────────────────────────────
    op.create_table(
        "execution_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "level IN ('DEBUG','INFO','WARNING','ERROR','CRITICAL')", name="ck_el_level"
        ),
        sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_execution_id"], ["step_executions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_el_execution_id", "execution_logs", ["execution_id", "id"], unique=False)
    op.create_index(
        "ix_execution_logs_execution_id", "execution_logs", ["execution_id"], unique=False
    )

    # ── 9. integrations ───────────────────────────────────────────────────────
    op.create_table(
        "integrations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("credential_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("allowed_hosts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('http_bearer', 'http_header_api_key', 'http_basic')",
            name="ck_integrations_type",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_integrations_owner_id", "integrations", ["owner_id"], unique=False)
    op.create_index(
        "uq_integrations_owner_name",
        "integrations",
        ["owner_id", sa.text("lower(name)")],
        unique=True,
    )

    # ── 10. schedules ─────────────────────────────────────────────────────────
    op.create_table(
        "schedules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("cron_expression", sa.String(length=100), nullable=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "timezone", sa.String(length=64), server_default=sa.text("'UTC'"), nullable=False
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("mode IN ('once', 'cron')", name="ck_schedules_mode"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id"),
    )
    op.create_index(
        "ix_schedules_next_run_at",
        "schedules",
        ["next_run_at"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )

    # ── 11. webhook_configs ───────────────────────────────────────────────────
    op.create_table(
        "webhook_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("secret_prefix", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id"),
    )

    # ── 12. audit_logs ────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(length=10), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=10), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("outcome IN ('success', 'failure')", name="ck_al_outcome"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_al_action_created_at",
        "audit_logs",
        ["action", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_al_actor_created_at",
        "audit_logs",
        ["actor_user_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index("ix_al_resource", "audit_logs", ["resource_type", "resource_id"], unique=False)
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"], unique=False)

    # ── 13. user_data_records ─────────────────────────────────────────────────
    op.create_table(
        "user_data_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection", sa.String(length=40), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dedupe_key", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_data_records_owner_id", "user_data_records", ["owner_id"], unique=False
    )
    op.create_index(
        "ix_udr_owner_collection_created",
        "user_data_records",
        ["owner_id", "collection", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_udr_owner_collection_dedupe",
        "user_data_records",
        ["owner_id", "collection", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )

    # ── 14. system_settings ───────────────────────────────────────────────────
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )

    # Seed required baseline system settings (SRS §12.2)
    system_settings_table = sa.table(
        "system_settings",
        sa.column("key", sa.String),
        sa.column("value", postgresql.JSONB),
    )
    op.bulk_insert(
        system_settings_table,
        [
            {"key": "registration_enabled", "value": True},
            {"key": "max_workflows_per_user", "value": 100},
            {"key": "max_active_workflows_per_user", "value": 25},
            {"key": "execution_retention_days", "value": 90},
            {"key": "audit_retention_days", "value": 365},
        ],
    )


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_index("uq_udr_owner_collection_dedupe", table_name="user_data_records")
    op.drop_index("ix_udr_owner_collection_created", table_name="user_data_records")
    op.drop_index("ix_user_data_records_owner_id", table_name="user_data_records")
    op.drop_table("user_data_records")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_index("ix_al_resource", table_name="audit_logs")
    op.drop_index("ix_al_actor_created_at", table_name="audit_logs")
    op.drop_index("ix_al_action_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("webhook_configs")
    op.drop_index("ix_schedules_next_run_at", table_name="schedules")
    op.drop_table("schedules")
    op.drop_index("uq_integrations_owner_name", table_name="integrations")
    op.drop_index("ix_integrations_owner_id", table_name="integrations")
    op.drop_table("integrations")
    op.drop_index("ix_execution_logs_execution_id", table_name="execution_logs")
    op.drop_index("ix_el_execution_id", table_name="execution_logs")
    op.drop_table("execution_logs")
    op.drop_index("ix_se_execution_step_index", table_name="step_executions")
    op.drop_index("ix_se_execution_id", table_name="step_executions")
    op.drop_table("step_executions")
    op.drop_index("uq_we_workflow_idempotency_key", table_name="workflow_executions")
    op.drop_index("ix_we_heartbeat_reaper", table_name="workflow_executions")
    op.drop_index("ix_we_queued_at_sweeper", table_name="workflow_executions")
    op.drop_index("ix_we_workflow_id", table_name="workflow_executions")
    op.drop_index("ix_we_status_next_attempt", table_name="workflow_executions")
    op.drop_index("ix_we_workflow_created_at", table_name="workflow_executions")
    op.drop_index("ix_we_owner_created_at", table_name="workflow_executions")
    op.drop_table("workflow_executions")
    op.drop_index("ix_workflow_versions_workflow_id", table_name="workflow_versions")
    op.drop_table("workflow_versions")
    op.drop_index("ix_workflows_owner_updated_at", table_name="workflows")
    op.drop_index("ix_workflows_owner_status", table_name="workflows")
    op.drop_index("ix_workflows_owner_name_unique", table_name="workflows")
    op.drop_index("ix_workflows_owner_id", table_name="workflows")
    op.drop_table("workflows")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
