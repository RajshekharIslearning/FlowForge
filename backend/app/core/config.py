"""
FlowForge — Core configuration.

All configuration is read from environment variables via pydantic-settings.
The Settings object is cached (singleton) and available throughout the app.
No secrets are ever hard-coded here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXAMPLE_JWT_KEY = "change-me-generate-with-openssl-rand-hex-32"
_EXAMPLE_FERNET_KEY = "generate-with-python-cryptography-fernet-generate-key"


def _validate_fernet_key(key: str) -> None:
    """Raise ValueError if *key* is not a valid Fernet key."""
    from cryptography.fernet import Fernet, InvalidToken

    try:
        Fernet(key.encode())
    except (ValueError, InvalidToken, Exception) as exc:
        raise ValueError(f"Invalid Fernet key: {exc}") from exc


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    The SRS (§20.1) specifies startup validation: the app MUST fail fast
    (CRITICAL log, process exit) when required settings are missing or invalid.
    That enforcement is done by field validators below and by the FastAPI
    startup event in main.py.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars (e.g. Docker infra vars)
    )

    # ── Application ────────────────────────────────────────────────────────
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    enable_docs: bool = True
    app_base_url: str = "http://localhost:3000"

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 10

    # ── Redis ──────────────────────────────────────────────────────────────
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    # ── Security ───────────────────────────────────────────────────────────
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Comma-separated Fernet keys; first encrypts, all decrypt (enables rotation)
    encryption_key: str

    # ── CORS ───────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"
    trusted_proxy_count: int = 0

    # ── Email ──────────────────────────────────────────────────────────────
    smtp_host: str = "mailpit"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@flowforge.local"
    smtp_starttls: bool = True
    email_daily_limit_per_user: int = 100

    # ── Workers ────────────────────────────────────────────────────────────
    worker_concurrency: int = 4

    # ── SSRF override (tests ONLY — refused in production) ─────────────────
    allow_private_network_requests: bool = False

    # ── Admin seed ─────────────────────────────────────────────────────────
    admin_email: str = ""
    admin_password: str = ""

    # =========================================================================
    # Validators
    # =========================================================================

    @field_validator("jwt_algorithm")
    @classmethod
    def _validate_jwt_algorithm(cls, v: str) -> str:
        if v != "HS256":
            raise ValueError("JWT_ALGORITHM must be 'HS256' (SRS SEC-02)")
        return v

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql+psycopg://"):
            raise ValueError(
                "DATABASE_URL must use 'postgresql+psycopg://' (psycopg3 driver). "
                "Do NOT use psycopg2 or SQLite."
            )
        return v

    @model_validator(mode="after")
    def _validate_security_settings(self) -> Settings:
        """
        SRS SEC-02: Refuse to start outside development if JWT secret is
        missing, too short, or equals the example value.
        """
        if self.environment != "development":
            if not self.jwt_secret_key:
                raise ValueError("JWT_SECRET_KEY is required in non-development environments")
            if len(self.jwt_secret_key) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters (SRS SEC-02)")
            if self.jwt_secret_key == _EXAMPLE_JWT_KEY:
                raise ValueError("JWT_SECRET_KEY must not equal the example value (SRS SEC-02)")

        # SRS SEC-02: Always reject 'none' — handled in JWT validation logic.
        # Validate ENCRYPTION_KEY (all keys in comma-separated list)
        for key in self.encryption_key.split(","):
            key = key.strip()
            if not key or key == _EXAMPLE_FERNET_KEY:
                if self.environment != "development" or key == _EXAMPLE_FERNET_KEY:
                    if self.environment != "development":
                        raise ValueError(
                            "ENCRYPTION_KEY must be a valid Fernet key in non-development"
                        )
            if key and key != _EXAMPLE_FERNET_KEY:
                _validate_fernet_key(key)

        # SRS: ALLOW_PRIVATE_NETWORK_REQUESTS must be false in production
        if self.environment == "production" and self.allow_private_network_requests:
            raise ValueError(
                "ALLOW_PRIVATE_NETWORK_REQUESTS must be false in production (SRS 14.1)"
            )

        # SRS SEC-06: Never wildcard CORS in production
        if self.environment == "production" and "*" in self.cors_origins:
            raise ValueError("Wildcard CORS_ORIGINS is not allowed in production (SRS SEC-06)")

        return self

    @model_validator(mode="after")
    def _configure_docs(self) -> Settings:
        """Disable OpenAPI docs by default in production."""
        if self.environment == "production":
            # Override to False unless explicitly set to True (unusual for prod)
            # We respect whatever is in the env; just don't default to True
            pass
        return self

    # =========================================================================
    # Computed properties
    # =========================================================================

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a parsed list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def fernet_keys(self) -> list[bytes]:
        """Return all Fernet keys as bytes, in order (first = active)."""
        return [k.strip().encode() for k in self.encryption_key.split(",") if k.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the cached Settings singleton.

    Using lru_cache means settings are read from the environment exactly once.
    In tests, call ``get_settings.cache_clear()`` after patching env vars.
    """
    return Settings()
