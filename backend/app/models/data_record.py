"""
FlowForge — UserDataRecord model.

SRS §12.2 — user_data_records table.

The database action (SRS §10.4) operates ONLY on this table.
owner_id is always injected by the engine — never supplied via config.
Collection names are regex-validated: ^[a-z][a-z0-9_]{0,39}$.
Quota: 10,000 records per user.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserDataRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    User-owned data record for the database action sandbox.

    SRS §12.2 — user_data_records table.
    SRS D-08: Only operates on this table; never on platform tables.
    """

    __tablename__ = "user_data_records"
    __table_args__ = (
        # Optional deduplication key per owner+collection
        UniqueConstraint(
            "owner_id",
            "collection",
            "dedupe_key",
            name="uq_udr_owner_collection_dedupe",
            # Effective only when dedupe_key IS NOT NULL (NULLs are not unique)
        ),
        # For find queries (SRS §10.4)
        Index(
            "ix_udr_owner_collection_created",
            "owner_id",
            "collection",
            text("created_at DESC"),
        ),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Collection regex: ^[a-z][a-z0-9_]{0,39}$ (validated in service layer)
    collection: Mapped[str] = mapped_column(String(40), nullable=False)
    # Arbitrary JSON data (≤64 KB, validated in service layer)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Optional deduplication key (unique per owner+collection when set)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────
    owner: Mapped[User] = relationship("User", foreign_keys=[owner_id])
