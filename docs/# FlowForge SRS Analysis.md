# FlowForge SRS Analysis

## 1. Project Purpose and Objectives

**Project**: FlowForge — A Python-based workflow automation and background job processing platform.

**Vision**: A lightweight, self-hostable automation engine in the spirit of Zapier or n8n, reduced to what can be built, tested and explained thoroughly by one engineer. Correctness, safety and clarity of failure behaviour take priority over feature count.

**Goals (G1-G5)**:
- G1: Reliable async execution — No execution is lost across worker, API, Redis or PostgreSQL restarts
- G2: Safe by default — SSRF protections, no arbitrary code, secrets encrypted, no secrets in logs
- G3: Observable — Every execution has step-level state, logs and a request/correlation ID
- G4: Demonstrable — `docker compose up` yields a working system with dashboard and seed admin
- G5: Maintainable — Layered architecture, type hints, Alembic migrations, ≥80% coverage

**Scope (V1 In-scope)**: Auth and RBAC, workflow CRUD with versioning, manual/scheduled/webhook triggers, five actions (HTTP, Python function, Database, Email, Transform), Celery execution engine with retries, execution monitoring and logs, integrations (credential store), admin endpoints, audit logging, rate limiting, health checks, minimal React dashboard, Docker Compose, GitHub Actions CI.

**Scope (V1 Out-of-scope)**: Branching, conditions, parallel steps, visual canvas, OAuth integrations, multi-tenancy/organisations, workflow templates, marketplace, email verification, Kubernetes, horizontal scheduler HA.

## 2. Functional Requirements

### 2.1 Authentication (FR-AUTH)
- FR-AUTH-01: Register with email, password, full_name; role always `user`; registration can be disabled
- FR-AUTH-02: Argon2id hashing (time_cost=3, memory_cost=65536 KiB, parallelism=4)
- FR-AUTH-03: Login with lockout after 5 failures (15 min)
- FR-AUTH-04: JWT HS256 access tokens (15 min default)
- FR-AUTH-05: Opaque rotating refresh tokens (7 days) with reuse detection
- FR-AUTH-06: Logout revokes refresh family and denylists access token
- FR-AUTH-07: Password reset with single-use tokens (30 min expiry)
- FR-AUTH-08: Account status (is_active) blocks login, revokes tokens, deactivates schedules
- FR-AUTH-09: RBAC via FastAPI dependencies
- FR-AUTH-10: Profile management (full_name, change password)

### 2.2 Workflow Management (FR-WF)
- FR-WF-01: Create workflow (draft, version 1)
- FR-WF-02: Update with versioning (definition changes bump version)
- FR-WF-03: Soft delete (deactivates schedule/webhook, cancels queued executions)
- FR-WF-04: Activate/deactivate with full validation
- FR-WF-05: Clone as draft
- FR-WF-06: List/search with filters and pagination
- FR-WF-07: Version history
- FR-WF-08: Validate definition without saving

**Validation Rules (7.2.1)**: Name 1-120 chars unique per owner; ≤20 steps; step IDs regex; action must be registered; template references only to earlier steps; timeout 1-60s; retry max_attempts 1-5; execution timeout 10-900s; variables ≤50 keys; definition ≤128 KB; schedule validation; per-user limits (100 workflows, 25 active)

### 2.3 Integrations (FR-INT)
- FR-INT-01: Credential types (http_bearer, http_header_api_key, http_basic) with optional allowed_hosts
- FR-INT-02: Encrypted at rest with Fernet; API never returns values
- FR-INT-03: Names unique per owner; update may replace credentials
- FR-INT-04: Delete blocked if referenced by non-deleted workflow
- FR-INT-05: Steps reference by integration_id; engine decrypts at execution time

### 2.4 Workflow Engine (Section 8)
- Definition format with trigger, variables, settings, steps
- Execution context with trigger, vars, steps
- Template rules (D-06): `{{ dotted.path[0] }}` lookups only
- Lifecycles: workflow (draft→active⇄inactive→deleted), execution (queued→running→waiting_retry→succeeded/failed/cancelled/timed_out), step (pending→running→waiting_retry→succeeded/failed/timed_out/skipped/cancelled)
- Execution algorithm with atomic claim, template resolution, action execution, retry/backoff
- Timeouts: step (1-60s), execution (10-900s), Celery soft/hard limits
- Cancellation: cooperative via cancel_requested flag
- Idempotency: Idempotency-Key header, unique indexes
- Failure behaviour: detailed matrix for all scenarios

### 2.5 Trigger System (Section 9)
- Trigger architecture with BaseTrigger abstract class
- Manual trigger: POST /workflows/{id}/execute
- Schedule trigger: once or cron mode, timezone support, min 60s interval, scheduler.tick every 15s
- Webhook trigger: HMAC-SHA256, timestamp ±300s, delivery ID replay protection, rate limit 60/min

### 2.6 Action System (Section 10)
- BaseAction abstract class with ConfigModel and execute method
- http_request: SSRF-safe, method/url/headers/query/json_body/integration_id, response extraction
- python_function: registered pure functions only, no arbitrary code
- database: operates only on user_data_records sandbox table
- email: SMTP with daily quota, CR/LF rejection
- transform: pure operations (select, rename, filter, map_values, set, pick)

### 2.7 Background Job Architecture (Section 11)
- Queues: executions, maintenance
- Tasks: run_execution, scheduler.tick, outbox.sweep, executions.reap, cleanup.run
- Celery config: acks_late, reject_on_worker_lost, prefetch=1, time limits
- Retry/dead-letter: PostgreSQL is DLQ, Redis holds no dead-letter queue
- Redis vs PostgreSQL data separation

## 3. Non-Functional Requirements (Section 17)

| ID | Area | Requirement |
|----|------|-------------|
| NFR-01 | API latency | p95 < 300 ms CRUD/read, < 500 ms list (10k executions, 20 users) |
| NFR-02 | Execute latency | POST /execute returns 202 in p95 < 500 ms |
| NFR-03 | Queue pickup | Median < 3s, p95 < 10s with idle workers |
| NFR-04 | Throughput | 20 concurrent executions with 1 worker (concurrency 4) |
| NFR-05 | Workflow size | ≤20 steps, ≤128 KB definition, ≤25 active per user |
| NFR-06 | Payloads | Trigger ≤256 KB, step output ≤256 KB, context ≤1 MB, HTTP response ≤1 MB |
| NFR-07 | Timeouts | Step 1-60s, HTTP ≤30s, execution 10-900s, DB 5s, API 30s |
| NFR-08 | DB pooling | API 10+10, worker 5+5, Postgres max_connections ≥100 |
| NFR-09 | Durability | No committed execution lost on single component restart |
| NFR-10 | Availability | Single instance, no HA claim |
| NFR-11 | Startup | docker compose up healthy in < 90s warm cache |
| NFR-12 | Retention | Executions 90 days, audit 365 days (configurable) |
| NFR-13 | Portability | Python 3.12, PostgreSQL 16, Redis 7, pinned versions |
| NFR-14 | Maintainability | ruff/mypy clean, typed, cyclomatic complexity ≤15 |
| NFR-15 | Accessibility | Keyboard-operable, labelled inputs, sufficient contrast |

## 4. Technology Stack and Architectural Decisions

### Technology Stack
- **Language**: Python 3.12
- **Web Framework**: FastAPI 0.115.x, Uvicorn
- **Database**: PostgreSQL 16, SQLAlchemy 2.0 (sync ORM), psycopg 3, Alembic
- **Queue/Cache**: Redis 7, Celery 5.4 (Redis broker)
- **Auth/Security**: Argon2id, PyJWT (HS256), cryptography (Fernet)
- **HTTP Client**: httpx
- **Logging**: structlog
- **Validation**: Pydantic 2, pydantic-settings
- **Scheduling**: croniter
- **Dev Tools**: uv (package management), ruff (lint/format), mypy (typing), pytest (testing), bandit/pip-audit (security)

### Architectural Decisions (D-01 through D-18)
Key decisions: sync ORM for API and workers, PostgreSQL as source of truth, JSONB workflow snapshots, fixed enum roles, form-based builder, no expression language, no arbitrary code, sandbox DB table, Argon2id+JWT auth, durable outbox pattern, step retries via re-enqueue, DB-driven scheduler, retry creates new execution, only active workflows execute, offset pagination, uv+ruff+mypy, no email verification, no auth cookies.

### Architecture Style (Section 15)
Layered modular monolith with one deployable backend image used by three processes (api, worker, scheduler). Strict layer imports downward only. Workflow engine is framework-free for unit testability.

## 5. Database Requirements and Entities (Section 12)

### Conventions
- PostgreSQL 16, SQLAlchemy 2.0 declarative with Mapped[] typing
- UUID PKs (uuid4, gen_random_uuid()), except execution_logs BIGINT identity
- TIMESTAMPTZ in UTC, created_at default now(), updated_at onupdate
- Enums as VARCHAR with CHECK constraints
- FKs indexed, session per request/task, services own transactions

### Tables (14 tables)
1. **users** - id, email, password_hash, full_name, role, is_active, failed_login_count, locked_until, last_login_at, timestamps
2. **refresh_tokens** - id, user_id, family_id, token_hash, expires_at, revoked_at, replaced_by_id, created_ip, user_agent, created_at
3. **password_reset_tokens** - id, user_id, token_hash, expires_at, used_at, created_at
4. **workflows** - id, owner_id, name, description, status, version, trigger_type, deleted_at, timestamps
5. **workflow_versions** - id, workflow_id, version, definition (JSONB), definition_hash, created_by, created_at
6. **workflow_executions** - id, workflow_id, workflow_version, owner_id, triggered_by_user_id, trigger_type, trigger_payload, status, idempotency_key, retry_of_execution_id, current_step_id, failed_step_id, retry_count, recovery_count, cancel_requested, error_code, error_message, queued_at, enqueued_at, next_attempt_at, started_at, finished_at, heartbeat_at, deadline_at, duration_ms, worker_id, request_id, created_at
7. **step_executions** - id, execution_id, step_id, step_index, action_type, status, retry_count, input_meta, output, output_meta, error_code, error_message, error_details, next_attempt_at, started_at, finished_at, duration_ms, created_at
8. **execution_logs** - id (BIGINT), execution_id, step_execution_id, level, message, context, request_id, created_at
9. **integrations** - id, owner_id, name, type, credentials_encrypted, credential_fields, allowed_hosts, timestamps
10. **schedules** - id, workflow_id, mode, cron_expression, run_at, timezone, next_run_at, last_run_at, is_active, timestamps
11. **webhook_configs** - id, workflow_id, secret_encrypted, secret_prefix, is_active, rotated_at, last_delivery_at, created_at
12. **audit_logs** - id, actor_user_id, actor_role, action, resource_type, resource_id, outcome, ip, user_agent, request_id, metadata, created_at
13. **user_data_records** - id, owner_id, collection, data, dedupe_key, timestamps
14. **system_settings** - key, value, updated_by, updated_at

### Normalisation Decisions
- 3NF for users, tokens, integrations, schedules, webhooks
- Deliberate denormalisation: workflows.trigger_type, workflow_executions.owner_id, workflow_executions.workflow_version
- JSONB snapshots for definitions
- step_executions pre-created per execution
- Retention via nightly cleanup

## 6. API Requirements (Section 13)

### Conventions
- Base path `/api/v1`, JSON only, ISO-8601 UTC timestamps, UUID strings
- Auth header: `Authorization: Bearer <access_token>`
- Request ID: `X-Request-ID` (client may send, server always returns)
- Pagination: page (default 1), page_size (1-100, default 20)
- Rate-limit headers: X-RateLimit-Limit, Remaining, Reset, Retry-After
- OpenAPI at `/openapi.json`, Swagger at `/docs` (disabled in prod)
- Body caps: 1 MB global, 256 KB webhook, 128 KB workflow definition

### Error Format
Standard envelope with code, message, details, request_id. Categories: 422 validation, 400 bad request, 401 auth, 403 forbidden, 404 not found, 409 conflict, 413 too large, 429 rate limited, 500 server, 503 unavailable.

### Endpoint Catalogue
**Auth & Profile**: register, login, refresh, logout, password reset request/confirm, GET/PATCH /users/me, change-password
**Workflows**: CRUD, activate/deactivate, clone, execute, validate, list/search, versions, webhook info/rotate
**Executions**: list, detail, retry, cancel, logs
**Webhook**: POST /webhooks/{workflow_id} (HMAC auth)
**Integrations**: CRUD, catalogue endpoints (/actions, /actions/python-functions)
**Admin**: users, executions, stats, workers, settings, audit-logs
**Health**: /health (liveness), /health/ready (readiness with DB/Redis/migrations checks)

### Rate Limiting (Section 13.6)
Redis fixed-window counters. Auth: per endpoint limits. Workflow ops: 30-60/hour/user. Execute/retry: 20/min/user. Webhook: 60/min/workflow. Other auth: 300/min/user. Unauth: 60/min/IP. Fail open on Redis errors.

## 7. Authentication and Authorization Requirements

### Auth (Section 7.1, 14)
- Argon2id password hashing
- JWT HS256 access tokens (15 min), opaque rotating refresh tokens (7 days)
- Refresh rotation with reuse detection (family revocation)
- Logout denylists access token, revokes refresh family
- Password reset with single-use tokens, revokes all refresh tokens
- Account lockout after 5 failures (15 min)
- is_active flag blocks all authenticated calls
- RBAC: user/admin roles, ownership checks in service layer, cross-user returns 404

### Authorization (Section 6.1)
Permission matrix: users manage own resources; admins read-only metadata access to all users' resources; admins cannot read integration secrets or step payloads; first admin via CLI or env vars; no public path to admin.

## 8. Background Jobs and Workflow Execution Requirements

### Engine (Section 8)
- Linear workflows (1 trigger, up to 20 ordered steps)
- Execution context with trigger, vars, steps
- Template resolution: `{{ dotted.path[0] }}` only, whole-value type preservation, no re-scan
- State machine with compare-and-set transitions
- Step execution: template resolution → config validation → action.execute() within timeout
- Retry: exponential backoff with jitter (base * 2^(attempt-1), max 600s, ±20% jitter)
- Retryable errors: network, HTTP 408/425/429/500/502/503/504, SMTP 4xx, HTTP step timeouts
- Permanent errors: other 4xx, config/template/validation, SSRF, unknown function, DB constraints, output too large

### Background Architecture (Section 11)
- FastAPI commits execution row → PostgreSQL, enqueues to Redis → Celery worker
- Celery Beat runs scheduler.tick, outbox.sweep, executions.reap, cleanup.run
- Queues: executions (run_execution), maintenance (scheduler, outbox, reaper, cleanup)
- Celery config: acks_late, reject_on_worker_lost, prefetch=1, time limits 120/150s, visibility_timeout=1800s
- Worker: prefork pool, concurrency 4 default, scale with docker compose
- Redis vs PostgreSQL: Redis for transient (queue, rate limits, denylist, dedupe, heartbeats, caches); PostgreSQL for all durable state

### Failure Behaviour (Section 8.8)
Detailed matrix covering: step success/failure/timeout, retry success/exhaustion, cancellation, worker crash (reaper recovery, max 3), API crash (outbox sweeper), Redis outage (fail open, sweeper drains), PostgreSQL outage (503, worker autoretry, reaper heals)

## 9. Frontend Requirements (Section 16)

### Stack
React 18, TypeScript, Vite, React Router, TanStack Query, Tailwind CSS. No state-management library beyond TanStack Query and React context for auth.

### Builder Decision
Form-based builder (not visual canvas). Ordered list of step cards with type selector, JSON schema-generated forms, up/down/remove, insert variable helper. Raw JSON tab with Validate button.

### Pages
Login, Register, Password Reset, Workflow List, Workflow Create/Edit, Workflow Detail, Execution History, Execution Detail, Integrations, Profile, Admin Dashboard.

### Behaviour Rules
- Access token in memory, refresh token in sessionStorage
- Single-flight interceptor refreshes on 401 TOKEN_EXPIRED
- Error envelope displayed with message, request_id copyable
- No dangerouslySetInnerHTML
- Served by nginx container (Compose profile ui, port 3000) proxying /api to API
- Frontend tests: Vitest for API client/refresh logic and step-form generator; manual smoke checklist

## 10. Security Requirements (Section 14)

### Security Controls (SEC-01 through SEC-20)
- SEC-01: Argon2id password hashing
- SEC-02: JWT HS256 with ≥32 byte secret, explicit alg verification
- SEC-03: Opaque refresh tokens, hashed at rest, rotated, reuse detection
- SEC-04: Token invalidation on logout/disable/password change
- SEC-05: RBAC with ownership filters in repository queries
- SEC-06: CORS explicit allow-list, no wildcard with credentials
- SEC-07: CSRF not applicable (no auth cookies)
- SEC-08: SQL injection prevention (ORM/bound params only)
- SEC-09: Command injection prevention (no subprocess/eval/pickle)
- SEC-10: Input validation (Pydantic v2, extra='forbid')
- SEC-11: Output safety (JSON only, sanitised errors, redaction)
- SEC-12: Security headers (nosniff, DENY, no-referrer, no-store, HSTS in prod)
- SEC-13: Secrets from env vars only, .env git-ignored, gitleaks in CI
- SEC-14: Encryption at rest (Fernet MultiFernet for key rotation)
- SEC-15: Audit logging
- SEC-16: Dependency management (uv.lock, pip-audit, Dependabot, Trivy)
- SEC-17: Docker hardening (non-root, slim base, multi-stage, cap_drop, read-only fs)
- SEC-18: Webhook HMAC with timestamp, replay protection, constant-time compare
- SEC-19: Rate limiting
- SEC-20: Error disclosure prevention

### SSRF Protection (SEC-SSRF, Section 14.1)
Mandatory SafeHttpClient wrapper for all outbound HTTP:
1. Scheme/port allow-list (http/https, ports 80/443/8080/8443)
2. Hostname deny-list (localhost, *.local, *.internal, metadata.google.internal, single-label)
3. Resolve first, validate every address against private/link-local/reserved ranges
4. Defeat DNS rebinding (connect to validated IP, send original Host/SNI)
5. Redirects disabled by default, ≤3 hops with re-validation
6. Limits: timeout ≤30s, response ≤1MB, request ≤256KB, trust_env=False
7. Credential scope: allowed_hosts enforcement
8. ALLOW_PRIVATE_NETWORK_REQUESTS=false in production
9. Logging of blocked attempts
10. Mandatory test matrix (10 test cases)

## 11. Testing Requirements (Section 19)

### Tooling
pytest, pytest-cov, pytest-asyncio, httpx/TestClient, respx, freezegun, factory-boy. Markers: unit, integration, e2e.

### Database
Real PostgreSQL (service container in CI, Compose locally). SQLite MUST NOT be used. Schema via alembic upgrade head once per session; tests in rolled-back transactions.

### Redis
Real Redis (db 15, flushed per test) for integration; fakeredis allowed in unit tests.

### Celery
Unit/integration: call task directly or task_always_eager=True. One e2e test with real worker container.

### Outbound HTTP
respx for unit tests; local mock server with ALLOW_PRIVATE_NETWORK_REQUESTS=true for integration. No real internet.

### Required Coverage (Section 19.2)
- Unit services: registration, lockout, workflow versioning, clone naming, ownership, concurrency, idempotency
- Unit engine: all transitions, backoff math, resume, on_failure=continue, cancel, deadline, heartbeat, claim race
- Unit templates: whole-value type preservation, embedded stringification, missing path error, no re-scan, forward reference rejection
- Unit validation: all 7.2.1 rules, cron/timezone/DST, schedule min interval
- Unit actions: each action happy path and error classes, transform ops, function registry import guard, email header injection, DB action isolation
- Unit security: password hashing/rehash, JWT claims/expiry/tamper/alg=none, refresh rotation/reuse, HMAC verification, Fernet round-trip/rotation, redaction, SSRF matrix
- API: all endpoints success and primary errors, pagination, cross-user 404, admin 403, error envelope, rate limit, idempotency
- Integration: execute→Celery→steps persisted→final state; webhook E2E; scheduler tick; reaper; outbox sweeper
- Failure tests: upstream 500→success, always 503, step timeout, invalid definition, invalid credentials, DB unavailable, Redis unavailable, worker crash, huge response, malformed/replayed/expired webhook
- E2E: register→login→create→activate→execute→poll succeeded; failing workflow

### Coverage Targets (Section 19.3)
Overall line coverage ≥80% (CI gate). ≥90% for app/engine, app/core/security*, app/actions/safe_http*. Branch coverage reported not gated.

## 12. Deployment and Infrastructure Requirements (Section 20)

### Configuration (Section 20.1)
All config from environment variables via pydantic-settings Settings class. Startup validation rejects missing required vars, weak secrets in non-dev, invalid Fernet key, ALLOW_PRIVATE_NETWORK_REQUESTS=true in production, wildcard CORS in production.

Key variables: ENVIRONMENT, LOG_LEVEL, LOG_FORMAT, ENABLE_DOCS, APP_BASE_URL, DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW, REDIS_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND, JWT_SECRET_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES, JWT_REFRESH_TOKEN_EXPIRE_DAYS, ENCRYPTION_KEY, CORS_ORIGINS, TRUSTED_PROXY_COUNT, SMTP_*, EMAIL_DAILY_LIMIT_PER_USER, WORKER_CONCURRENCY, ALLOW_PRIVATE_NETWORK_REQUESTS, ADMIN_EMAIL, ADMIN_PASSWORD.

### Images (Section 20.2)
- backend.Dockerfile: multi-stage (builder with uv sync --frozen --no-dev, runtime python:3.12-slim, user flowforge UID 10001)
- frontend.Dockerfile: Node 20 build, nginx:1.27-alpine serving dist with proxy to api:8000

### Compose Services (Section 20.3)
postgres, redis, migrate (alembic upgrade head + seed), api (uvicorn 2 workers), worker (celery -Q executions,maintenance), scheduler (celery beat), mailpit, frontend (profile ui). One network flowforge-net, named volumes pgdata/redisdata, restart unless-stopped, cap_drop ALL, no-new-privileges, read-only with tmpfs /tmp for app services. Production compose no host ports; override publishes 5432/6379, mounts source for reload.

### Run Commands (Section 20.4)
cp .env.example .env, docker compose up --build, docker compose --profile ui up --build, make test, make lint.

## 13. Explicitly Excluded Features and Out-of-Scope Items (Sections 5, 27)

### V1 Out of Scope
- Branching, conditions, parallel steps
- Visual node-based canvas (React Flow)
- OAuth integrations
- Multi-tenancy/organisations
- Workflow templates and marketplace
- Email verification
- Kubernetes deployment
- Horizontal scheduler HA
- Advanced analytics (Prometheus/OpenTelemetry)
- MFA, SSO
- Workflow-to-workflow calls and sub-workflows
- Execution payload encryption
- Per-step sensitive-output marking

### V2+ Future Scope (Section 27)
Visual drag-and-drop builder; branching/conditional/parallel/loops; templates/marketplace; OAuth integrations; more actions; advanced analytics; multi-tenancy; distributed workers/HA scheduler; email verification/MFA/SSO; K8s/Helm; workflow-to-workflow calls; payload encryption.

## 14. Implementation Phases and Dependencies (Section 23)

### Phase 1: Project Setup, Database, Configuration
- **Objective**: Runnable skeleton with all tables
- **Tasks**: Repo layout, pyproject.toml, ruff/mypy/pytest config, Settings, DB session, all SQLAlchemy models, initial Alembic migration, request-ID middleware, structured logging, error classes/handlers, /health and /health/ready, Dockerfile, Compose, Makefile, CI skeleton
- **Dependencies**: None
- **Acceptance**: docker compose up brings API healthy; alembic upgrade head creates all tables; alembic check no drift; /health/ready 200/503; settings validation tests pass

### Phase 2: Authentication & Authorisation
- **Tasks**: Argon2 hashing, register/login/refresh/logout/reset, users/me, RBAC deps, Redis rate limiter, audit service, email sender, admin seed/CLI
- **Dependencies**: Phase 1
- **Acceptance**: All AC-AUTH criteria; rate-limit and lockout tests pass; reuse detection revokes family

### Phase 3: Workflow CRUD
- **Tasks**: Definition schemas and validation, workflow CRUD, versions, activate/deactivate (schedule/webhook hooks stubbed), clone, list/search, validate endpoint, per-user limits, audit entries
- **Dependencies**: Phase 2
- **Acceptance**: AC-WF; version bumps only on definition change; cross-user 404

### Phase 4: Workflow Engine & Actions
- **Tasks**: Template resolver, state machine with compare-and-set, runner callable synchronously, actions (transform, python_function, database, email, http_request with SafeHttpClient), /actions catalogue, ExecutionService.create_and_enqueue, execution read endpoints
- **Dependencies**: Phase 3
- **Acceptance**: Engine unit tests cover all transitions; SSRF matrix passes; in-process engine yields persisted step states

### Phase 5: Celery + Redis
- **Tasks**: Celery app and config, run_execution task, execute/retry/cancel endpoints, idempotency keys, outbox sweeper, reaper, heartbeats, worker and scheduler Compose services
- **Dependencies**: Phase 4
- **Acceptance**: AC-EXEC; retry/backoff verified; worker kill mid-run leads to recovery; Redis stop/start doesn't lose queued execution

### Phase 6: Scheduling & Webhooks
- **Tasks**: Schedule trigger validation and next_run_at computation, scheduler.tick, activation hooks creating schedule/webhook rows, webhook endpoint with HMAC/replay protection/rate limit, secret rotation, trigger registry
- **Dependencies**: Phase 5
- **Acceptance**: AC-SCHED, AC-WEBHOOK; concurrent ticks create one execution per due schedule

### Phase 7: Integrations
- **Tasks**: Fernet MultiFernet crypto, integration CRUD with write-only credentials, in-use check, credential injection into http_request, allowed_hosts enforcement
- **Dependencies**: Phase 4 (can run parallel with 6)
- **Acceptance**: AC-INT; credentials never in API responses, logs, step outputs

### Phase 8: Monitoring, Logging, Admin
- **Tasks**: execution_logs writes and GET /executions/{id}/logs, complete audit coverage, admin endpoints, worker heartbeat keys, stats cache, cleanup task, log-redaction tests
- **Dependencies**: Phases 5-7
- **Acceptance**: AC-ADMIN, AC-OBS; one request ID traces from API to worker log

### Phase 9: Frontend
- **Tasks**: Vite app per section 16, API client with refresh logic, all pages, nginx image, ui Compose profile
- **Dependencies**: Phases 2-8 API stable
- **Acceptance**: User completes E2E journey in browser; admin pages work

### Phase 10: Testing & Security Hardening
- **Tasks**: Fill gaps in 19.2, failure tests, coverage gates, security headers, bandit/pip-audit clean, review ownership filters, load check NFR-01/02/04
- **Dependencies**: All prior
- **Acceptance**: 19.3 targets met; no HIGH findings; failure-test list passes

### Phase 11: Docker, CI/CD, Documentation
- **Tasks**: Final Dockerfiles and hardening, finalise CI, Dependabot, all docs, demo seed script, README quick start verified on clean clone
- **Dependencies**: All prior
- **Acceptance**: Definition of Done (section 29)

## 15. Ambiguous or Unspecified Items

1. **Email verification**: Explicitly stated as not required in V1 (D-17), but password reset emails are sent. The email delivery mechanism for password reset is specified but the actual email template/content is not detailed.

2. **System settings defaults**: Some system settings are mentioned (registration_enabled, max_workflows_per_user, max_active_workflows_per_user, execution_retention_days, audit_retention_days) but not all possible settings are enumerated.

3. **Frontend test coverage**: Only Vitest for API client/refresh logic and step-form generator mentioned; Playwright is "optional" but no specific coverage targets for frontend.

4. **Monitoring/metrics**: Prometheus/OpenTelemetry explicitly V2, but no specific metrics or alerting requirements for V1 beyond health endpoints and admin stats.

5. **Backup/restore**: No mention of database backup/restore procedures or disaster recovery.

6. **Log retention**: Structured logging to stdout, but no log aggregation or retention policy specified beyond application-level audit_logs retention.

7. **API versioning strategy**: Only v1 specified; no deprecation or versioning policy for future versions.

8. **Webhook secret rotation**: Secret rotation endpoint exists but no automatic rotation schedule or notification mechanism.

9. **Integration credential rotation**: Fernet MultiFernet supports key rotation but no automatic rotation schedule or process specified.

10. **Worker scaling**: Horizontal scaling via `docker compose up --scale worker=N` mentioned but no auto-scaling or queue-depth-based scaling logic.

11. **Execution priority**: No priority queue or execution prioritization mechanism specified.

12. **Workflow import/export**: Explicitly V2, but no format specified for future implementation.

13. **Audit log integrity**: Append-only mentioned but no cryptographic integrity verification (hash chains, signatures) specified.

14. **Rate limit configuration**: Limits specified but not all are configurable via system settings (some hardcoded in SRS).

15. **Timezone handling for users**: User timezone preference not stored; schedules use workflow-level timezone only.