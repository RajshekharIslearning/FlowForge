"""
FlowForge — Pytest configuration and shared fixtures.

SRS §19.1:
  - Database: real PostgreSQL (service container in CI, Compose locally).
    SQLite MUST NOT be used anywhere, including tests.
  - Rollback pattern: each test runs in a transaction rolled back at the end.
  - Redis: fakeredis in unit tests, real Redis in integration tests.
  - TestClient for API endpoints.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest

# Ensure test environment variables are set before importing any application modules
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://flowforge:change-me@localhost:5432/flowforge",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/14")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/13")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-chars-long!")
os.environ.setdefault("ENCRYPTION_KEY", "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=")

from fastapi.testclient import TestClient

from app.main import create_app


# Guard: Strictly reject SQLite anywhere (SRS §19.1 and Phase 1 Constraint 4)
def _guard_no_sqlite(db_url: str) -> None:
    if "sqlite" in db_url.lower():
        raise RuntimeError(
            "SQLite is strictly forbidden by the FlowForge SRS (§19.1) and Phase 1 constraints. "
            "Tests must run against a real PostgreSQL instance."
        )


@pytest.fixture(scope="session", autouse=True)
def verify_test_environment() -> None:
    """Verify that tests are running in test environment and not SQLite."""
    # Ensure test environment variables are set with fallback defaults for local test runs
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://flowforge:change-me@localhost:5432/flowforge",
    )
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
    os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/14")
    os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/13")
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-chars-long!")
    os.environ.setdefault("ENCRYPTION_KEY", "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=")

    db_url = os.environ.get("DATABASE_URL", "")
    _guard_no_sqlite(db_url)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provide a TestClient instance for testing HTTP endpoints."""
    app = create_app()
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client
