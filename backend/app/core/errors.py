"""
FlowForge — Error classes.

A single AppError hierarchy maps to HTTP status codes and error codes.
Exception handlers in app/api/errors.py convert these into the standard
error envelope defined in SRS §13.2.

Error codes that are raised during workflow execution (e.g. RETRIES_EXHAUSTED,
STEP_TIMEOUT) are NOT API errors — they are stored on execution/step rows
and returned as data through the execution detail endpoints.
"""

from __future__ import annotations


class AppError(Exception):
    """
    Base class for all FlowForge application errors.

    Attributes
    ----------
    code:        Machine-readable error code (from SRS §13.2).
    http_status: HTTP status code to return.
    message:     Human-readable message (stable, safe to show to clients).
    details:     Optional structured detail payload (for 422 field errors).
    """

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "An internal error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[dict] | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.details = details
        super().__init__(self.message)


# ── 400 Bad Request ────────────────────────────────────────────────────────────


class BadRequestError(AppError):
    code = "BAD_REQUEST"
    http_status = 400
    message = "Bad request."


class MalformedWebhookError(AppError):
    code = "MALFORMED_WEBHOOK"
    http_status = 400
    message = "Webhook body is malformed or not valid JSON."


class ResetTokenInvalidError(AppError):
    code = "RESET_TOKEN_INVALID"
    http_status = 400
    message = "Password reset token is invalid or expired."


# ── 401 Unauthorized ───────────────────────────────────────────────────────────


class InvalidCredentialsError(AppError):
    code = "INVALID_CREDENTIALS"
    http_status = 401
    message = "Invalid credentials."


class TokenExpiredError(AppError):
    code = "TOKEN_EXPIRED"
    http_status = 401
    message = "Access token has expired."


class TokenInvalidError(AppError):
    code = "TOKEN_INVALID"
    http_status = 401
    message = "Access token is invalid."


class TokenRevokedError(AppError):
    code = "TOKEN_REVOKED"
    http_status = 401
    message = "Access token has been revoked."


class RefreshTokenInvalidError(AppError):
    code = "REFRESH_TOKEN_INVALID"
    http_status = 401
    message = "Refresh token is invalid or unknown."


class RefreshTokenExpiredError(AppError):
    code = "REFRESH_TOKEN_EXPIRED"
    http_status = 401
    message = "Refresh token has expired."


class RefreshTokenReusedError(AppError):
    code = "REFRESH_TOKEN_REUSED"
    http_status = 401
    message = "Refresh token has already been used. All sessions have been revoked."


class InvalidSignatureError(AppError):
    code = "INVALID_SIGNATURE"
    http_status = 401
    message = "Webhook signature is invalid."


class WebhookTimestampInvalidError(AppError):
    code = "WEBHOOK_TIMESTAMP_INVALID"
    http_status = 401
    message = "Webhook timestamp is outside the acceptable window."


# ── 403 Forbidden ──────────────────────────────────────────────────────────────


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    http_status = 403
    message = "You do not have permission to perform this action."


class AccountDisabledError(AppError):
    code = "ACCOUNT_DISABLED"
    http_status = 403
    message = "This account has been disabled."


class RegistrationDisabledError(AppError):
    code = "REGISTRATION_DISABLED"
    http_status = 403
    message = "New user registration is currently disabled."


# ── 404 Not Found ─────────────────────────────────────────────────────────────


class NotFoundError(AppError):
    """Base for all 404 errors — cross-user access MUST return 404 (SRS §6.1)."""

    code = "NOT_FOUND"
    http_status = 404
    message = "Resource was not found."


class WorkflowNotFoundError(NotFoundError):
    code = "WORKFLOW_NOT_FOUND"
    message = "Workflow was not found."


class ExecutionNotFoundError(NotFoundError):
    code = "EXECUTION_NOT_FOUND"
    message = "Execution was not found."


class IntegrationNotFoundError(NotFoundError):
    code = "INTEGRATION_NOT_FOUND"
    message = "Integration was not found."


class UserNotFoundError(NotFoundError):
    code = "USER_NOT_FOUND"
    message = "User was not found."


class WebhookNotFoundError(NotFoundError):
    code = "WEBHOOK_NOT_FOUND"
    message = "Webhook configuration was not found."


class VersionNotFoundError(NotFoundError):
    code = "VERSION_NOT_FOUND"
    message = "Workflow version was not found."


# ── 409 Conflict ──────────────────────────────────────────────────────────────


class ConflictError(AppError):
    code = "CONFLICT"
    http_status = 409
    message = "A conflict occurred."


class EmailAlreadyRegisteredError(ConflictError):
    code = "EMAIL_ALREADY_REGISTERED"
    message = "An account with this email address already exists."


class WorkflowNameExistsError(ConflictError):
    code = "WORKFLOW_NAME_EXISTS"
    message = "A workflow with this name already exists."


class WorkflowNotActiveError(ConflictError):
    code = "WORKFLOW_NOT_ACTIVE"
    message = "Workflow must be active to execute."


class WorkflowLimitReachedError(ConflictError):
    code = "WORKFLOW_LIMIT_REACHED"
    message = "Workflow limit reached for this account."


class VersionConflictError(ConflictError):
    code = "VERSION_CONFLICT"
    message = "Optimistic concurrency conflict: the workflow was modified by another request."


class IntegrationInUseError(ConflictError):
    code = "INTEGRATION_IN_USE"
    message = "Integration is referenced by one or more active workflows."


class IntegrationNameExistsError(ConflictError):
    code = "INTEGRATION_NAME_EXISTS"
    message = "An integration with this name already exists."


class ExecutionNotRetryableError(ConflictError):
    code = "EXECUTION_NOT_RETRYABLE"
    message = "Only failed or timed_out executions can be retried."


class ExecutionAlreadyFinishedError(ConflictError):
    code = "EXECUTION_ALREADY_FINISHED"
    message = "Execution is already in a terminal state."


class ForbiddenSelfChangeError(ConflictError):
    code = "FORBIDDEN_SELF_CHANGE"
    http_status = 409
    message = "Administrators cannot disable or demote themselves."


# ── 413 Payload Too Large ──────────────────────────────────────────────────────


class PayloadTooLargeError(AppError):
    code = "PAYLOAD_TOO_LARGE"
    http_status = 413
    message = "Request payload exceeds the maximum allowed size."


class DefinitionTooLargeError(AppError):
    code = "DEFINITION_TOO_LARGE"
    http_status = 413
    message = "Workflow definition exceeds the maximum allowed size."


# ── 429 Too Many Requests ──────────────────────────────────────────────────────


class RateLimitedError(AppError):
    code = "RATE_LIMITED"
    http_status = 429
    message = "Too many requests. Please slow down."

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after: int | None = None,
        details: list[dict] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after = retry_after


class AccountLockedError(AppError):
    code = "ACCOUNT_LOCKED"
    http_status = 429
    message = "Account is temporarily locked due to too many failed login attempts."

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after: int | None = None,
        details: list[dict] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after = retry_after


class WorkflowConcurrencyLimitError(AppError):
    code = "WORKFLOW_CONCURRENCY_LIMIT"
    http_status = 429
    message = "Maximum concurrent executions for this workflow has been reached."


# ── 500 Internal Server Error ─────────────────────────────────────────────────


class InternalError(AppError):
    code = "INTERNAL_ERROR"
    http_status = 500
    message = "An internal server error occurred."


# ── 503 Service Unavailable ───────────────────────────────────────────────────


class DatabaseUnavailableError(AppError):
    code = "DATABASE_UNAVAILABLE"
    http_status = 503
    message = "Database is temporarily unavailable."


class ServiceUnavailableError(AppError):
    code = "SERVICE_UNAVAILABLE"
    http_status = 503
    message = "Service is temporarily unavailable."
