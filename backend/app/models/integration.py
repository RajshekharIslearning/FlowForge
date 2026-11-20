"""
FlowForge — Integration model.

SRS §12.2 — integrations table.

Security: credentials are encrypted at rest using Fernet (SRS SEC-14).
The encrypted ciphertext is stored; the API response returns only
credential_fields (field names, never values).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Integration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Reusable credential store for workflow steps.

    SRS §12.2 — integrations table.
    SRS FR-INT-01: Types are http_bearer, http_header_api_key, http_basic.
    SRS FR-INT-02: Credentials are Fernet-encrypted; API never returns values.
    """

    __tablename__ = "integrations"
    __table_args__ = (
        Index(
            "uq_integrations_owner_name",
            "owner_id",
            text("lower(name)"),
            unique=True,
        ),
        CheckConstraint(
            "type IN ('http_bearer', 'http_header_api_key', 'http_basic')",
            name="ck_integrations_type",
        ),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Fernet-encrypted JSON blob (SRS SEC-14, FR-INT-02)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # Field names only — what fields exist, no values (SRS FR-INT-02)
    credential_fields: Mapped[list] = mapped_column(JSONB, nullable=False)
    # Optional list of allowed hostnames for credential injection (SRS FR-INT-01)
    allowed_hosts: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────
    owner: Mapped[User] = relationship("User", foreign_keys=[owner_id])
