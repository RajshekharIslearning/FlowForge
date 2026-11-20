# FlowForge — Implementation Decisions Log

This document records architectural clarifications, edge-case resolutions, and design decisions made during the implementation of FlowForge. All decisions here are strictly aligned with the FlowForge SRS v1.0.

---

## Decision Log

### DEC-001: ExecutionLog Primary Key Uses BIGINT Identity
- **SRS Reference:** §12.1, §12.2 (`execution_logs` table)
- **Context:** SRS §12.1 states that all primary keys must be UUID4 with server default `gen_random_uuid()`. However, §12.2 explicitly specifies `execution_logs.id` as `BIGINT identity PK` for cheap, ordered appends.
- **Resolution:** `ExecutionLog` is defined with `id: BigInteger, Identity(always=True)` rather than using the `UUIDPrimaryKeyMixin`. All other 12 tables strictly use UUID4 primary keys.
- **Impact:** Aligns with PostgreSQL append performance for high-frequency logs while preserving UUID uniformity across entities.

### DEC-002: System Settings Idempotent Seed vs Migration Separation
- **SRS Reference:** §12.2 (`system_settings`), §20.3 (`migrate` service)
- **Context:** The SRS states "Seeded by migration" under §12.2 for system settings, while §20.3 specifies the container command as `alembic upgrade head && python -m app.scripts.seed`.
- **Resolution:** Alembic migration `0001_initial_schema.py` handles pure DDL (table, indexes, constraints). Data seeding is handled in `backend/app/scripts/seed.py` using `INSERT ... ON CONFLICT (key) DO NOTHING`.
- **Impact:** Keeps migrations strictly schema-focused and ensures seed operations can be safely re-run without violating unique constraints or failing container restarts.

### DEC-003: Alembic Autogenerate and Expression / Partial Indexes
- **SRS Reference:** §12.2, Binding decision D-03
- **Context:** Alembic autogenerate does not natively synthesize functional expression indexes like `(owner_id, lower(name)) WHERE deleted_at IS NULL` or partial unique indexes without manual review.
- **Resolution:** The initial migration `0001_initial_schema.py` was crafted with explicit `op.create_index` calls including `postgresql_where` and `sa.text("lower(name)")`. Every future migration will be manually reviewed against model definitions and checked via `alembic check` in CI.
- **Impact:** Guarantees that PostgreSQL expression and partial indexes match SRS requirements exactly.

### DEC-004: Phase 1 Admin Creation CLI Stub
- **SRS Reference:** Phase 1 Approval Constraints
- **Context:** User constraint #3 specifies that Phase 1 is foundation only; `create_admin.py` remains a CLI stub until Phase 2 implements full authentication, password hashing (Argon2id), and user creation.
- **Resolution:** `backend/app/scripts/create_admin.py` is implemented as an executable CLI stub that logs its Phase 1 status and exits cleanly.
- **Impact:** Clear boundary separation between foundation (Phase 1) and authentication/authorization business logic (Phase 2).

### DEC-005: Strict PostgreSQL Enforcement (No SQLite)
- **SRS Reference:** §12.1, §19.1, Constraint #4
- **Context:** SQLite lacks native support for `JSONB`, `INET`, partial indexes, and `FOR UPDATE SKIP LOCKED`.
- **Resolution:** Both the application engine factory (`app/db/session.py`) and test suite configuration (`tests/conftest.py`) actively guard against and reject `sqlite://` connections with a fatal error.
- **Impact:** Prevents subtle dialect bugs and guarantees test fidelity against production PostgreSQL 16.
