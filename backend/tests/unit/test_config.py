"""
FlowForge — Unit tests for Settings configuration validation.

SRS §20.1 & SRS SEC-02:
  - Valid settings load properly.
  - Startup validation rejects missing or invalid required values.
  - SQLite rejected in DATABASE_URL.
  - JWT secret length (< 32 chars) rejected in non-development.
  - Example JWT secret rejected in non-development.
  - Invalid Fernet key rejected.
  - ALLOW_PRIVATE_NETWORK_REQUESTS=true rejected in production.
  - Wildcard CORS rejected in production.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_FERNET_KEY = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="
VALID_JWT_KEY = "a" * 32
VALID_DB_URL = "postgresql+psycopg://user:pass@localhost:5432/flowforge"


def _make_settings(**kwargs: str | int | bool) -> Settings:
    """Helper to instantiate Settings with valid base values and overrides."""
    base: dict[str, str | int | bool] = {
        "environment": "test",
        "database_url": VALID_DB_URL,
        "redis_url": "redis://localhost:6379/1",
        "celery_broker_url": "redis://localhost:6379/0",
        "celery_result_backend": "redis://localhost:6379/2",
        "jwt_secret_key": VALID_JWT_KEY,
        "encryption_key": VALID_FERNET_KEY,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_valid_settings() -> None:
    """Valid settings instantiate without error and computed properties work."""
    settings = _make_settings()
    assert settings.environment == "test"
    assert settings.is_test is True
    assert settings.is_development is False
    assert settings.is_production is False
    assert len(settings.cors_origins_list) >= 1
    assert len(settings.fernet_keys) >= 1


def test_invalid_database_url_sqlite() -> None:
    """SQLite in DATABASE_URL is strictly rejected."""
    with pytest.raises(ValidationError) as exc_info:
        _make_settings(database_url="sqlite:///test.db")
    assert "postgresql+psycopg://" in str(exc_info.value)


def test_invalid_database_url_psycopg2() -> None:
    """psycopg2 driver in DATABASE_URL is rejected (psycopg3 required)."""
    with pytest.raises(ValidationError) as exc_info:
        _make_settings(database_url="postgresql+psycopg2://user:pass@localhost/db")
    assert "postgresql+psycopg://" in str(exc_info.value)


def test_jwt_algorithm_must_be_hs256() -> None:
    """Only HS256 is accepted as JWT algorithm (SRS SEC-02)."""
    with pytest.raises(ValidationError) as exc_info:
        _make_settings(jwt_algorithm="RS256")
    assert "HS256" in str(exc_info.value)


def test_jwt_secret_too_short_in_test_or_prod() -> None:
    """JWT secret under 32 characters is rejected outside development."""
    with pytest.raises(ValidationError) as exc_info:
        _make_settings(jwt_secret_key="too-short")
    assert "at least 32 characters" in str(exc_info.value)


def test_jwt_secret_example_value_rejected_in_test_or_prod() -> None:
    """Default/example JWT secret is rejected outside development."""
    with pytest.raises(ValidationError) as exc_info:
        _make_settings(jwt_secret_key="change-me-generate-with-openssl-rand-hex-32")
    assert "must not equal the example value" in str(exc_info.value)


def test_invalid_fernet_encryption_key() -> None:
    """Malformed Fernet key is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        _make_settings(encryption_key="not-a-valid-base64-fernet-key")
    assert "Fernet key" in str(exc_info.value)


def test_allow_private_network_requests_forbidden_in_production() -> None:
    """ALLOW_PRIVATE_NETWORK_REQUESTS=true must fail validation in production."""
    with pytest.raises(ValidationError) as exc_info:
        _make_settings(
            environment="production",
            allow_private_network_requests=True,
        )
    assert "ALLOW_PRIVATE_NETWORK_REQUESTS must be false in production" in str(exc_info.value)


def test_wildcard_cors_forbidden_in_production() -> None:
    """Wildcard CORS origin is rejected in production (SRS SEC-06)."""
    with pytest.raises(ValidationError) as exc_info:
        _make_settings(
            environment="production",
            cors_origins="*",
        )
    assert "Wildcard CORS_ORIGINS is not allowed in production" in str(exc_info.value)
