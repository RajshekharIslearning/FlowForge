"""
FlowForge — User, RefreshToken, and PasswordResetToken models.

SRS §12.2 tables: users, refresh_tokens, password_reset_tokens.

Security notes (SRS SEC-01, SEC-03):
- password_hash stores only the Argon2id hash, never plaintext.
- RefreshToken stores only the SHA-256 hash of the opaque token,
  never the raw token value.
- PasswordResetToken stores only the SHA-256 hash of the raw token.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Platform user account.

    SRS §12.2 — users table.
    Role is a VARCHAR CHECK constraint enum (D-04: no roles table).
    """

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),)

    email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
        unique=True,
        # SRS FR-AUTH-01: stored lower-cased
        # Lower-casing is enforced in the service layer before persisting.
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        # Argon2id hash, never plaintext (SRS SEC-01)
    )
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("'user'"),
        default="user",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        default=True,
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        default=0,
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RefreshToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """
    Opaque rotating refresh token record.

    SRS §12.2 — refresh_tokens table.
    SRS SEC-03: Only the SHA-256 hash of the raw token is stored.
    Rotation: each use revokes the presented token and creates a new one
    in the same family_id. Reuse detection: presenting a rotated token
    revokes the entire family (SRS FR-AUTH-05).
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    # SHA-256 hex digest of the raw opaque token (SRS SEC-03)
    token_hash: Mapped[str] = mapped_column(
        String(64),  # SHA-256 hex = 64 chars
        nullable=False,
        unique=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # FK to the replacement token (for audit chain)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_ip: Mapped[str | None] = mapped_column(
        INET,
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


class PasswordResetToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """
    Single-use password reset token.

    SRS §12.2 — password_reset_tokens table.
    Only the SHA-256 hash of the raw token is stored.
    Max 3 outstanding per user; 30-min expiry.
    """

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),  # SHA-256 hex
        nullable=False,
        unique=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="password_reset_tokens")
