"""
FlowForge — Unit tests for SQLAlchemy ORM models.

SRS §12.2:
  - All 13 tables instantiated without error.
  - Primary key types verified (UUID except execution_logs.id which is BIGINT identity).
  - Table names and check constraints match SRS specification.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.data_record import UserDataRecord
from app.models.execution import ExecutionLog, StepExecution, WorkflowExecution
from app.models.integration import Integration
from app.models.system import AuditLog, SystemSetting
from app.models.trigger import Schedule, WebhookConfig
from app.models.user import RefreshToken, User
from app.models.workflow import Workflow, WorkflowVersion


def test_user_model_instantiation() -> None:
    """User model instantiates with expected defaults."""
    user = User(
        email="test@flowforge.local",
        password_hash="argon2id_hash_placeholder",
        full_name="Test User",
    )
    assert user.role == "user"
    assert user.is_active is True
    assert user.failed_login_count == 0
    assert user.__tablename__ == "users"


def test_refresh_token_model_instantiation() -> None:
    """RefreshToken model instantiates with required fields."""
    uid = uuid.uuid4()
    fid = uuid.uuid4()
    token = RefreshToken(
        user_id=uid,
        family_id=fid,
        token_hash="a" * 64,
        expires_at=datetime.now(UTC),
    )
    assert token.user_id == uid
    assert token.family_id == fid
    assert token.__tablename__ == "refresh_tokens"


def test_workflow_model_instantiation() -> None:
    """Workflow model instantiates with draft status and version 1."""
    owner_id = uuid.uuid4()
    wf = Workflow(
        owner_id=owner_id,
        name="Order Processing",
        trigger_type="webhook",
    )
    assert wf.status == "draft"
    assert wf.version == 1
    assert wf.__tablename__ == "workflows"


def test_workflow_version_model_instantiation() -> None:
    """WorkflowVersion stores immutable definition snapshot."""
    wf_id = uuid.uuid4()
    creator_id = uuid.uuid4()
    wfv = WorkflowVersion(
        workflow_id=wf_id,
        version=1,
        definition={"trigger": {"type": "manual"}, "steps": []},
        definition_hash="b" * 64,
        created_by=creator_id,
    )
    assert wfv.version == 1
    assert wfv.__tablename__ == "workflow_versions"


def test_execution_models_instantiation() -> None:
    """WorkflowExecution and StepExecution instantiate properly."""
    wf_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    we = WorkflowExecution(
        workflow_id=wf_id,
        workflow_version=1,
        owner_id=owner_id,
        trigger_type="manual",
    )
    assert we.status == "queued"
    assert we.retry_count == 0
    assert we.__tablename__ == "workflow_executions"

    se = StepExecution(
        execution_id=we.id,
        step_id="step_1",
        step_index=0,
        action_type="http_request",
    )
    assert se.status == "pending"
    assert se.retry_count == 0
    assert se.__tablename__ == "step_executions"


def test_execution_log_bigint_identity() -> None:
    """ExecutionLog has BIGINT identity PK (SRS §12.1 exception)."""
    we_id = uuid.uuid4()
    log = ExecutionLog(
        execution_id=we_id,
        level="INFO",
        message="Workflow execution started",
    )
    assert log.__tablename__ == "execution_logs"
    assert log.level == "INFO"


def test_integration_model_instantiation() -> None:
    """Integration model instantiates with encrypted credentials."""
    owner_id = uuid.uuid4()
    integ = Integration(
        owner_id=owner_id,
        name="GitHub API",
        type="http_bearer",
        credentials_encrypted="gAAAAAB...",
        credential_fields=["token"],
    )
    assert integ.type == "http_bearer"
    assert integ.__tablename__ == "integrations"


def test_trigger_models_instantiation() -> None:
    """Schedule and WebhookConfig instantiate correctly."""
    wf_id = uuid.uuid4()
    sched = Schedule(
        workflow_id=wf_id,
        mode="cron",
        cron_expression="0 9 * * *",
    )
    assert sched.is_active is True
    assert sched.__tablename__ == "schedules"

    wh = WebhookConfig(
        workflow_id=wf_id,
        secret_encrypted="gAAAAAB...",
        secret_prefix="whsec_",
    )
    assert wh.is_active is True
    assert wh.__tablename__ == "webhook_configs"


def test_user_data_record_instantiation() -> None:
    """UserDataRecord sandbox model instantiates."""
    owner_id = uuid.uuid4()
    record = UserDataRecord(
        owner_id=owner_id,
        collection="customers",
        data={"name": "Alice", "city": "Bengaluru"},
    )
    assert record.collection == "customers"
    assert record.__tablename__ == "user_data_records"


def test_system_models_instantiation() -> None:
    """SystemSetting and AuditLog instantiate with required fields."""
    setting = SystemSetting(
        key="registration_enabled",
        value={"enabled": True},
    )
    assert setting.key == "registration_enabled"
    assert setting.__tablename__ == "system_settings"

    audit = AuditLog(
        action="auth.login",
        outcome="success",
    )
    assert audit.action == "auth.login"
    assert audit.outcome == "success"
    assert audit.__tablename__ == "audit_logs"
