"""
FlowForge — Time utilities.

Provides mockable UTC time helpers.
SRS §12.1: All timestamps are stored in UTC with timezone.
SRS §19.3: Tests use frozen time or injected clocks.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(UTC)


def to_iso8601(dt: datetime) -> str:
    """Format datetime as ISO-8601 UTC string (e.g. 2026-10-31T09:00:00Z)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
