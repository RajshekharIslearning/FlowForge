"""
FlowForge models package.

Imports all model modules so that Alembic autogenerate can discover
every table by importing this package in alembic/env.py.

IMPORTANT: Every new model file MUST be imported here.
"""

from app.models.data_record import UserDataRecord
from app.models.execution import ExecutionLog, StepExecution, WorkflowExecution
from app.models.integration import Integration
from app.models.system import AuditLog, SystemSetting
from app.models.trigger import Schedule, WebhookConfig
from app.models.user import PasswordResetToken, RefreshToken, User
from app.models.workflow import Workflow, WorkflowVersion

__all__ = [
    "User",
    "RefreshToken",
    "PasswordResetToken",
    "Workflow",
    "WorkflowVersion",
    "WorkflowExecution",
    "StepExecution",
    "ExecutionLog",
    "Integration",
    "Schedule",
    "WebhookConfig",
    "UserDataRecord",
    "SystemSetting",
    "AuditLog",
]
