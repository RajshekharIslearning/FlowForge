# FlowForge — API Reference

This document summarizes the REST API design. Full endpoints are detailed in the [FlowForge SRS](file:///FlowForge%20SRS.md) §13.

## Phase 1 Endpoints

### Health Check Endpoints (Root Path, Public)
- `GET /health` — Liveness check. Returns 200 `{"status": "ok"}` without checking dependencies.
- `GET /health/ready` — Readiness check. Checks PostgreSQL (`SELECT 1`), Redis (`PING`), and Alembic migration revision. Returns 200 `{"status": "ready", ...}` or 503 `{"status": "not_ready", ...}`.

Full authentication, workflow, execution, and integration APIs are implemented in subsequent phases.
