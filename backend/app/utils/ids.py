"""
FlowForge — Identifier utilities.

SRS §12.1: Primary keys are UUID4.
Helper functions for generating and validating UUIDs.
"""

from __future__ import annotations

import uuid


def new_uuid() -> uuid.UUID:
    """Generate a new UUID4."""
    return uuid.uuid4()


def new_uuid_str() -> str:
    """Generate a new UUID4 as a hyphenated string."""
    return str(uuid.uuid4())


def is_valid_uuid(value: str) -> bool:
    """Check whether a string is a valid UUID representation."""
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
