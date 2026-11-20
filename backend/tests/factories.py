"""
FlowForge — Test factories.

This file provides factory helpers for test fixtures.
In Phase 1, basic helpers are defined; full FactoryBoy models are added in Phase 2+.
"""

from __future__ import annotations

import uuid
from typing import Any


def create_user_data(
    email: str = "user@example.com",
    full_name: str = "Test User",
    role: str = "user",
    password_hash: str = "dummy_hash_for_phase1_tests",
) -> dict[str, Any]:
    """Helper to generate user model dictionary."""
    return {
        "id": uuid.uuid4(),
        "email": email,
        "full_name": full_name,
        "role": role,
        "password_hash": password_hash,
    }
