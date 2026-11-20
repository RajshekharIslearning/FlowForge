"""
FlowForge — Integration tests for health endpoints.

SRS §13.3:
  - GET /health returns 200 {"status": "ok"} without checking dependencies.
  - GET /health/ready returns 200 {"status": "ready", "checks": {...}} when ready.
  - GET /health/ready returns 503 with the failing check named when any dependency fails.
  - X-Request-ID header is returned on every response (SRS §18.1).
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_liveness_endpoint(client: TestClient) -> None:
    """GET /health must return 200 {'status': 'ok'} and carry X-Request-ID."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


def test_readiness_endpoint_all_ok(client: TestClient) -> None:
    """GET /health/ready returns 200 when all dependencies are healthy."""
    with (
        patch("app.api.v1.health.ping_database", return_value=True),
        patch("app.api.v1.health.ping_redis", return_value=True),
        patch("app.api.v1.health._check_migrations", return_value=True),
    ):
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"] == "ok"
        assert data["checks"]["redis"] == "ok"
        assert data["checks"]["migrations"] == "ok"


def test_readiness_endpoint_database_down(client: TestClient) -> None:
    """GET /health/ready returns 503 when the database check fails."""
    with (
        patch("app.api.v1.health.ping_database", return_value=False),
        patch("app.api.v1.health.ping_redis", return_value=True),
        patch("app.api.v1.health._check_migrations", return_value=True),
    ):
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["database"] == "unavailable"


def test_readiness_endpoint_redis_down(client: TestClient) -> None:
    """GET /health/ready returns 503 when Redis check fails."""
    with (
        patch("app.api.v1.health.ping_database", return_value=True),
        patch("app.api.v1.health.ping_redis", return_value=False),
        patch("app.api.v1.health._check_migrations", return_value=True),
    ):
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["redis"] == "unavailable"


def test_readiness_endpoint_migrations_behind(client: TestClient) -> None:
    """GET /health/ready returns 503 when migrations are behind head."""
    with (
        patch("app.api.v1.health.ping_database", return_value=True),
        patch("app.api.v1.health.ping_redis", return_value=True),
        patch("app.api.v1.health._check_migrations", return_value=False),
    ):
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["migrations"] == "behind"


def test_request_id_preserved_when_supplied(client: TestClient) -> None:
    """When client sends X-Request-ID, the server echoes the same ID."""
    custom_id = "test-request-id-12345"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id
