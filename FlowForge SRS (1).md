# FlowForge — Software Requirements Specification

*A Python-based workflow automation and background job processing platform.*

**Version 1.0 · 31 October 2026 · Owner: Rajshekhar · Primary consumer: Antigravity (AI coding agent)**

---

## 1. Document Information

| Field | Value |
| --- | --- |
| Project | FlowForge |
| Document type | Software Requirements Specification (implementation-ready) |
| Status | Baseline v1.0 |
| Source of truth | This document. If code and SRS disagree, the SRS wins until it is formally amended. |
| Keywords | MUST / MUST NOT / SHOULD / MAY are used in the RFC 2119 sense. |
| Requirement IDs | `FR-<AREA>-nn` (functional), `NFR-nn` (non-functional), `SEC-nn` (security). Tests SHOULD reference IDs. |

### 1.1 Resolved design decisions (binding)

Where the brief left room, these decisions were made. The agent MUST NOT reopen them without amending this SRS.

| ID | Decision | Reason |
| --- | --- | --- |
| D-01 | Python 3.12, FastAPI, SQLAlchemy 2.0 **sync** ORM with psycopg 3, Alembic. | Celery workers are synchronous; one DB style for API and workers avoids duplicate session code. FastAPI runs sync endpoints in a threadpool. |
| D-02 | PostgreSQL is the **source of truth** for all state. Redis holds only transient data (queue messages, rate-limit counters, token denylist, dedupe cache, worker heartbeats, small caches). | Redis loss must never lose executions. |
| D-03 | Workflow definitions (trigger + steps) are stored as an immutable JSONB snapshot per version in `workflow_versions`. There is **no** `workflow_steps` table. | Executions pin to a version; snapshots are simpler and safer than versioning child rows. Step-level state lives in `step_executions`. |
| D-04 | Roles are a fixed enum column `users.role` (`user`, `admin`). There is **no** `roles` table. | Only two static roles; a table adds joins with no benefit. |
| D-05 | Visual node-based builder is **out of V1**. V1 uses a form-based, ordered-list step editor. | Linear workflows only; a node canvas adds large frontend cost with no backend value. |
| D-06 | No expression language. Templates are `{{ dotted.path[0] }}` lookups only. | Eliminates a whole class of injection and complexity. |
| D-07 | No arbitrary user code. The Python action runs only functions from a code-registered allow-list of pure functions. | Safety. |
| D-08 | Database action operates only on a per-user sandbox table (`user_data_records`), never on platform tables. | Safety; still demonstrates DB writes. |
| D-09 | Auth: Argon2id passwords, HS256 JWT access tokens (15 min), opaque rotating refresh tokens (7 days) with reuse detection. | Standard, testable, no key-distribution complexity. |
| D-10 | Execution is dispatched via a **durable-outbox pattern**: the execution row is committed first (`queued`), then enqueued; a beat sweeper re-enqueues anything not picked up. | Survives Redis outages and API crashes. |
| D-11 | Step retries are implemented by ending the Celery task and re-enqueuing it with a countdown; the engine resumes from persisted step state. | Frees worker slots during backoff and makes crash recovery the same code path as retry. |
| D-12 | Scheduling uses a DB-driven poller (`scheduler.tick` every 15 s, `FOR UPDATE SKIP LOCKED`) run by Celery Beat, not Celery's in-memory schedule. | Schedules are user data in PostgreSQL; survives restarts; no per-schedule Beat entries. |
| D-13 | Retry of a failed execution creates a **new** execution (full re-run, same version, same trigger payload). | Keeps execution records immutable and auditable. |
| D-14 | Only `active` workflows can be executed (manual, scheduled, or webhook). New workflows start as `draft`. | Activation is the validation gate. |
| D-15 | Pagination is offset-based: `page` (default 1), `page_size` (default 20, max 100). | Simple; adequate at portfolio scale. |
| D-16 | Package management with `uv` and `pyproject.toml` + `uv.lock`; lint/format with `ruff`; typing with `mypy`. | Fast, reproducible. |
| D-17 | Email verification is not required in V1. Registration can be switched off via system setting. | Scope control; documented limitation. |
| D-18 | Access token in memory; refresh token sent in JSON body (no auth cookies). CSRF therefore does not apply to the API. | Avoids cookie/CSRF complexity. |

---

## 2. Executive Summary

FlowForge lets authenticated users define linear workflows (one trigger, up to 20 ordered steps), run them manually, on a schedule, or via signed webhook, and watch every execution step by step. A FastAPI service handles the REST API; Celery workers execute workflows asynchronously; PostgreSQL stores all durable state; Redis provides the broker and fast ephemeral storage. The platform is deliberately small, but it exercises the skills a backend engineer is expected to show: relational design, auth, async job processing, retries and idempotency, SSRF-safe outbound HTTP, observability, testing, containerisation and CI.

## 3. Product Vision

A lightweight, self-hostable automation engine in the spirit of Zapier or n8n, reduced to what can be built, tested and explained thoroughly by one engineer. Correctness, safety and clarity of failure behaviour take priority over feature count.

## 4. Goals & Objectives

| # | Goal | Measurable outcome |
| --- | --- | --- |
| G1 | Reliable async execution | No execution is lost across worker, API, Redis or PostgreSQL restarts (see 8.8). |
| G2 | Safe by default | SSRF protections, no arbitrary code, secrets encrypted, no secrets in logs. |
| G3 | Observable | Every execution has step-level state, logs and a request/correlation ID. |
| G4 | Demonstrable | `docker compose up` yields a working system with dashboard and seed admin. |
| G5 | Maintainable | Layered architecture, type hints, Alembic migrations, ≥80% coverage. |

## 5. Scope

**In scope (V1):** auth and RBAC, workflow CRUD with versioning, manual/scheduled/webhook triggers, five actions (HTTP, Python function, Database, Email, Transform), Celery execution engine with retries, execution monitoring and logs, integrations (credential store), admin endpoints, audit logging, rate limiting, health checks, minimal React dashboard, Docker Compose, GitHub Actions CI.

**Out of scope (V1):** branching, conditions, parallel steps, visual canvas, OAuth integrations, multi-tenancy/organisations, workflow templates, marketplace, email verification, Kubernetes, horizontal scheduler HA. See section 27.

## 6. Users & Roles

| Role | Description |
| --- | --- |
| `user` | Standard account. Owns and manages only their own resources. |
| `admin` | Platform operator. Can manage users and view system-wide data. Admins MUST NOT read integration secrets or step payloads of other users; they see metadata, status and error codes only. |

### 6.1 Permission matrix

| Capability | user | admin |
| --- | --- | --- |
| Register, log in, manage own profile, change own password | ✔ | ✔ |
| CRUD own workflows; activate/deactivate/clone/execute own workflows | ✔ | ✔ (own only) |
| View own executions, step details, logs; retry/cancel own executions | ✔ | ✔ (own only) |
| CRUD own integrations | ✔ | ✔ (own only) |
| View any user's workflows/executions (metadata only) | ✘ | ✔ read-only via `/admin/*` |
| Cancel any execution | ✘ | ✔ via `/admin/executions/{id}/cancel` |
| List/disable/enable users, change roles | ✘ | ✔ (cannot disable or demote self) |
| View platform stats, workers, audit logs | ✘ | ✔ |
| Read/update system settings | ✘ | ✔ |

Accessing another user's resource MUST return `404 *_NOT_FOUND` (not 403) to avoid leaking existence.

The first admin is created by a CLI command (`python -m app.scripts.create_admin`) or from `ADMIN_EMAIL`/`ADMIN_PASSWORD` env vars on first boot when no admin exists. There is no public path to become admin.

---

## 7. Functional Requirements

### 7.1 Authentication (FR-AUTH)

| ID | Requirement |
| --- | --- |
| FR-AUTH-01 | **Register**: `email` (valid, ≤254, stored lower-cased, unique), `password` (10–128 chars, MUST NOT equal email or be in a bundled list of ≥1,000 common passwords), `full_name` (1–100). Role is always `user`. Returns 201 with profile. If registration is disabled in system settings, return 403 `REGISTRATION_DISABLED`. Duplicate email returns 409 `EMAIL_ALREADY_REGISTERED`. |
| FR-AUTH-02 | **Hashing**: Argon2id via `argon2-cffi` (time\_cost=3, memory\_cost=65536 KiB, parallelism=4). Re-hash transparently at login if parameters are outdated. |
| FR-AUTH-03 | **Login**: `email` + `password`. Unknown email and wrong password MUST yield the same 401 `INVALID_CREDENTIALS` and comparable timing (verify against a dummy hash when user is absent). After 5 consecutive failures the account is locked for 15 minutes: 429 `ACCOUNT_LOCKED` with `Retry-After`. Success resets the counter. |
| FR-AUTH-04 | **Access token**: JWT HS256, claims `sub` (user UUID), `role`, `jti`, `iat`, `exp`, `type=access`. Lifetime `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default 15). Validation MUST check signature, `exp`, `type`, and Redis denylist, then load the user and require `is_active`. |
| FR-AUTH-05 | **Refresh token**: opaque 256-bit `secrets.token_urlsafe(32)`, stored only as SHA-256 hash in `refresh_tokens`, lifetime `JWT_REFRESH_TOKEN_EXPIRE_DAYS` (default 7). **Rotation**: each refresh revokes the presented token and issues a new one in the same `family_id`. **Reuse detection**: presenting an already-rotated/revoked token revokes the entire family and returns 401 `REFRESH_TOKEN_REUSED`. |
| FR-AUTH-06 | **Logout**: body carries the refresh token; its family is revoked; the current access token `jti` is written to Redis (`ff:denylist:{jti}`) with TTL = remaining lifetime. Returns 204. Idempotent. |
| FR-AUTH-07 | **Password reset**: `POST /auth/password-reset/request` always returns 202 regardless of whether the email exists. If it exists and the account is active, email a single-use token (32 random bytes, stored hashed, 30-min expiry, max 3 outstanding). `POST /auth/password-reset/confirm` sets the new password, marks the token used, revokes ALL the user's refresh tokens, resets lockout. |
| FR-AUTH-08 | **Account status**: `is_active=false` blocks login, refresh and all authenticated calls (403 `ACCOUNT_DISABLED`). Disabling a user revokes all their refresh tokens, deactivates their schedules (flag, not deletion) and cancels their queued executions. Re-enabling does NOT auto-reactivate schedules; the owner re-activates workflows explicitly (see 25: disabled user with scheduled workflow). |
| FR-AUTH-09 | **RBAC**: implemented as FastAPI dependencies `get_current_user` and `require_admin`. Ownership checks live in the service layer, never only in routers. |
| FR-AUTH-10 | **Profile**: `GET/PATCH /users/me` (full\_name only), `POST /users/me/change-password` (requires current password; revokes other refresh families). |

### 7.2 Workflow management (FR-WF)

| ID | Requirement |
| --- | --- |
| FR-WF-01 | **Create**: persists workflow (status `draft`, version 1) and the first `workflow_versions` row. Draft MAY have 0 steps. |
| FR-WF-02 | **Update** (`PUT`): full replacement of name, description, definition. If `definition` differs from the current version, `version` increments and a new immutable `workflow_versions` row is inserted. Name/description-only changes do not bump the version. Editing an `active` workflow is allowed; the new version applies to future executions only. Request MAY include `expected_version` for optimistic concurrency; mismatch returns 409 `VERSION_CONFLICT`. |
| FR-WF-03 | **Delete**: soft delete (`deleted_at`). Deactivates schedule/webhook, cancels queued/waiting-retry executions, requests cancellation of running ones. Execution history is retained. |
| FR-WF-04 | **Activate**: runs full validation (7.2.1). On success sets `active`, creates/updates the schedule row (scheduled trigger) or webhook config (webhook trigger, generating the secret on first activation). **Deactivate**: sets `inactive`, disables schedule; webhook returns 404 while inactive; in-flight executions finish. |
| FR-WF-05 | **Clone**: new `draft` workflow owned by the caller, version 1, same definition, name `<name> (copy)` (suffix `  2 `, `  3 `, … on collision). No schedule, no webhook secret, no execution history. |
| FR-WF-06 | **List/search**: filters `status`, `trigger_type`, `q` (case-insensitive substring of name), `sort` (`created_at`, `updated_at`, `name`; prefix `-` for descending; default `-updated_at`), pagination per D-15. |
| FR-WF-07 | **Versions**: `GET /workflows/{id}/versions` and `/versions/{n}` return history. Old versions are read-only. |
| FR-WF-08 | **Validate**: `POST /workflows/validate` validates a definition without saving and returns all errors at once. |

#### 7.2.1 Workflow validation rules

| Rule | Limit / behaviour | Error |
| --- | --- | --- |
| `name` | 1–120 chars after trimming; unique per owner among non-deleted (case-insensitive) | 409 `WORKFLOW_NAME_EXISTS` |
| `description` | ≤1000 chars | 422 |
| Steps count | ≤20 always; ≥1 required to activate | 422 `WORKFLOW_TOO_MANY_STEPS` / `WORKFLOW_NO_STEPS` |
| Step `id` | regex `^[a-z][a-z0-9_]{0,39}$`, unique within workflow | 422 `STEP_ID_INVALID` / `STEP_ID_DUPLICATE` |
| Step `action` | MUST be a registered action type | 422 `UNKNOWN_ACTION` |
| Step `config` | validated by the action's Pydantic model | 422 with field paths |
| Template references | only `trigger.*`, `vars.*`, and `steps.<id>.output...` where `<id>` is an **earlier** step. Forward, self, or unknown references rejected | 422 `INVALID_REFERENCE` |
| Circular references | impossible by construction (rule above); no workflow-to-workflow calls in V1 | — |
| `timeout_seconds` (step) | 1–60, default 30 | 422 |
| `retry.max_attempts` | 1–5 total attempts (1 = no retry), default 3 | 422 |
| `retry.backoff_base_seconds` | 1–300, default 5 | 422 |
| `settings.timeout_seconds` (execution) | 10–900, default 300 | 422 |
| `variables` | object, ≤50 keys, JSON-serialisable, no template syntax inside | 422 |
| Definition size | ≤128 KB serialised | 422 `DEFINITION_TOO_LARGE` |
| Schedule | see 9.2 | 422 `INVALID_CRON` / `INVALID_TIMEZONE` / `SCHEDULE_TOO_FREQUENT` |
| Limits per user | ≤100 non-deleted workflows, ≤25 active (system-setting overridable) | 409 `WORKFLOW_LIMIT_REACHED` |

### 7.3 Integrations (FR-INT)

| ID | Requirement |
| --- | --- |
| FR-INT-01 | An integration stores reusable credentials for HTTP Request steps. Types: `http_bearer` (`token`), `http_header_api_key` (`header_name`, `api_key`), `http_basic` (`username`, `password`). Optional `allowed_hosts` list restricts which hostnames the credential may be sent to (enforced when set). |
| FR-INT-02 | Credentials are encrypted at rest with Fernet using `ENCRYPTION_KEY`. API responses MUST NEVER return credential values; they return `credential_fields` (field names) only. |
| FR-INT-03 | Names unique per owner. Update may replace credentials (write-only). |
| FR-INT-04 | Delete returns 409 `INTEGRATION_IN_USE` if referenced by any non-deleted workflow's current version; otherwise hard-deletes. |
| FR-INT-05 | Steps reference an integration by `integration_id`; the engine decrypts it in memory at execution time only, and verifies it belongs to the workflow owner. |

---

## 8. Workflow Engine

### 8.1 Definition format

```json
{
  "trigger": { "type": "schedule", "config": { "mode": "cron", "cron": "0 9 * * 1-5", "timezone": "Asia/Kolkata" } },
  "variables": { "api_base": "https://api.example.com" },
  "settings": { "timeout_seconds": 300 },
  "steps": [
    { "id": "fetch", "name": "Fetch users", "action": "http_request",
      "config": { "method": "GET", "url": "{{ vars.api_base }}/users", "integration_id": null },
      "timeout_seconds": 20, "retry": { "max_attempts": 3, "backoff_base_seconds": 5 }, "on_failure": "fail" },
    { "id": "shape", "name": "Pick fields", "action": "transform",
      "config": { "input": "{{ steps.fetch.output.body }}", "operations": [ { "op": "select", "fields": ["id", "email"] } ] } }
  ]
}
```

`on_failure` is `fail` (default; abort the workflow) or `continue` (mark the step failed, proceed; its output is `null`). `continue` is the only error-tolerance feature in V1.

### 8.2 Execution context & data flow

The engine builds one JSON-serialisable context per execution:

```json
{
  "trigger": { "type": "webhook", "payload": { }, "received_at": "2026-10-31T09:00:00Z", "execution_id": "..." },
  "vars": { "api_base": "https://api.example.com" },
  "steps": { "fetch": { "status": "succeeded", "output": { "status_code": 200, "body": [ ] } } }
}
```

**Template rules (D-06):**

1. Syntax is `{{ path }}` where `path` is dot-separated keys with optional `[n]` integer indexes, e.g. `steps.fetch.output.body[0].email`. Whitespace inside braces is ignored. No operators, filters, function calls or arithmetic.
2. Templates are resolved **only** in string values inside a step's `config`. Keys are never templated.
3. If a string is exactly one template, the resolved value keeps its JSON type (object, list, number, bool, null). If embedded in a longer string, the value is stringified (objects/lists via compact JSON) and concatenated.
4. A path that cannot be resolved raises a permanent `TEMPLATE_RESOLUTION_ERROR` failing the step (no silent empty strings).
5. Resolved values are NOT re-scanned for templates (prevents injection through webhook payloads or API responses).
6. After resolution the action's Pydantic model validates the final config (type validation). Failure is a permanent `STEP_CONFIG_INVALID`.
7. Integration credentials are never part of the context and cannot be referenced by templates.

**Size limits:** webhook/execute input ≤256 KB; each step output ≤256 KB serialised (excess → permanent `OUTPUT_TOO_LARGE`); total context ≤1 MB. Serialisation is UTF-8 JSON; `datetime` as ISO-8601 UTC strings; `Decimal` as strings; bytes are not allowed in outputs.

**Sensitive data:** step outputs are stored raw (needed for resume), but (a) API responses redact values whose keys match `password|secret|token|authorization|api_key|apikey|credential` (case-insensitive) to `***`, and (b) logs record only metadata (sizes, key names, status codes), never payloads.

### 8.3 Lifecycles and state transitions

**Workflow:** `draft → active ⇄ inactive`; any → `deleted` (soft). Only `active` runs.

**Execution statuses:** `queued`, `running`, `waiting_retry`, `succeeded`, `failed`, `cancelled`, `timed_out`. Terminal: the last four.

| From | To | Trigger |
| --- | --- | --- |
| (new) | `queued` | Execution row created by manual/schedule/webhook/retry |
| `queued` | `running` | Worker claims row atomically |
| `queued` | `cancelled` | Cancel requested before pickup |
| `running` | `waiting_retry` | A step failed with a retryable error and attempts remain |
| `waiting_retry` | `running` | Re-enqueued task claims row when `next_attempt_at` has passed |
| `running` | `succeeded` | All steps succeeded (or failed with `on_failure=continue`) |
| `running` | `failed` | Permanent step failure or retries exhausted with `on_failure=fail`; or recovery exhausted |
| `running` / `waiting_retry` | `timed_out` | Execution deadline exceeded |
| `running` / `waiting_retry` | `cancelled` | Cancel requested and honoured at next checkpoint |

**Step statuses:** `pending`, `running`, `waiting_retry`, `succeeded`, `failed`, `timed_out`, `skipped`, `cancelled`. `skipped` applies to steps never reached after a failure/cancel/timeout.

Every transition MUST be a conditional `UPDATE ... WHERE status IN (...)` (compare-and-set); zero rows updated means another actor won and the caller aborts silently.

### 8.4 Execution algorithm

```
run_execution(execution_id):               # Celery task, queue=executions, acks_late
  claim: UPDATE executions SET status='running', started_at=coalesce(started_at,now()),
         heartbeat_at=now(), worker_id=:host
         WHERE id=:id AND status IN ('queued','waiting_retry')
           AND (next_attempt_at IS NULL OR next_attempt_at <= now())
  if 0 rows: return                         # duplicate delivery or not yet due
  load workflow_version snapshot; rebuild context from step_executions with status=succeeded
  for step in steps (in order), skipping steps already succeeded / failed-continued:
    if now() > deadline: finish(timed_out); return
    if cancel_requested: finish(cancelled); return
    mark step running (attempt += 1), heartbeat
    try: resolve templates -> validate config -> action.execute(ctx) within step timeout
    except Retryable:
        if attempt < max_attempts:
            step=waiting_retry; execution=waiting_retry; next_attempt_at = now + backoff(attempt)
            apply_async(run_execution, countdown=backoff, queue=executions); return
        else: step=failed (RETRIES_EXHAUSTED)
    except Permanent / Timeout: step=failed / timed_out
    on success: persist output, context.steps[id]=output
    on failure: if on_failure=='continue': record, continue
                else: mark remaining steps skipped; finish(failed); return
  finish(succeeded)
```

- **Backoff:** `delay = min(backoff_base * 2^(attempt-1), 600)` plus ±20% jitter.
- **Retryable errors:** network errors, HTTP 408/425/429/500/502/503/504 (honour `Retry-After` up to 600 s), SMTP temporary (4xx) errors, step timeouts for `http_request` only. **Permanent:** other 4xx, config/template/validation errors, SSRF blocks, unknown function, DB constraint errors, output too large.
- `finish(status)` writes `finished_at`, `duration_ms`, `error_code`, `error_message` (sanitised) in one transaction and emits an execution log entry.
- Each step state change is committed immediately (own transaction) so the dashboard shows live progress.

### 8.5 Timeouts

- **Step timeout** (`timeout_seconds`, default 30, max 60): HTTP via httpx connect/read/total timeouts; Python functions via a worker thread with `future.result(timeout)` (functions are pure, so abandoning a runaway thread is safe and documented); DB action via `statement_timeout`; email via SMTP socket timeout.
- **Execution timeout** (`settings.timeout_seconds`, default 300, max 900): deadline = `started_at + timeout`; checked between steps and before each retry. Exceeding it yields `timed_out`. Retries do not extend the deadline.
- Celery `soft_time_limit` per task slice = 120 s, `time_limit` = 150 s as a backstop (a slice is at most one step plus overhead).

### 8.6 Cancellation

`POST /executions/{id}/cancel` sets `cancel_requested=true`. If status is `queued` or `waiting_retry` the API itself performs the compare-and-set to `cancelled` (remaining steps `skipped`). If `running`, the worker honours the flag before the next step/retry; the in-flight step is allowed to finish or time out (no thread killing), then the execution becomes `cancelled`. Cancelling a terminal execution returns 409 `EXECUTION_ALREADY_FINISHED`.

### 8.7 Idempotency, locking and concurrency

- **Idempotency key:** `POST /workflows/{id}/execute` and `POST /executions/{id}/retry` accept header `Idempotency-Key` (≤128 chars). A partial unique index on `(workflow_id, idempotency_key)` guarantees a repeat returns the original execution with 200 instead of creating a new one. Webhook uses `X-FlowForge-Delivery-Id` the same way. Scheduled runs use key `sched:{schedule_id}:{scheduled_for_iso}`.
- **Locking:** the atomic claim in 8.4 is the execution lock; PostgreSQL row-level atomicity is authoritative. No Redis locks.
- **Concurrency limits:** ≤3 active (`queued`/`running`/`waiting_retry`) executions per workflow; exceeding returns 429 `WORKFLOW_CONCURRENCY_LIMIT` for manual/webhook. Scheduled ticks that find the limit hit **skip** that occurrence and write a WARNING log + audit entry `schedule.skipped`. Different workflows run in parallel up to worker concurrency.
- **Step-level idempotency:** `http_request` with POST/PATCH is retried only on connection errors before the request is sent, 429 and 503. `database` insert accepts an optional `dedupe_key`.

### 8.8 Failure behaviour (explicit)

| Situation | Behaviour |
| --- | --- |
| Step succeeds | Output persisted, step `succeeded`, context updated, next step starts. |
| Step fails (permanent) | Step `failed`. If `on_failure=continue` proceed; else remaining steps `skipped`, execution `failed` with `error_code` = step's code and `failed_step_id` set. |
| Step times out | Retryable only for `http_request`; otherwise permanent. Step ends `timed_out`; execution `failed` with `STEP_TIMEOUT` (or `timed_out` if the execution deadline was the cause). |
| Retry succeeds | Step `succeeded`, `retry_count` retained for visibility, execution continues; earlier errors preserved in logs. |
| All retries fail | Step `failed` with `RETRIES_EXHAUSTED` (original cause in `details`), execution `failed` (unless `continue`). The execution row is the dead-letter record, visible via `GET /admin/executions?status=failed`. |
| Workflow cancelled | See 8.6. |
| Worker crashes mid-step | Task is not acked (`acks_late`, `reject_on_worker_lost`), so Redis redelivers after `visibility_timeout`. Additionally the **reaper** (beat, every 60 s) finds `running` executions with `heartbeat_at` older than 5 min, sets them `queued`, increments `recovery_count`, re-enqueues. Limit 3 recoveries, then `failed` with `WORKER_LOST`. A step caught mid-flight is re-run from its start, so side-effecting steps MAY run twice; this at-least-once behaviour is documented. |
| API server crashes | Execution rows are committed before enqueueing. If the crash falls between commit and enqueue, the **outbox sweeper** (beat, every 30 s) enqueues any `queued` execution with `enqueued_at IS NULL` or older than 2 min. |
| Redis unavailable | API still accepts executions (row committed `queued`; enqueue failure logged WARNING; API returns 202 with status `queued`). Rate limiting fails open (WARNING log); token denylist check fails open (exposure bounded by access-token lifetime); webhook dedupe falls back to the DB unique index. `/health/ready` returns 503. Workers and beat reconnect automatically; the sweeper drains the backlog on recovery. |
| PostgreSQL unavailable | API returns 503 `DATABASE_UNAVAILABLE`; `/health/ready` 503. Workers retry DB errors (Celery autoretry, 5 tries, exponential). An execution left `running` is recovered by the reaper once the DB returns. No state is held only in memory. |

---

## 9. Trigger System

### 9.1 Trigger architecture

```python
class BaseTrigger(ABC):
    type: ClassVar[str]
    ConfigModel: ClassVar[type[BaseModel]]
    def validate(self, config: BaseModel, workflow: Workflow) -> None: ...
    def on_activate(self, session, workflow, version) -> None: ...    # e.g. create schedule row
    def on_deactivate(self, session, workflow) -> None: ...
```

Triggers are registered in `triggers/registry.py` (`TRIGGER_REGISTRY: dict[str, BaseTrigger]`). Adding a trigger = (1) new module with a subclass and config model, (2) register it, (3) add the enum value, (4) tests. The engine is trigger-agnostic: every trigger ends by calling `ExecutionService.create_and_enqueue(workflow, trigger_type, payload, triggered_by, idempotency_key)`.

### 9.2 Initial triggers

**Manual** — `config: {}`. Started via `POST /workflows/{id}/execute` with optional JSON `input` (becomes `trigger.payload`). `triggered_by` = caller.

**Schedule** — config:

| Field | Rules |
| --- | --- |
| `mode` | `once` or `cron` |
| `run_at` | required for `once`; ISO-8601 with offset; MUST be ≥30 s in the future at activation |
| `cron` | required for `cron`; standard 5-field expression validated by `croniter`; minimum interval 60 s (checked by computing the next 5 fire times) |
| `timezone` | IANA name validated via `zoneinfo`; default `UTC`. DST: nonexistent local times are skipped, ambiguous times fire once (first occurrence). |

One schedule row per workflow. `scheduler.tick` (every 15 s) selects `schedules WHERE is_active AND next_run_at <= now() FOR UPDATE SKIP LOCKED LIMIT 100`, creates an execution per due schedule (idempotency key above), computes the next `next_run_at` strictly after now, and for `once` sets `is_active=false` after firing. Missed runs during downtime are **not** replayed: only the most recent due occurrence runs, once, if it was due within the last 15 minutes; otherwise it is skipped and logged. `triggered_by` = workflow owner, `trigger_type=schedule`. Owner disabled or workflow not `active` → the schedule is skipped and deactivated.

**Webhook** — `config: {}`; secret generated on activation.

- Endpoint: `POST /api/v1/webhooks/{workflow_id}` (no JWT).
- **Authentication:** HMAC-SHA256. Headers: `X-FlowForge-Timestamp` (Unix seconds), `X-FlowForge-Signature: sha256=<hex>` over the string `{timestamp}.{raw_body}` using the webhook secret; `X-FlowForge-Delivery-Id` (UUID, required). Compare with `hmac.compare_digest`.
- **Replay protection:** timestamp within ±300 s of server time; delivery ID stored via Redis `SET NX EX 86400` (backed by the DB unique index). A duplicate delivery returns 200 with the original `execution_id` and `duplicate: true`; it does not run again.
- **Payload validation:** `Content-Type: application/json`; body ≤256 KB; must parse to a JSON object; otherwise 400 `MALFORMED_WEBHOOK` / 413 `PAYLOAD_TOO_LARGE`.
- **Rate limit:** 60 requests/min per workflow (Redis), 429 with `Retry-After`.
- **Responses:** 202 `{execution_id, status: queued}`; 401 `INVALID_SIGNATURE` / `WEBHOOK_TIMESTAMP_INVALID`; 404 `WEBHOOK_NOT_FOUND` for unknown, inactive or deleted workflow or disabled owner (identical body to prevent enumeration).
- The secret is shown once on creation/rotation (`POST /workflows/{id}/webhook/rotate-secret`), stored Fernet-encrypted (it must be recoverable for HMAC) with a visible `secret_prefix` (first 6 chars) for identification.

---

## 10. Action System

### 10.1 Architecture

```python
class BaseAction(ABC):
    type: ClassVar[str]
    ConfigModel: ClassVar[type[BaseModel]]       # validated AFTER template resolution
    def execute(self, config: BaseModel, ctx: ActionContext) -> dict: ...  # JSON-serialisable output

class RetryableActionError(Exception): ...        # carries error_code, message, retry_after
class PermanentActionError(Exception): ...
```

`ActionContext` provides: `owner_id`, `execution_id`, `step_id`, `session` (DB, for the database action), `logger` (bound with IDs), `integration_resolver` (decrypt on demand), `deadline`. Actions are registered in `actions/registry.py`; `GET /api/v1/actions` returns each action's type, label and JSON schema (from the Pydantic model) so the dashboard form can render dynamically. Adding an action = new module + registry entry + tests, with no engine change.

### 10.2 `http_request`

| Config | Rules |
| --- | --- |
| `method` | GET, POST, PUT, PATCH, DELETE |
| `url` | http/https only, ≤2048 chars, no userinfo (`user:pass@`) |
| `headers` | object ≤20 entries; forbidden: `Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Proxy-*`, and `Authorization` when `integration_id` is set |
| `query` | object of scalars/lists, appended and URL-encoded |
| `json_body` | any JSON ≤256 KB; sent as `application/json`; not allowed with GET |
| `integration_id` | optional; adds the auth header from the stored credential |
| `follow_redirects` | default false; if true max 3 hops, each hop re-validated by the SSRF guard |
| `expected_status` | optional list; default any 2xx. Others are errors |
| `extract` | optional map `name -> dotted path` into the parsed JSON body; result in `output.extracted` |

Timeout comes from the step's `timeout_seconds` (effective maximum 30 for HTTP).

**Output:** `{status_code, headers (allow-list: content-type, content-length, retry-after, etag), body, extracted}`. `body` is parsed JSON if the response is JSON, else UTF-8 text. The response is streamed with a hard 1 MB cap; exceeding it raises permanent `RESPONSE_TOO_LARGE`.

**Errors:** 5xx/429/408, network errors and timeouts are retryable; other unexpected statuses are permanent `HTTP_STATUS_UNEXPECTED` (status plus a 500-char sanitised body excerpt in `details`).

**SSRF guard:** mandatory for every outbound request including redirects. See SEC-SSRF in section 14.

### 10.3 `python_function`

Config: `function` (name from registry), `args` (object validated by the function's Pydantic model). Functions are ordinary callables decorated with `@register_function(name, ArgsModel)` in `actions/functions/`. They MUST be pure (no I/O; no imports of `os`, `subprocess`, `socket`, `requests`, `httpx`), deterministic where possible, and finish in <5 s. V1 built-ins: `text.upper`, `text.lower`, `text.slugify`, `text.truncate`, `math.sum`, `math.average`, `math.min_max`, `json.merge`, `json.get`, `list.unique`, `list.sort`, `list.count`, `date.now_iso`, `date.format`, `string.join`. A CI test asserts that no function module imports from the forbidden list. `GET /actions/python-functions` lists them with schemas. No endpoint or step field accepts source code.

### 10.4 `database`

Operates only on `user_data_records`. `owner_id` is injected by the engine from the workflow owner and can never be supplied by config. No raw SQL anywhere.

| Operation | Config | Output |
| --- | --- | --- |
| `insert` | `collection`, `data` (object ≤64 KB), optional `dedupe_key` (unique per owner+collection; duplicate returns the existing row, no error) | `{id, created}` |
| `find` | `collection`, `filters` (top-level key → scalar equality, ≤10 keys), `limit` (≤100, default 20), `order` (`created_at` / `-created_at`) | `{records, count}` |
| `update` | `collection`, `record_id`, `data` (shallow merge) | `{updated}` |
| `delete` | `collection`, `record_id` | `{deleted}` |

Collection regex `^[a-z][a-z0-9_]{0,39}$`. Quota 10,000 records per user (permanent `QUOTA_EXCEEDED`). Statement timeout 5 s.

### 10.5 `email`

Config: `to` (1–10 valid addresses), `subject` (≤200, no CR/LF), `body` (plain text ≤50 KB). Sent through system SMTP settings (STARTTLS by default) with stdlib `smtplib` and `EmailMessage`; CR/LF in headers is rejected explicitly. Per-user cap `EMAIL_DAILY_LIMIT_PER_USER` (default 100/day, counter in Redis) → permanent `EMAIL_QUOTA_EXCEEDED`. SMTP 4xx and connection errors are retryable; 5xx permanent. Output `{accepted: n}` only. Development Compose includes Mailpit.

### 10.6 `transform`

Config: `input` (usually a template resolving to an object or list of objects) and `operations` (ordered, ≤20). All operations are pure:

| `op` | Parameters | Behaviour |
| --- | --- | --- |
| `select` | `fields: [str]` | keep only listed keys (dotted paths allowed) |
| `rename` | `mapping: {old: new}` | rename keys |
| `filter` | `field`, `operator` (`eq ne gt gte lt lte in contains exists`), `value` | keep matching items (list input only) |
| `map_values` | `field`, `mapping`, optional `default` | replace values |
| `set` | `field`, `value` | set constant |
| `pick` | `path` | replace data with the value at path |

Output `{result}`. Type errors (e.g. `filter` on an object) are permanent `TRANSFORM_TYPE_ERROR`.

---

## 11. Background Job Architecture

```
FastAPI --commit row--> PostgreSQL
   |                        ^
   +--enqueue--> Redis --> Celery worker --> Workflow Engine --+
                  ^            ^                (state)--------+
   Celery Beat (scheduler.tick, outbox sweeper, reaper, cleanup)
```

### 11.1 Queues and tasks

| Queue | Task | Purpose | Notes |
| --- | --- | --- | --- |
| `executions` | `run_execution(execution_id)` | Runs or resumes one execution | `acks_late`, `reject_on_worker_lost`, `ignore_result` |
| `maintenance` | `scheduler.tick` | Fire due schedules | every 15 s |
| `maintenance` | `outbox.sweep` | Enqueue `queued` executions not yet enqueued | every 30 s |
| `maintenance` | `executions.reap` | Recover stale `running` executions | every 60 s |
| `maintenance` | `cleanup.run` | Delete executions/logs/audit older than retention; expired tokens | daily 03:00 UTC |

### 11.2 Celery configuration (binding)

- Broker: `CELERY_BROKER_URL` (Redis db 0). `CELERY_RESULT_BACKEND` (Redis db 2) is configured but tasks use `ignore_result=True`; PostgreSQL is the only result store. `result_expires=3600`.
- `task_acks_late=True`, `task_reject_on_worker_lost=True`, `worker_prefetch_multiplier=1`, `task_time_limit=150`, `task_soft_time_limit=120`, `broker_transport_options={'visibility_timeout': 1800}` (must exceed the longest countdown of 600 s; any resulting duplicate delivery is harmless because of the atomic claim).
- Worker: `celery -A app.tasks.celery_app worker -Q executions,maintenance -c ${WORKER_CONCURRENCY:-4} -l info`. Beat: `celery -A app.tasks.celery_app beat -l info`; exactly one beat instance.
- Infrastructure errors (`OperationalError`, Redis `ConnectionError`) use `autoretry_for`, `retry_backoff=True`, `retry_backoff_max=120`, `max_retries=5`. Business failures never use Celery retry; they use the engine retry in 8.4.
- Task IDs for `run_execution` are random; duplicate prevention relies on the claim, the idempotency keys and the unique indexes, not on task IDs.

### 11.3 Retry, dead-letter, cancellation

| Topic | Specification |
| --- | --- |
| Retry policy | Per step: `max_attempts` 1–5, exponential backoff with jitter (8.4). |
| Dead-letter | PostgreSQL is the DLQ. Permanently failed executions stay as `failed` rows with `error_code`; admins query them; users retry via `POST /executions/{id}/retry`. Redis holds no dead-letter queue. |
| Task timeout | See 8.5. |
| Cancellation | Cooperative via `cancel_requested`; no Celery `revoke(terminate=True)`. |
| Concurrency | Prefork pool, default 4 per worker container; scale with `docker compose up --scale worker=N`. |
| Idempotency | See 8.7. |

### 11.4 Redis vs PostgreSQL

| Data | Store | Key / table |
| --- | --- | --- |
| Executions, steps, logs, schedules, users, tokens, audit | PostgreSQL | tables in section 12 |
| Queue messages | Redis db 0 | Celery-managed |
| Rate-limit counters | Redis db 1 | `ff:rl:{scope}:{id}:{window}` (INCR + EXPIRE) |
| Access-token denylist | Redis db 1 | `ff:denylist:{jti}` (TTL = remaining lifetime) |
| Webhook delivery dedupe | Redis db 1 | `ff:wh:{workflow_id}:{delivery_id}` (24 h) |
| Worker heartbeat | Redis db 1 | `ff:worker:{hostname}` (TTL 30 s, refreshed every 10 s) |
| Email daily counter | Redis db 1 | `ff:email:{user_id}:{yyyymmdd}` |
| Caches | Redis db 1 | `ff:cache:admin_stats` (30 s); `ff:cache:wfv:{workflow_id}:{version}` (300 s; versions are immutable, so no invalidation needed) |

Rule: nothing in Redis may be required for correctness after a restart; each Redis use has a defined fail-open or DB-fallback behaviour (8.8).

---

## 12. Database Requirements

### 12.1 Conventions

- PostgreSQL 16. SQLAlchemy 2.0 declarative models with `Mapped[]` typing; Alembic migrations (autogenerate then review; one migration per phase minimum; never edit an applied migration).
- Primary keys are `UUID` (`uuid4`, server default `gen_random_uuid()`), except `execution_logs.id` (`BIGINT` identity) for ordered, cheap appends.
- All timestamps are `TIMESTAMPTZ`, stored in UTC; `created_at` default `now()`; `updated_at` maintained by ORM `onupdate`.
- Enums are `VARCHAR` with `CHECK` constraints (simpler to migrate than native enums).
- Foreign keys are indexed. Session per request (API) / per task slice (worker); services own transaction boundaries (`session.begin()`); repositories never commit.
- Connection pool: `pool_size=10`, `max_overflow=10`, `pool_pre_ping=True`, `pool_recycle=1800` (API); worker pool 5+5 per process.

### 12.2 Tables

**users**

| Column | Type | Constraints |
| --- | --- | --- |
| id | UUID | PK |
| email | VARCHAR(254) | NOT NULL, UNIQUE (stored lower-case) |
| password\_hash | VARCHAR(255) | NOT NULL |
| full\_name | VARCHAR(100) | NOT NULL |
| role | VARCHAR(10) | NOT NULL, default `user`, CHECK in (`user`,`admin`) |
| is\_active | BOOLEAN | NOT NULL, default true |
| failed\_login\_count | INT | NOT NULL, default 0 |
| locked\_until | TIMESTAMPTZ | NULL |
| last\_login\_at | TIMESTAMPTZ | NULL |
| created\_at, updated\_at | TIMESTAMPTZ | NOT NULL |

**refresh\_tokens** — `id` UUID PK; `user_id` UUID FK users ON DELETE CASCADE NOT NULL; `family_id` UUID NOT NULL; `token_hash` CHAR(64) NOT NULL UNIQUE; `expires_at` TIMESTAMPTZ NOT NULL; `revoked_at` TIMESTAMPTZ NULL; `replaced_by_id` UUID NULL FK self; `created_ip` INET NULL; `user_agent` VARCHAR(255) NULL; `created_at`. Indexes: `(user_id)`, `(family_id)`.

**password\_reset\_tokens** — `id` UUID PK; `user_id` FK CASCADE NOT NULL; `token_hash` CHAR(64) NOT NULL UNIQUE; `expires_at` NOT NULL; `used_at` NULL; `created_at`. Index `(user_id)`.

**workflows**

| Column | Type | Constraints |
| --- | --- | --- |
| id | UUID | PK |
| owner\_id | UUID | FK users ON DELETE RESTRICT, NOT NULL |
| name | VARCHAR(120) | NOT NULL |
| description | TEXT | NULL (≤1000 enforced in app) |
| status | VARCHAR(10) | NOT NULL, default `draft`, CHECK in (`draft`,`active`,`inactive`) |
| version | INT | NOT NULL, default 1 (current version number) |
| trigger\_type | VARCHAR(20) | NOT NULL (denormalised from current definition for filtering) |
| deleted\_at | TIMESTAMPTZ | NULL |
| created\_at, updated\_at | TIMESTAMPTZ | NOT NULL |

Indexes: UNIQUE `(owner_id, lower(name)) WHERE deleted_at IS NULL`; `(owner_id, status) WHERE deleted_at IS NULL`; `(owner_id, updated_at DESC) WHERE deleted_at IS NULL`.

**workflow\_versions** — `id` UUID PK; `workflow_id` FK workflows CASCADE NOT NULL; `version` INT NOT NULL; `definition` JSONB NOT NULL; `definition_hash` CHAR(64) NOT NULL; `created_by` UUID FK users NOT NULL; `created_at`. UNIQUE `(workflow_id, version)`.

**workflow\_executions**

| Column | Type | Constraints |
| --- | --- | --- |
| id | UUID | PK |
| workflow\_id | UUID | FK workflows RESTRICT, NOT NULL |
| workflow\_version | INT | NOT NULL |
| owner\_id | UUID | FK users, NOT NULL (denormalised for filtering/authz) |
| triggered\_by\_user\_id | UUID | FK users, NULL (null for schedule/webhook) |
| trigger\_type | VARCHAR(20) | NOT NULL, CHECK (`manual`,`schedule`,`webhook`) |
| trigger\_payload | JSONB | NOT NULL, default `{}` |
| status | VARCHAR(20) | NOT NULL, default `queued`, CHECK per 8.3 |
| idempotency\_key | VARCHAR(128) | NULL |
| retry\_of\_execution\_id | UUID | NULL, FK self |
| current\_step\_id | VARCHAR(40) | NULL |
| failed\_step\_id | VARCHAR(40) | NULL |
| retry\_count | INT | NOT NULL, default 0 (sum of step retries) |
| recovery\_count | INT | NOT NULL, default 0 |
| cancel\_requested | BOOLEAN | NOT NULL, default false |
| error\_code | VARCHAR(64) | NULL |
| error\_message | VARCHAR(500) | NULL (sanitised) |
| queued\_at | TIMESTAMPTZ | NOT NULL, default now() |
| enqueued\_at, next\_attempt\_at, started\_at, finished\_at, heartbeat\_at, deadline\_at | TIMESTAMPTZ | NULL |
| duration\_ms | INT | NULL |
| worker\_id | VARCHAR(100) | NULL |
| request\_id | VARCHAR(64) | NULL |
| created\_at | TIMESTAMPTZ | NOT NULL |

Indexes: `(owner_id, created_at DESC)`; `(workflow_id, created_at DESC)`; `(status, next_attempt_at)`; partial `(queued_at) WHERE status='queued'` (sweeper); partial `(heartbeat_at) WHERE status='running'` (reaper); UNIQUE `(workflow_id, idempotency_key) WHERE idempotency_key IS NOT NULL`.

**step\_executions** — `id` UUID PK; `execution_id` FK CASCADE NOT NULL; `step_id` VARCHAR(40) NOT NULL; `step_index` INT NOT NULL; `action_type` VARCHAR(30) NOT NULL; `status` VARCHAR(20) NOT NULL default `pending`; `retry_count` INT NOT NULL default 0 (attempts = retry\_count + 1); `input_meta` JSONB NULL (action, URL host and method, key names, byte sizes; never payloads); `output` JSONB NULL; `output_meta` JSONB NULL (size, status\_code, keys); `error_code` VARCHAR(64) NULL; `error_message` VARCHAR(500) NULL; `error_details` JSONB NULL (sanitised); `next_attempt_at`, `started_at`, `finished_at` TIMESTAMPTZ NULL; `duration_ms` INT NULL; `created_at`. UNIQUE `(execution_id, step_id)`; index `(execution_id, step_index)`. Rows for all steps are pre-created as `pending` when the execution is created.

**execution\_logs** — `id` BIGINT identity PK; `execution_id` FK CASCADE NOT NULL; `step_execution_id` FK SET NULL NULL; `level` VARCHAR(8) NOT NULL; `message` VARCHAR(1000) NOT NULL; `context` JSONB NULL (metadata only); `request_id` VARCHAR(64) NULL; `created_at` NOT NULL. Index `(execution_id, id)`.

**integrations** — `id` UUID PK; `owner_id` FK users CASCADE NOT NULL; `name` VARCHAR(100) NOT NULL; `type` VARCHAR(30) NOT NULL CHECK in (`http_bearer`,`http_header_api_key`,`http_basic`); `credentials_encrypted` TEXT NOT NULL (Fernet token); `credential_fields` JSONB NOT NULL (field names only); `allowed_hosts` JSONB NULL; `created_at`, `updated_at`. UNIQUE `(owner_id, lower(name))`.

**schedules** — `id` UUID PK; `workflow_id` FK CASCADE NOT NULL UNIQUE; `mode` VARCHAR(10) CHECK (`once`,`cron`); `cron_expression` VARCHAR(100) NULL; `run_at` TIMESTAMPTZ NULL; `timezone` VARCHAR(64) NOT NULL default `UTC`; `next_run_at` TIMESTAMPTZ NULL; `last_run_at` TIMESTAMPTZ NULL; `is_active` BOOLEAN NOT NULL default true; `created_at`, `updated_at`. Partial index `(next_run_at) WHERE is_active`.

**webhook\_configs** — `id` UUID PK; `workflow_id` FK CASCADE NOT NULL UNIQUE; `secret_encrypted` TEXT NOT NULL; `secret_prefix` VARCHAR(8) NOT NULL; `is_active` BOOLEAN NOT NULL default true; `rotated_at` NULL; `last_delivery_at` NULL; `created_at`.

**audit\_logs** — `id` UUID PK; `actor_user_id` UUID FK users ON DELETE SET NULL NULL; `actor_role` VARCHAR(10) NULL; `action` VARCHAR(64) NOT NULL (e.g. `auth.login`); `resource_type` VARCHAR(40) NULL; `resource_id` VARCHAR(64) NULL; `outcome` VARCHAR(10) NOT NULL CHECK (`success`,`failure`); `ip` INET NULL; `user_agent` VARCHAR(255) NULL; `request_id` VARCHAR(64) NULL; `metadata` JSONB NOT NULL default `{}` (no secrets); `created_at` NOT NULL. Indexes `(actor_user_id, created_at DESC)`, `(action, created_at DESC)`, `(resource_type, resource_id)`. Append-only: no code path updates or deletes rows except the retention task.

**user\_data\_records** — `id` UUID PK; `owner_id` FK users CASCADE NOT NULL; `collection` VARCHAR(40) NOT NULL; `data` JSONB NOT NULL; `dedupe_key` VARCHAR(128) NULL; `created_at`, `updated_at`. UNIQUE `(owner_id, collection, dedupe_key) WHERE dedupe_key IS NOT NULL`; index `(owner_id, collection, created_at DESC)`.

**system\_settings** — `key` VARCHAR(64) PK; `value` JSONB NOT NULL; `updated_by` UUID FK users NULL; `updated_at`. Seeded by migration: `registration_enabled=true`, `max_workflows_per_user=100`, `max_active_workflows_per_user=25`, `execution_retention_days=90`, `audit_retention_days=365`.

### 12.3 Normalisation decisions

- 3NF for users, tokens, integrations, schedules, webhooks. Deliberate denormalisation: `workflows.trigger_type` (filter without parsing JSONB), `workflow_executions.owner_id` (authz and filtering without joins), `workflow_executions.workflow_version` (pin).
- Definitions are JSONB snapshots (D-03), the only practical way to keep immutable history.
- `step_executions` rows are pre-created per execution so progress is visible and the unique `(execution_id, step_id)` constraint serialises state.
- Retention: nightly cleanup deletes executions older than `execution_retention_days` (cascade to steps/logs) and audit rows older than `audit_retention_days`.

### 12.4 ERD

```mermaid
erDiagram
  USERS ||--o{ REFRESH_TOKENS : has
  USERS ||--o{ PASSWORD_RESET_TOKENS : has
  USERS ||--o{ WORKFLOWS : owns
  USERS ||--o{ INTEGRATIONS : owns
  USERS ||--o{ USER_DATA_RECORDS : owns
  USERS ||--o{ AUDIT_LOGS : performs
  WORKFLOWS ||--|{ WORKFLOW_VERSIONS : versions
  WORKFLOWS ||--o| SCHEDULES : has
  WORKFLOWS ||--o| WEBHOOK_CONFIGS : has
  WORKFLOWS ||--o{ WORKFLOW_EXECUTIONS : runs
  USERS ||--o{ WORKFLOW_EXECUTIONS : owns
  WORKFLOW_EXECUTIONS ||--|{ STEP_EXECUTIONS : contains
  WORKFLOW_EXECUTIONS ||--o{ EXECUTION_LOGS : logs
  STEP_EXECUTIONS ||--o{ EXECUTION_LOGS : emits
  WORKFLOW_EXECUTIONS |o--o| WORKFLOW_EXECUTIONS : retry_of
  USERS ||--o{ SYSTEM_SETTINGS : updates
```

---

## 13. API Specification

### 13.1 Conventions

- Base path `/api/v1`. JSON only (`Content-Type: application/json`). Timestamps ISO-8601 UTC (`2026-10-31T09:00:00Z`); IDs are UUID strings. Request models use `extra='forbid'` (unknown fields → 422).
- **Auth header:** `Authorization: Bearer <access_token>` on every endpoint except those marked *public*. **Request ID:** client MAY send `X-Request-ID` (≤64 chars, else replaced); the server always returns it, and includes it in error bodies and logs.
- **Pagination** (list endpoints): query `page` (≥1, default 1), `page_size` (1–100, default 20). Response: `{ "items": [...], "total": 42, "page": 1, "page_size": 20 }`.
- **Rate-limit headers:** `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`; on 429 also `Retry-After`.
- **Docs:** OpenAPI at `/openapi.json`, Swagger UI at `/docs`; disabled when `ENABLE_DOCS=false` (production default).
- Global request body cap 1 MB (webhook 256 KB; workflow definition 128 KB). Violations → 413 `PAYLOAD_TOO_LARGE`.
- Every 4xx/5xx uses the error envelope in 13.2. Every mutating endpoint writes an audit entry where listed in section 18.4.

### 13.2 Error format

```json
{
  "error": {
    "code": "WORKFLOW_NOT_FOUND",
    "message": "Workflow was not found.",
    "details": null,
    "request_id": "3f1c2a52-9c1e-4c0e-8a55-0b6f3f2a9d11"
  }
}
```

`details` is `null` or, for 422, a list `[{"loc": ["body","steps",0,"id"], "msg": "...", "code": "STEP_ID_INVALID"}]`. Messages are human-readable, stable, and never contain stack traces, SQL, file paths or secrets.

| Category | HTTP | Codes (non-exhaustive) |
| --- | --- | --- |
| Validation | 422 | `VALIDATION_ERROR` and the specific codes in 7.2.1 |
| Bad request | 400 | `MALFORMED_WEBHOOK`, `RESET_TOKEN_INVALID`, `INVALID_PAGINATION` |
| Authentication | 401 | `INVALID_CREDENTIALS`, `TOKEN_EXPIRED`, `TOKEN_INVALID`, `TOKEN_REVOKED`, `REFRESH_TOKEN_INVALID`, `REFRESH_TOKEN_EXPIRED`, `REFRESH_TOKEN_REUSED`, `INVALID_SIGNATURE`, `WEBHOOK_TIMESTAMP_INVALID` |
| Authorization | 403 | `FORBIDDEN`, `ACCOUNT_DISABLED`, `REGISTRATION_DISABLED` |
| Not found | 404 | `WORKFLOW_NOT_FOUND`, `EXECUTION_NOT_FOUND`, `INTEGRATION_NOT_FOUND`, `USER_NOT_FOUND`, `WEBHOOK_NOT_FOUND`, `VERSION_NOT_FOUND` |
| Conflict | 409 | `EMAIL_ALREADY_REGISTERED`, `WORKFLOW_NAME_EXISTS`, `WORKFLOW_NOT_ACTIVE`, `WORKFLOW_LIMIT_REACHED`, `VERSION_CONFLICT`, `INTEGRATION_IN_USE`, `EXECUTION_NOT_RETRYABLE`, `EXECUTION_ALREADY_FINISHED`, `INTEGRATION_NAME_EXISTS` |
| Too large | 413 | `PAYLOAD_TOO_LARGE`, `DEFINITION_TOO_LARGE` |
| Rate limited | 429 | `RATE_LIMITED`, `ACCOUNT_LOCKED`, `WORKFLOW_CONCURRENCY_LIMIT` |
| Server | 500 | `INTERNAL_ERROR` (generic message; details only in logs) |
| Unavailable | 503 | `DATABASE_UNAVAILABLE`, `SERVICE_UNAVAILABLE` |

**Handling rules:** a single set of FastAPI exception handlers maps `AppError` subclasses (each carries `code`, `http_status`, `message`), `RequestValidationError`, `HTTPException`, SQLAlchemy `OperationalError`/`DBAPIError` (→ 503 or 500, never leaking SQL), and bare `Exception` (→ 500 `INTERNAL_ERROR`, logged at ERROR with stack trace and request ID). **Worker and external errors** are not API errors: they are recorded on `step_executions`/`workflow_executions` as `error_code` values such as `HTTP_STATUS_UNEXPECTED`, `STEP_TIMEOUT`, `RETRIES_EXHAUSTED`, `WORKER_LOST`, `SSRF_BLOCKED`, `TEMPLATE_RESOLUTION_ERROR`, `STEP_CONFIG_INVALID`, `OUTPUT_TOO_LARGE`, `RESPONSE_TOO_LARGE`, `QUOTA_EXCEEDED`, `EMAIL_QUOTA_EXCEEDED`, `TRANSFORM_TYPE_ERROR`, `UNKNOWN_FUNCTION`, `INTERNAL_ENGINE_ERROR`, and surfaced through execution detail endpoints.

### 13.3 Endpoint catalogue

Columns: **Auth** = `public`, `user` (any valid JWT; ownership enforced), or `admin`. Unless stated, errors always also include 401 (missing/invalid token), 422 (validation), 429 (rate limit), 500.

#### Authentication & profile

| Method & URL | Purpose | Auth | Success | Endpoint-specific errors | Rate limit |
| --- | --- | --- | --- | --- | --- |
| `POST /auth/register` | Create account | public | 201 `UserOut` | 403 `REGISTRATION_DISABLED`, 409 `EMAIL_ALREADY_REGISTERED` | 5/hour/IP |
| `POST /auth/login` | Obtain tokens | public | 200 `TokenPair` | 401 `INVALID_CREDENTIALS`, 403 `ACCOUNT_DISABLED`, 429 `ACCOUNT_LOCKED` | 10/min/IP and 5/min/email |
| `POST /auth/refresh` | Rotate refresh token, new access token | public | 200 `TokenPair` | 401 `REFRESH_TOKEN_INVALID` / `_EXPIRED` / `_REUSED`, 403 `ACCOUNT_DISABLED` | 30/min/IP |
| `POST /auth/logout` | Revoke refresh family, denylist access token | user | 204 | — (idempotent) | 30/min/user |
| `POST /auth/password-reset/request` | Email reset token | public | 202 (always) | — | 3/hour/email, 10/hour/IP |
| `POST /auth/password-reset/confirm` | Set new password | public | 204 | 400 `RESET_TOKEN_INVALID` | 10/hour/IP |
| `GET /users/me` | Own profile | user | 200 `UserOut` | — | general |
| `PATCH /users/me` | Update `full_name` | user | 200 `UserOut` | — | general |
| `POST /users/me/change-password` | Change password | user | 204 | 401 `INVALID_CREDENTIALS` (wrong current password) | 5/hour/user |

#### Workflows

| Method & URL | Purpose | Auth | Success | Endpoint-specific errors | Rate limit |
| --- | --- | --- | --- | --- | --- |
| `POST /workflows` | Create (draft) | user | 201 `WorkflowOut` | 409 `WORKFLOW_NAME_EXISTS`, `WORKFLOW_LIMIT_REACHED`; 413/422 definition errors | 30/hour/user |
| `GET /workflows` | List/search own. Query: `status`, `trigger_type`, `q`, `sort`, `page`, `page_size` | user | 200 paginated `WorkflowSummary` | 422 invalid filter | general |
| `GET /workflows/{id}` | Detail incl. current definition | user | 200 `WorkflowOut` | 404 `WORKFLOW_NOT_FOUND` | general |
| `PUT /workflows/{id}` | Replace name/description/definition; optional `expected_version` | user | 200 `WorkflowOut` | 404; 409 `VERSION_CONFLICT`, `WORKFLOW_NAME_EXISTS`; 422 | 60/hour/user |
| `DELETE /workflows/{id}` | Soft delete | user | 204 | 404 | 30/hour/user |
| `POST /workflows/{id}/activate` | Validate and activate | user | 200 `WorkflowOut` | 404; 409 `WORKFLOW_LIMIT_REACHED`; 422 validation | 30/hour/user |
| `POST /workflows/{id}/deactivate` | Deactivate | user | 200 `WorkflowOut` | 404 | 30/hour/user |
| `POST /workflows/{id}/clone` | Clone as draft | user | 201 `WorkflowOut` | 404; 409 `WORKFLOW_LIMIT_REACHED` | 30/hour/user |
| `POST /workflows/{id}/execute` | Manual run. Body `{ "input": {...} }` (optional, ≤256 KB). Header `Idempotency-Key` optional | user | 202 `ExecutionOut` (200 with original on idempotent repeat) | 404; 409 `WORKFLOW_NOT_ACTIVE`; 429 `WORKFLOW_CONCURRENCY_LIMIT` | 20/min/user |
| `POST /workflows/validate` | Validate a definition without saving | user | 200 `{valid: bool, errors: [...]}` | — | 60/min/user |
| `GET /workflows/{id}/versions` | Version history (paginated) | user | 200 | 404 | general |
| `GET /workflows/{id}/versions/{n}` | One version snapshot | user | 200 | 404 `VERSION_NOT_FOUND` | general |
| `GET /workflows/{id}/webhook` | Webhook info (URL, `secret_prefix`, status); no secret | user | 200 | 404 `WEBHOOK_NOT_FOUND` if trigger isn't webhook | general |
| `POST /workflows/{id}/webhook/rotate-secret` | New secret, shown once | user | 200 `{secret, secret_prefix}` | 404; 409 if trigger isn't webhook | 10/hour/user |

#### Executions

| Method & URL | Purpose | Auth | Success | Endpoint-specific errors | Rate limit |
| --- | --- | --- | --- | --- | --- |
| `GET /executions` | List own. Query: `workflow_id`, `status`, `trigger_type`, `created_from`, `created_to`, `sort` (`created_at`/`-created_at`), pagination | user | 200 paginated `ExecutionSummary` | 422 | general |
| `GET /executions/{id}` | Detail with ordered `steps[]` (outputs redacted per 8.2) | user | 200 `ExecutionDetail` | 404 `EXECUTION_NOT_FOUND` | general |
| `POST /executions/{id}/retry` | New execution re-running the same version and payload. Header `Idempotency-Key` optional | user | 202 `ExecutionOut` | 404; 409 `EXECUTION_NOT_RETRYABLE` (only `failed`/`timed_out`), `WORKFLOW_NOT_ACTIVE`; 429 concurrency | 20/min/user |
| `POST /executions/{id}/cancel` | Request cancellation | user | 200 `ExecutionOut` | 404; 409 `EXECUTION_ALREADY_FINISHED` | 30/min/user |
| `GET /executions/{id}/logs` | Log entries. Query: `level` (min level), `step_id`, `after_id` (cursor), `limit` (1–500, default 100) | user | 200 `{items, next_after_id}` | 404 | general |

#### Webhook

| Method & URL | Purpose | Auth | Success | Endpoint-specific errors | Rate limit |
| --- | --- | --- | --- | --- | --- |
| `POST /webhooks/{workflow_id}` | Receive external event; see 9.2 for headers and signing | public (HMAC) | 202 `{execution_id, status}`; 200 `{execution_id, duplicate: true}` | 400 `MALFORMED_WEBHOOK`; 401 `INVALID_SIGNATURE` / `WEBHOOK_TIMESTAMP_INVALID`; 404 `WEBHOOK_NOT_FOUND`; 413; 429 | 60/min/workflow |

#### Integrations & catalogue

| Method & URL | Purpose | Auth | Success | Endpoint-specific errors | Rate limit |
| --- | --- | --- | --- | --- | --- |
| `POST /integrations` | Create; body `{name, type, credentials{...}, allowed_hosts?}` | user | 201 `IntegrationOut` (no secrets) | 409 `INTEGRATION_NAME_EXISTS`; 422 | 30/hour/user |
| `GET /integrations` | List own (paginated) | user | 200 | — | general |
| `GET /integrations/{id}` | Detail | user | 200 | 404 `INTEGRATION_NOT_FOUND` | general |
| `PUT /integrations/{id}` | Update name/hosts; `credentials` optional (replaces if present) | user | 200 | 404; 409 name | 60/hour/user |
| `DELETE /integrations/{id}` | Delete | user | 204 | 404; 409 `INTEGRATION_IN_USE` | 30/hour/user |
| `GET /actions` | Action types + JSON schemas | user | 200 | — | general |
| `GET /actions/python-functions` | Registered functions + arg schemas | user | 200 | — | general |

#### Admin (all require `admin`; non-admin gets 403 `FORBIDDEN`)

| Method & URL | Purpose | Success | Notes |
| --- | --- | --- | --- |
| `GET /admin/users` | List users; query `q` (email/name), `role`, `is_active`, pagination | 200 paginated | 404-free |
| `GET /admin/users/{id}` | User detail + counts | 200 | 404 `USER_NOT_FOUND` |
| `PATCH /admin/users/{id}` | Body `{is_active?, role?}`; cannot target self for disable/demote (409 `FORBIDDEN_SELF_CHANGE`) | 200 | audited; disabling follows FR-AUTH-08 |
| `GET /admin/executions` | All executions; filters `status`, `owner_id`, `workflow_id`, `error_code`, dates; metadata only (no payloads/outputs) | 200 paginated | includes the dead-letter view (`status=failed`) |
| `POST /admin/executions/{id}/cancel` | Cancel any execution | 200 | audited |
| `GET /admin/stats` | Totals: users, workflows by status, executions by status (24 h / 7 d), failure rate, queue depth (`queued` count), avg duration | 200 | cached 30 s |
| `GET /admin/workers` | Live workers from Redis heartbeats + Celery `inspect` stats (active tasks, concurrency, last seen) | 200 | degraded flag if Redis down |
| `GET /admin/settings` | All system settings | 200 | — |
| `PUT /admin/settings` | Update known keys only (unknown key → 422) | 200 | audited |
| `GET /admin/audit-logs` | Filter by `actor_user_id`, `action`, dates, pagination | 200 | read-only |

#### Health (root path, no auth, not rate limited)

| URL | Behaviour |
| --- | --- |
| `GET /health` | Liveness: process is up. 200 `{status:"ok"}`. No dependency checks. |
| `GET /health/ready` | Readiness: `SELECT 1` on PostgreSQL, `PING` on Redis, Alembic revision equals head. 200 `{status:"ready", checks:{database:"ok", redis:"ok", migrations:"ok"}}`; otherwise 503 with the failing check named. Worker presence is reported as informational `workers: n`, never failing readiness. |

### 13.4 Key schemas

- `UserOut`: `id, email, full_name, role, is_active, created_at`.
- `TokenPair`: `access_token, refresh_token, token_type="bearer", expires_in` (seconds).
- `WorkflowOut`: `id, owner_id, name, description, status, version, trigger_type, definition, created_at, updated_at`. `WorkflowSummary` omits `definition`, adds `step_count`.
- `ExecutionOut`: `id, workflow_id, workflow_version, trigger_type, status, current_step_id, retry_count, error_code, error_message, queued_at, started_at, finished_at, duration_ms`.
- `ExecutionDetail`: `ExecutionOut` + `triggered_by_user_id, trigger_payload (redacted), retry_of_execution_id, failed_step_id, steps: [StepOut]`. `StepOut`: `step_id, step_index, action_type, status, retry_count, input_meta, output (redacted), output_meta, error_code, error_message, started_at, finished_at, duration_ms`.
- `LogOut`: `id, level, message, step_id, context, created_at`.

### 13.5 Representative examples

**Login**

```json
POST /api/v1/auth/login
{ "email": "rajshekhar@example.com", "password": "correct-horse-battery" }

200 OK
{ "access_token": "eyJhbGciOi...", "refresh_token": "Zk3x...", "token_type": "bearer", "expires_in": 900 }
```

**Create workflow**

```json
POST /api/v1/workflows
{ "name": "Daily user digest", "description": "Fetch users and email a count",
  "definition": { "trigger": { "type": "manual", "config": {} }, "variables": {}, "settings": { "timeout_seconds": 300 },
    "steps": [ { "id": "fetch", "name": "Fetch", "action": "http_request",
                 "config": { "method": "GET", "url": "https://api.example.com/users" } } ] } }

201 Created
{ "id": "0d9c...", "name": "Daily user digest", "status": "draft", "version": 1, "trigger_type": "manual", "created_at": "2026-10-31T09:00:00Z", ... }
```

**Execute**

```json
POST /api/v1/workflows/0d9c.../execute        Idempotency-Key: run-2026-10-31-a
{ "input": { "note": "manual test" } }

202 Accepted
{ "id": "b71e...", "workflow_id": "0d9c...", "workflow_version": 1, "trigger_type": "manual", "status": "queued",
  "retry_count": 0, "queued_at": "2026-10-31T09:01:00Z", "started_at": null, "finished_at": null }
```

**Execution detail (failed)**

```json
200 OK
{ "id": "b71e...", "status": "failed", "failed_step_id": "fetch", "error_code": "RETRIES_EXHAUSTED",
  "steps": [ { "step_id": "fetch", "status": "failed", "retry_count": 2, "error_code": "RETRIES_EXHAUSTED",
               "error_message": "HTTP 503 from api.example.com after 3 attempts", "duration_ms": 21450 } ] }
```

**Webhook call**

```
POST /api/v1/webhooks/0d9c...
X-FlowForge-Timestamp: 1793437200
X-FlowForge-Delivery-Id: 6f1f1c7e-0c88-4b0a-bb2b-9a3f5d2a7a10
X-FlowForge-Signature: sha256=<hex hmac of "1793437200." + raw body>
{ "event": "order.created", "order_id": 981 }

202 Accepted  { "execution_id": "c3a4...", "status": "queued" }
```

### 13.6 Rate limiting

Implementation: Redis fixed-window counters. Key `ff:rl:{scope}:{identity}:{window_start}`; `INCR`, and `EXPIRE` = window + 1 s when the result is 1 (atomic via pipeline). Identity is user ID for authenticated routes, client IP (from `X-Forwarded-For` only when `TRUSTED_PROXY_COUNT` > 0) for public routes, workflow ID for webhooks. Redis errors fail open with a WARNING log (8.8).

| Scope | Limit |
| --- | --- |
| Authentication (login / register / refresh / reset) | per table in 13.3 |
| Workflow create / update / delete / activate | 30–60 per hour per user (13.3) |
| Manual execute and retry | 20 per minute per user |
| Webhook | 60 per minute per workflow |
| All other authenticated API requests | 300 per minute per user |
| All other unauthenticated requests | 60 per minute per IP |

---

## 14. Security Requirements

| ID | Area | Requirement |
| --- | --- | --- |
| SEC-01 | Password hashing | Argon2id per FR-AUTH-02; plaintext passwords are never logged, stored or returned; max length 128 to bound hashing cost. |
| SEC-02 | JWT | HS256 with `JWT_SECRET_KEY` ≥32 random bytes; app MUST refuse to start outside `ENVIRONMENT=development` if the secret is missing, shorter than 32 chars, or equals the example value. Verify `alg` explicitly (reject `none`); required claims `sub, exp, iat, jti, type`; 30 s clock-skew leeway max. |
| SEC-03 | Refresh tokens | Opaque, hashed at rest, rotated on use, reuse → family revoked, 7-day expiry, cleanup of expired rows daily. |
| SEC-04 | Token invalidation | Logout/disable/password change revoke refresh tokens; access tokens expire in 15 min and are denylisted on logout. |
| SEC-05 | RBAC | `require_admin` dependency for all `/admin/*`; ownership filter applied in repository queries (`WHERE owner_id = :user`), so a missing check cannot leak data; cross-user access returns 404. Tests MUST cover each endpoint with a second user. |
| SEC-06 | CORS | `CORS_ORIGINS` explicit comma-separated allow-list; never `*` together with credentials; methods and headers restricted to those used. |
| SEC-07 | CSRF | Not applicable to the API because authentication uses an `Authorization` header and no auth cookies (D-18). If cookies are ever introduced, SameSite=Strict plus CSRF tokens become mandatory. |
| SEC-08 | SQL injection | ORM or bound parameters only. String-built SQL is prohibited; CI runs `ruff` rule `S608` and `bandit`. The database action uses ORM expressions with whitelisted collection names and JSONB containment operators, never concatenation. |
| SEC-09 | Command injection | No `subprocess`, `os.system`, `eval`, `exec`, `pickle` loading of untrusted data, or `yaml.load` in application code. Celery serialiser is JSON only (`task_serializer='json'`, `accept_content=['json']`). Enforced by bandit in CI. |
| SEC-10 | Input validation | Pydantic v2 models on every request, `extra='forbid'`, length/range limits as in this SRS, UUID path params validated, body-size middleware. |
| SEC-11 | Output safety | API returns JSON only; error bodies are sanitised; redaction of sensitive keys (8.2); the dashboard never uses `dangerouslySetInnerHTML`. |
| SEC-12 | Security headers | API: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on auth routes, `Strict-Transport-Security` when `ENVIRONMENT=production`. Frontend (nginx): same plus `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'`. |
| SEC-13 | Secrets | Only from environment variables / Docker secrets; `.env` is git-ignored; `.env.example` holds placeholders; `pydantic-settings` validates at startup; `gitleaks` runs in CI. |
| SEC-14 | Encryption at rest | Integration credentials and webhook secrets use Fernet via `MultiFernet` (`ENCRYPTION_KEY` accepts comma-separated keys, first encrypts, all decrypt → enables rotation). |
| SEC-15 | Audit logging | Section 18.4. |
| SEC-16 | Dependencies | Versions pinned via `uv.lock`; `pip-audit` and Dependabot weekly; Trivy image scan; fail CI on HIGH/CRITICAL with a fix available. |
| SEC-17 | Docker | Non-root user (UID 10001), slim base image pinned by minor version, multi-stage build, no secrets baked into images, `.dockerignore`, `cap_drop: [ALL]`, `no-new-privileges`, read-only root filesystem for api/worker with a tmpfs `/tmp`, Postgres/Redis not published to the host in the production-style compose file. |
| SEC-18 | Webhooks | HMAC-SHA256 with timestamp, delivery-ID replay protection, constant-time compare, size cap, rate limit, indistinguishable 404s (9.2). |
| SEC-19 | Rate limiting | 13.6. |
| SEC-20 | Error disclosure | No stack traces, SQL, internal hostnames or library versions in responses (13.2). |

### 14.1 SSRF protection for `http_request` (SEC-SSRF)

All outbound HTTP from workflows MUST go through a single `SafeHttpClient` wrapper; direct use of `httpx`/`requests` elsewhere in `actions/` is a CI failure (test greps the package).

1. **Scheme/port allow-list:** `http`, `https`; ports 80, 443, 8080, 8443 only. Reject userinfo in URLs.
2. **Hostname deny-list:** `localhost`, `*.localhost`, `*.local`, `*.internal`, `*.lan`, `metadata.google.internal`, and bare single-label hostnames (e.g. `redis`, `postgres`, `api`) — these are Docker-network service names.
3. **Resolve first, validate every address:** resolve the hostname with `getaddrinfo` (A and AAAA), and reject if ANY returned address is in: `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16` (link-local, includes cloud metadata `169.254.169.254` and AWS IPv6 `fd00:ec2::254`), `100.64.0.0/10`, `0.0.0.0/8`, `224.0.0.0/4`, `240.0.0.0/4`, `::1/128`, `::/128`, `fc00::/7`, `fe80::/10`, `ff00::/8`, and IPv4-mapped/6to4/NAT64 forms of any of the above. Use `ipaddress` properties (`is_private`, `is_loopback`, `is_link_local`, `is_reserved`, `is_multicast`, `is_unspecified`) plus the explicit list. Literal-IP URLs (including decimal/octal/hex encodings, which `ipaddress`/`getaddrinfo` normalise) go through the same check.
4. **Defeat DNS rebinding:** connect to the validated IP (custom httpx transport or resolver that returns only the vetted address) while sending the original `Host` header and SNI; never resolve a second time.
5. **Redirects:** disabled by default; when enabled, ≤3 hops and each hop repeats steps 1–4. Redirects to non-http(s) schemes are rejected.
6. **Limits:** timeout ≤30 s, response ≤1 MB streamed, request body ≤256 KB, no proxy environment variables honoured (`trust_env=False`).
7. **Credential scope:** if the integration has `allowed_hosts`, the URL host MUST match; otherwise the credential is not attached and the step fails `SSRF_BLOCKED`/`INTEGRATION_HOST_MISMATCH`.
8. **Override flag:** `ALLOW_PRIVATE_NETWORK_REQUESTS` defaults to `false`; it exists only so integration tests can reach a local mock server, and the app MUST refuse to start with it `true` when `ENVIRONMENT=production`.
9. **Logging:** blocked attempts log WARNING (`ssrf_blocked`, host, reason, execution ID, no payloads) and are visible in audit logs as `execution.ssrf_blocked`.
10. **Tests (mandatory):** localhost, `127.0.0.1`, `[::1]`, `0.0.0.0`, `10.x`, `172.16.x`, `192.168.x`, `169.254.169.254`, `metadata.google.internal`, hostnames resolving to private IPs, decimal-encoded IPs (`2130706433`), IPv4-mapped IPv6, redirect to private IP, DNS rebinding simulation, Docker service names.

---

## 15. Architecture

### 15.1 Style and rationale

A **layered modular monolith** with one deployable backend image used by three processes (`api`, `worker`, `scheduler`). Layers are strict; imports flow downward only. This was chosen over microservices (operational cost with no benefit at this scale) and over full hexagonal/DDD (too many abstractions for a CRUD-plus-engine system). The workflow engine is a plain Python package with no FastAPI or Celery imports, so it is unit-testable without infrastructure and Celery tasks stay thin.

```
HTTP -> api (routers, deps, handlers) -> services -> repositories -> models/db
                                           |
Celery task (thin) ----------------------> engine -> actions / triggers
                                           |            \-> repositories
 core (config, security, logging, errors, rate limit) is imported by all layers
```

### 15.2 Responsibilities

| Layer | Package | Responsibility | MUST NOT |
| --- | --- | --- | --- |
| API | `app/api` | Routing, request/response schemas, dependency injection (`get_db`, `get_current_user`), pagination params, HTTP status mapping | Contain business rules or SQL |
| Schemas | `app/schemas` | Pydantic v2 models for I/O and definition validation | Import models/ORM |
| Services | `app/services` | Business rules, authorisation/ownership checks, transaction boundaries, audit entries, orchestration across repositories | Know about HTTP objects |
| Repositories | `app/repositories` | All SQLAlchemy queries; return ORM objects or DTOs; apply owner filters | Commit transactions, contain business rules |
| Models / DB | `app/models`, `app/db` | ORM tables, session factory, base class, Alembic env | Contain logic beyond simple properties |
| Engine | `app/engine` | Execution state machine, step runner, template resolver, retry/backoff, context building, heartbeat, finish logic | Import FastAPI/Celery |
| Actions | `app/actions` | Plugin implementations and registry; `SafeHttpClient` | Access DB except via `ActionContext.session` (database action only) |
| Triggers | `app/triggers` | Trigger plugins and registry; schedule computation | — |
| Tasks | `app/tasks` | Celery app, task wrappers, beat schedule, DB-session lifecycle per task | Contain engine logic |
| Core | `app/core` | Settings, security (hashing, JWT, Fernet), logging, error classes, rate limiter, constants | Import from higher layers |
| Middleware | `app/middleware` | Request ID, access logging, security headers, body-size limit | — |
| Utils | `app/utils` | Small pure helpers (time, ids, redaction, json size) | Hold state |

**Deviations from the suggested layout (intentional):** `workflows/` is named `engine/` (clearer); `workers/` is folded into `tasks/` (a separate package would only hold one file); `integrations/` is not a package because credentials are plain CRUD handled by `services/integration_service.py`, while outbound-call code lives in `actions/`; added `actions/` and `triggers/` as first-class plugin packages; added `scripts/` for the admin CLI.

### 15.3 Cross-cutting rules

- Dependency injection via FastAPI `Depends`; services are constructed per request with the session; no global mutable state except settings, the Redis client pool and registries.
- One transaction per service method. Engine step-state writes use their own short transactions (8.4).
- Time is obtained through `utils.time.utcnow()` so tests can freeze it.
- Configuration is read once through a cached `Settings` object (`pydantic-settings`).

---

## 16. Frontend Requirements

Backend is the priority; the dashboard exists to demonstrate it. **Stack:** React 18, TypeScript, Vite, React Router, TanStack Query, Tailwind CSS. No state-management library beyond TanStack Query and React context for auth.

### 16.1 Builder decision (resolves the visual-vs-form question)

**V1 uses a form-based builder.** The workflow is an ordered list of step cards; each card has a type selector and a form generated from the JSON schema returned by `GET /actions`, plus up/down/remove buttons and an "insert variable" helper that pastes `{{ steps.<id>.output... }}` snippets. A raw-JSON tab with a Validate button (`POST /workflows/validate`) is provided for power use. A node-based visual canvas (React Flow, edge validation, layout persistence, node palette, accessibility) would roughly double frontend effort without improving any backend skill being demonstrated, and V1 workflows are strictly linear. It is a V2 candidate (section 27).

### 16.2 Pages

| Page | Route | Content |
| --- | --- | --- |
| Login | `/login` | Email/password; error display; link to register and reset |
| Register | `/register` | Form; hidden/disabled message if registration is off |
| Password reset | `/reset-password` | Request and confirm forms |
| Workflow list | `/workflows` | Table with search, status filter, pagination; actions: open, clone, activate/deactivate, delete |
| Workflow create/edit | `/workflows/new`, `/workflows/:id/edit` | Name, description, trigger form (manual / schedule / webhook), step cards, variables editor, Save and Validate; shows version and `VERSION_CONFLICT` handling |
| Workflow detail | `/workflows/:id` | Summary, definition read-only view, versions list, Run button (JSON input dialog), webhook info and Rotate secret (secret shown once in a modal), recent executions |
| Execution history | `/executions` | Filterable table (workflow, status, date), status badges, pagination |
| Execution detail | `/executions/:id` | Header with status and timings, step timeline with per-step status/retries/errors, redacted outputs, Retry and Cancel buttons; polls every 2 s until terminal; tabbed Logs view with level/step filters |
| Integrations | `/integrations` | List, create, edit, delete; credentials are write-only fields |
| Profile | `/profile` | Edit name; change password |
| Admin dashboard | `/admin` | Stats cards, failed-executions table, users table with enable/disable, workers list, settings form, audit log table. Route guarded by role; backend still enforces |

### 16.3 Behaviour rules

- Access token is kept in memory; refresh token in `sessionStorage` (documented trade-off, D-18). A single-flight Axios/fetch interceptor refreshes on 401 `TOKEN_EXPIRED` and retries once; a failed refresh logs the user out.
- Errors from the API envelope are displayed with `message`; the `request_id` is shown in a "copy details" affordance.
- No `dangerouslySetInnerHTML`; all data is rendered as text.
- Served by an nginx container (Compose profile `ui`, port 3000) proxying `/api` to the API; development uses `npm run dev` with a Vite proxy.
- Frontend tests: Vitest for the API client/refresh logic and the step-form generator; a manual smoke checklist in `docs/`. Playwright is optional.

---

## 17. Non-Functional Requirements

Realistic targets for a single-node portfolio deployment (4 vCPU / 8 GB, Docker Compose). They are test targets, not guarantees.

| ID | Area | Requirement |
| --- | --- | --- |
| NFR-01 | API latency | p95 < 300 ms for CRUD/read endpoints and < 500 ms for list endpoints with 10,000 executions in the table, at 20 concurrent users (login excluded: Argon2 makes it \~150–400 ms by design). |
| NFR-02 | Execute latency | `POST /execute` returns 202 in p95 < 500 ms (enqueue never waits for the workflow). |
| NFR-03 | Queue pickup | Median time from `queued` to `running` < 3 s with idle workers; p95 < 10 s. |
| NFR-04 | Throughput | 20 concurrent workflow executions with one worker container (concurrency 4) without errors; steady 5 executions/s of single-step transform workflows is a stretch goal, not a requirement. |
| NFR-05 | Workflow size | ≤20 steps, ≤128 KB definition, ≤25 active workflows per user. |
| NFR-06 | Payloads | Trigger payload ≤256 KB; step output ≤256 KB; context ≤1 MB; HTTP response ≤1 MB; request bodies ≤1 MB. |
| NFR-07 | Timeouts | Step 1–60 s (default 30); HTTP ≤30 s; execution 10–900 s (default 300); DB statement 5 s; API request hard cap 30 s. |
| NFR-08 | DB pooling | API pool 10+10 overflow with `pool_pre_ping`; worker 5+5 per process; PostgreSQL `max_connections` ≥ 100 in Compose. |
| NFR-09 | Durability | No committed execution is lost on restart of any single component (8.8). Data durability depends on the Postgres volume. |
| NFR-10 | Availability | Single instance; no HA claim. Readiness endpoint reflects dependency health. |
| NFR-11 | Startup | `docker compose up` reaches healthy state in < 90 s on a warm image cache. |
| NFR-12 | Retention | Executions 90 days, audit 365 days (configurable settings), cleaned nightly. |
| NFR-13 | Portability | Python 3.12, PostgreSQL 16, Redis 7, Celery 5.4+, FastAPI 0.115+, SQLAlchemy 2.0+, Pydantic 2. Pin exact versions in `uv.lock`. |
| NFR-14 | Maintainability | `ruff` and `mypy` clean; public functions typed; cyclomatic complexity of any function ≤ 15 (ruff `C901`). |
| NFR-15 | Accessibility (UI) | Keyboard-operable forms, labelled inputs, sufficient contrast; no formal WCAG audit in V1. |

---

## 18. Logging & Observability

### 18.1 Structured logging

`structlog` configured for JSON to stdout (console renderer when `LOG_FORMAT=console` in development). Every line has: `timestamp` (UTC ISO), `level`, `event` (message), `logger`, `service` (`api`/`worker`/`scheduler`), `request_id`, plus context when known: `user_id`, `execution_id`, `workflow_id`, `step_id`, `task_id`, `duration_ms`.

**Correlation:** `RequestIDMiddleware` accepts or creates `X-Request-ID` (UUID4), stores it in a `contextvars` variable, and returns it in the response. When enqueuing a task, the ID is stored on the execution row (`request_id`) and passed in Celery headers; the worker rebinds it, so API log lines and worker log lines for one execution share the ID. Scheduler-created executions get `sched-<uuid>`.

### 18.2 Levels

| Level | Use |
| --- | --- |
| DEBUG | Template resolution outcomes (keys, not values), SQL timing, rate-limit decisions. Off by default. |
| INFO | Request completed (method, path template, status, duration), execution queued/started/finished, step started/finished, schedule fired, login success. |
| WARNING | Retry scheduled, rate-limit hit, Redis unavailable (fail-open), SSRF block, invalid webhook signature (sampled: max 1/min/workflow), schedule skipped, reaper recovery. |
| ERROR | Unhandled exception, step failed permanently, retries exhausted, task infrastructure failure. Includes stack trace (server logs only). |
| CRITICAL | Cannot start (invalid configuration, migrations behind), repeated DB failure in worker loop, encryption key failure. |

### 18.3 Never log

Passwords, password hashes, JWTs, refresh tokens, reset tokens, API keys, integration credentials, webhook secrets or signatures, `Authorization`/`Cookie` headers, request/response bodies, webhook payloads, step outputs. A structlog processor redacts keys matching the 8.2 pattern as a safety net, but the rule is not to pass such values in at all. Tests assert that a login and an integration create do not put secret values into captured logs.

### 18.4 Audit logging

Written by services, in the same transaction as the change where possible, to `audit_logs` (schema in 12.2). Metadata contains IDs and non-sensitive attributes only.

| Category | Actions |
| --- | --- |
| Auth | `auth.register`, `auth.login`, `auth.login_failed`, `auth.logout`, `auth.refresh_reuse_detected`, `auth.password_reset_requested`, `auth.password_reset_completed`, `auth.password_changed` |
| Workflows | `workflow.create`, `workflow.update`, `workflow.delete`, `workflow.activate`, `workflow.deactivate`, `workflow.clone` |
| Executions | `execution.manual_run`, `execution.retry`, `execution.cancel`, `execution.ssrf_blocked`, `schedule.skipped` |
| Integrations | `integration.create`, `integration.update`, `integration.delete`, `webhook.secret_rotated` |
| Admin | `admin.user_update`, `admin.settings_update`, `admin.execution_cancel` |

Audit failure policy: if the audit insert fails inside a state-changing transaction, the whole transaction fails (security-relevant actions must not go unrecorded). Successful scheduled/webhook runs are not audited individually (they are in `workflow_executions`).

### 18.5 Health and metrics

`GET /health` and `GET /health/ready` per 13.3. `GET /admin/stats` and `GET /admin/workers` give platform visibility. Prometheus/OpenTelemetry are V2 (section 27); V1 deliberately avoids them.

---

## 19. Testing Strategy

### 19.1 Tooling and rules

`pytest`, `pytest-cov`, `pytest-asyncio` (only where needed), `httpx`/FastAPI `TestClient`, `respx` (mock outbound httpx), `freezegun` (time), `factory-boy` or simple factories. Markers: `unit`, `integration`, `e2e`. Tests live in `backend/tests/{unit,integration,e2e}` mirroring `app/`.

- **Database:** real PostgreSQL (service container in CI, Compose locally). SQLite MUST NOT be used (JSONB, partial indexes, `SKIP LOCKED`). Schema created via `alembic upgrade head` once per session; each test runs in a transaction rolled back at the end (nested savepoints for service-managed commits).
- **Redis:** real Redis (db 15, flushed per test) for integration tests; `fakeredis` allowed in unit tests.
- **Celery:** unit/integration tests call the task function directly or use `task_always_eager=True`; one e2e test runs a real worker container against the Compose stack.
- **Outbound HTTP:** `respx` for unit tests; a local mock server fixture with `ALLOW_PRIVATE_NETWORK_REQUESTS=true` for integration tests. No real internet in tests.

### 19.2 Required coverage of behaviour

| Area | Must test |
| --- | --- |
| Unit: services | Registration rules, lockout, workflow versioning rules, clone naming, ownership, concurrency limit, idempotency |
| Unit: engine | Every transition in 8.3; backoff math and jitter bounds; resume after partial completion; on\_failure=continue; cancel before/within run; deadline; heartbeat; claim race (two concurrent claims → one wins) |
| Unit: templates | Whole-value type preservation, embedded stringification, missing path error, no re-scan, forward reference rejection |
| Unit: validation | All 7.2.1 rules, cron/timezone/DST, schedule min interval |
| Unit: actions | Each action's happy path and each error class (retryable vs permanent); transform ops; function registry import guard; email header injection; DB action isolation by owner |
| Unit: security | Password hashing and rehash, JWT claims/expiry/tamper/`alg=none`, refresh rotation and reuse, HMAC verification and timestamp window, Fernet round-trip and key rotation, redaction, SSRF matrix (14.1 item 10) |
| API | Auth flows; every endpoint's success and primary error codes; pagination; cross-user 404 for each resource; admin-only 403; error envelope shape and `request_id`; rate-limit 429 with headers; idempotency repeat returns same execution |
| Integration | Execute → Celery task → steps persisted → final state; webhook end-to-end including duplicate delivery; scheduler tick creates exactly one execution per due schedule under two concurrent ticks; reaper recovers a stale `running` execution; outbox sweeper enqueues orphaned `queued` rows |
| Failure tests | Upstream 500 then success (retry succeeds); upstream always 503 (retries exhausted, state `failed`); step timeout; invalid workflow definition rejected; invalid credentials; DB unavailable (patched engine raises `OperationalError` → 503 / worker autoretry); Redis unavailable (execute still 202, row `queued`, later swept; rate limiter fails open); worker crash simulation (kill mid-step in e2e or simulate via stale heartbeat); huge response; malformed/replayed/expired webhook |
| E2E (Compose) | Register → login → create workflow → activate → execute → poll to `succeeded`; one failing workflow reaching `failed` |

### 19.3 Coverage targets

Overall line coverage ≥ **80%** (CI gate with `--cov-fail-under=80`); ≥ **90%** for `app/engine`, `app/core/security*`, and `app/actions/safe_http*`. Branch coverage reported, not gated. Coverage is a floor; the table in 19.2 is the real requirement. No test may sleep for more than 1 s; use frozen time or injected clocks.

---

## 20. Docker & Infrastructure

### 20.1 Configuration

All configuration comes from environment variables, loaded by a single `pydantic-settings` `Settings` class with types, defaults and validators. Nothing secret is hard-coded or committed. Startup validation (fail fast, CRITICAL log) rejects: missing required variables; in non-development environments, a `JWT_SECRET_KEY` shorter than 32 chars or equal to the example value; an invalid Fernet `ENCRYPTION_KEY`; `ALLOW_PRIVATE_NETWORK_REQUESTS=true` in production; wildcard `CORS_ORIGINS` in production.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `ENVIRONMENT` | no | `development` | `development` / `test` / `production` |
| `LOG_LEVEL`, `LOG_FORMAT` | no | `INFO`, `json` | Logging |
| `ENABLE_DOCS` | no | `true` in dev, `false` in prod | Swagger/OpenAPI |
| `APP_BASE_URL` | yes | `http://localhost:3000` | Used in password-reset links |
| `DATABASE_URL` | yes | — | `postgresql+psycopg://user:pass@postgres:5432/flowforge` |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | no | 10, 10 | Pooling |
| `REDIS_URL` | yes | — | App Redis (db 1): limits, denylist, cache |
| `CELERY_BROKER_URL` | yes | — | Redis db 0 |
| `CELERY_RESULT_BACKEND` | yes | — | Redis db 2 |
| `JWT_SECRET_KEY` | yes | — | HS256 signing key |
| `JWT_ALGORITHM` | no | `HS256` | Fixed; other values rejected |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | no | 15 |  |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | no | 7 |  |
| `ENCRYPTION_KEY` | yes | — | Fernet key(s), comma-separated for rotation |
| `CORS_ORIGINS` | no | `http://localhost:3000` | Allow-list |
| `TRUSTED_PROXY_COUNT` | no | 0 | Proxies to trust for `X-Forwarded-For` |
| `SMTP_HOST`, `SMTP_PORT` | yes | — / 587 | Mail server |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | no | empty | Credentials (empty for Mailpit) |
| `SMTP_FROM`, `SMTP_STARTTLS` | no | `noreply@flowforge.local`, `true` |  |
| `EMAIL_DAILY_LIMIT_PER_USER` | no | 100 | Email action quota |
| `WORKER_CONCURRENCY` | no | 4 | Celery prefork processes |
| `ALLOW_PRIVATE_NETWORK_REQUESTS` | no | `false` | Tests only |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | no | empty | Seeds the first admin if none exists |

`.env.example` (committed; placeholders only):

```
ENVIRONMENT=development
LOG_LEVEL=INFO
LOG_FORMAT=console
ENABLE_DOCS=true
APP_BASE_URL=http://localhost:3000
DATABASE_URL=postgresql+psycopg://flowforge:change-me@postgres:5432/flowforge
POSTGRES_USER=flowforge
POSTGRES_PASSWORD=change-me
POSTGRES_DB=flowforge
REDIS_URL=redis://redis:6379/1
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/2
JWT_SECRET_KEY=change-me-generate-with-openssl-rand-hex-32
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
ENCRYPTION_KEY=generate-with-python-cryptography-fernet-generate-key
CORS_ORIGINS=http://localhost:3000
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=noreply@flowforge.local
SMTP_STARTTLS=false
WORKER_CONCURRENCY=4
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change-me-too
```

### 20.2 Images

**`docker/backend.Dockerfile`** — multi-stage: (1) `python:3.12-slim` builder installs `uv` and runs `uv sync --frozen --no-dev` into `/opt/venv`; (2) runtime stage `python:3.12-slim` copies the venv and `backend/app`, `alembic/`, creates user `flowforge` (UID 10001), sets `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`, `USER flowforge`, default `CMD` for the API. The same image runs api, worker, scheduler and migrate with different commands.

**`docker/frontend.Dockerfile`** — Node 20 build stage (`npm ci && npm run build`), then `nginx:1.27-alpine` serving `dist/` with an `nginx.conf` that proxies `/api/` to `api:8000`, sets security headers, and falls back to `index.html`.

### 20.3 Compose services

| Service | Image / command | Depends on (condition) | Healthcheck | Ports |
| --- | --- | --- | --- | --- |
| `postgres` | `postgres:16-alpine`; volume `pgdata` | — | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` | none (dev override: 5432) |
| `redis` | `redis:7-alpine --appendonly yes`; volume `redisdata` | — | `redis-cli ping` | none (dev override: 6379) |
| `migrate` | backend image; `alembic upgrade head && python -m app.scripts.seed` (idempotent: system settings, optional admin) ; `restart: "no"` | postgres healthy | exits 0 | — |
| `api` | backend image; `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2` | migrate `service_completed_successfully`, redis healthy | `python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"` | 8000 |
| `worker` | backend image; `celery -A app.tasks.celery_app worker -Q executions,maintenance -c ${WORKER_CONCURRENCY:-4} -l info` | migrate completed, redis healthy | `celery -A app.tasks.celery_app inspect ping -d celery@$$HOSTNAME` | none |
| `scheduler` | backend image; `celery -A app.tasks.celery_app beat -l info --schedule /tmp/celerybeat-schedule` | migrate completed, redis healthy | `pgrep -f "celery.*beat"` | none |
| `mailpit` | `axllent/mailpit` | — | HTTP on 8025 | 8025 (UI) |
| `frontend` | frontend image; profile `ui` | api healthy | HTTP `/` | 3000 |

Compose rules: one user-defined network `flowforge-net`; named volumes `pgdata`, `redisdata`; all services read `.env` via `env_file`; `restart: unless-stopped` for long-running services; resource-safe defaults (`stop_grace_period: 60s` for worker so in-flight steps can finish); `cap_drop: [ALL]` and `security_opt: [no-new-privileges:true]` on app services; `read_only: true` with `tmpfs: /tmp` for api/worker/scheduler. `docker-compose.yml` is production-style (no DB/Redis host ports); `docker-compose.override.yml` (auto-loaded in development) publishes 5432/6379, mounts source for `--reload`, and enables `mailpit`.

### 20.4 Run commands (must be documented in README)

```
cp .env.example .env            # then edit secrets
docker compose up --build       # api, worker, scheduler, postgres, redis, mailpit
docker compose --profile ui up --build   # also the dashboard on :3000
# API docs: http://localhost:8000/docs   Mail UI: http://localhost:8025
docker compose exec api python -m app.scripts.create_admin
make test      # runs pytest in a container against the compose stack
make lint      # ruff + mypy
```

A `Makefile` provides `up`, `down`, `logs`, `test`, `lint`, `fmt`, `migrate`, `revision m="message"`, `shell`.

---

## 21. CI/CD

`.github/workflows/ci.yml`, triggered on pull requests and pushes to `main`. Deployment is a documented future extension (`docs/DEPLOYMENT.md`).

```yaml
name: CI
on: { push: { branches: [main] }, pull_request: {} }
jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_USER: flowforge, POSTGRES_PASSWORD: ci, POSTGRES_DB: flowforge_test }
        options: >-
          --health-cmd="pg_isready -U flowforge" --health-interval=5s --health-retries=10
        ports: ["5432:5432"]
      redis:
        image: redis:7-alpine
        options: --health-cmd="redis-cli ping" --health-interval=5s --health-retries=10
        ports: ["6379:6379"]
    env:
      ENVIRONMENT: test
      DATABASE_URL: postgresql+psycopg://flowforge:ci@localhost:5432/flowforge_test
      REDIS_URL: redis://localhost:6379/15
      CELERY_BROKER_URL: redis://localhost:6379/14
      CELERY_RESULT_BACKEND: redis://localhost:6379/13
      JWT_SECRET_KEY: ci-only-secret-ci-only-secret-ci-only-secret
      ENCRYPTION_KEY: ${{ secrets.CI_FERNET_KEY }}   # or generated in a step
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
        working-directory: backend
      - run: uv run ruff check . && uv run ruff format --check .
        working-directory: backend
      - run: uv run mypy app
        working-directory: backend
      - run: uv run alembic upgrade head && uv run alembic check
        working-directory: backend
      - run: uv run pytest --cov=app --cov-fail-under=80 --cov-report=xml
        working-directory: backend
      - run: uv run bandit -q -r app && uv run pip-audit
        working-directory: backend
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci && npm run lint && npm test -- --run && npm run build
        working-directory: frontend
  docker:
    needs: [backend, frontend]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -f docker/backend.Dockerfile -t flowforge-backend:ci .
      - run: docker build -f docker/frontend.Dockerfile -t flowforge-frontend:ci .
      - uses: aquasecurity/trivy-action@0.24.0
        with: { image-ref: flowforge-backend:ci, severity: "HIGH,CRITICAL", ignore-unfixed: true, exit-code: "1" }
      - uses: gitleaks/gitleaks-action@v2
```

Pipeline order: checkout → install → lint/format/type-check → migrations check → tests with coverage gate → security (bandit, pip-audit) → Docker build → image scan and secret scan. Any failure blocks merge. Dependabot is configured for `pip`, `npm`, `docker` and `github-actions` weekly. The agent MUST verify action versions are current when writing the file and MUST NOT use secrets that do not exist: where the YAML above references a secret, generate the Fernet key in a prior step instead.

---

## 22. Repository Structure

```
flowforge/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app factory, middleware, routers, handlers
│   │   ├── api/
│   │   │   ├── deps.py              # get_db, get_current_user, require_admin, pagination
│   │   │   ├── errors.py            # exception handlers
│   │   │   └── v1/{auth,users,workflows,executions,webhooks,integrations,actions,admin,health}.py
│   │   ├── core/                    # config.py, security.py, crypto.py, logging.py, errors.py, rate_limit.py, redis.py
│   │   ├── db/                      # base.py, session.py
│   │   ├── models/                  # one module per table group
│   │   ├── schemas/                 # pydantic: auth, user, workflow(+definition), execution, integration, admin, common
│   │   ├── repositories/            # user, token, workflow, execution, integration, schedule, audit, data_record, settings
│   │   ├── services/                # auth, user, workflow, execution, integration, webhook, admin, audit, email
│   │   ├── engine/                  # runner.py, state.py, templates.py, context.py, backoff.py, errors.py, validation.py
│   │   ├── actions/                 # base.py, registry.py, http_request.py, safe_http.py, python_function.py,
│   │   │   │                          # database.py, email.py, transform.py
│   │   │   └── functions/           # registered pure functions
│   │   ├── triggers/                # base.py, registry.py, manual.py, schedule.py, webhook.py
│   │   ├── tasks/                   # celery_app.py, execution_tasks.py, maintenance_tasks.py, signals.py
│   │   ├── middleware/              # request_id.py, access_log.py, security_headers.py, body_limit.py
│   │   ├── utils/                   # time.py, redaction.py, json_size.py, ids.py
│   │   └── scripts/                 # create_admin.py, seed.py
│   ├── alembic/                     # env.py, versions/
│   ├── alembic.ini
│   ├── tests/{unit,integration,e2e}/ + conftest.py + factories.py
│   ├── pyproject.toml  uv.lock  ruff/mypy/pytest config in pyproject
├── frontend/                    # Vite React TS app: src/{api,components,pages,hooks,auth}, tests
├── docker/                      # backend.Dockerfile, frontend.Dockerfile, nginx.conf
├── docs/                        # ARCHITECTURE.md API.md DATABASE.md SECURITY.md TESTING.md DEPLOYMENT.md PROGRESS.md SRS.md
├── scripts/                     # dev helpers (wait-for, smoke test, demo data)
├── .github/{workflows/ci.yml, dependabot.yml}
├── docker-compose.yml  docker-compose.override.yml
├── Makefile  .env.example  .gitignore  .dockerignore
├── README.md  CONTRIBUTING.md  LICENSE
```

Purposes: `app/` is the deployable package; `tests/` mirrors it; `alembic/versions` holds immutable migrations; `docs/` holds living documentation; `docker/` holds build files; `scripts/` holds non-app tooling; the SRS itself is saved as `docs/SRS.md`; `docs/PROGRESS.md` is the agent's checklist (section 28).

---

## 23. Development Phases

Each phase ends with green tests, passing lint/type checks, updated docs, and a commit. Do not start a phase until the previous phase's acceptance criteria pass.

**Phase 1 — Project setup, database, configuration**

- *Objective:* runnable skeleton with all tables.
- *Tasks:* repo layout; `pyproject.toml`, ruff, mypy, pytest config; `Settings`; DB session; all SQLAlchemy models and the initial Alembic migration; request-ID middleware, structured logging, error classes and handlers; `/health` and `/health/ready`; Dockerfile; Compose with postgres, redis, migrate, api; Makefile; CI skeleton.
- *Dependencies:* none.
- *Acceptance:* `docker compose up` brings the API healthy; `alembic upgrade head` creates every table in 12.2; `alembic check` reports no drift; `/health/ready` returns 200 and returns 503 when Postgres is stopped; settings validation tests pass.
- *Deliverables:* skeleton, migration 0001, CI running lint+tests.

**Phase 2 — Authentication & authorisation**

- *Tasks:* Argon2 hashing; register/login/refresh/logout/reset; `users/me`; RBAC deps; Redis rate limiter; audit service; email sender (SMTP) for reset; admin seed/CLI.
- *Dependencies:* Phase 1.
- *Acceptance:* all AC-AUTH criteria (section 24); rate-limit and lockout tests pass; reuse detection revokes family.
- *Deliverables:* auth endpoints, services, tests, audit entries.

**Phase 3 — Workflow CRUD**

- *Tasks:* definition schemas and full validation (7.2.1, templates reference check); workflow CRUD, versions, activate/deactivate (schedule/webhook rows deferred to Phase 6 with stubbed hooks), clone, list/search, `validate` endpoint; per-user limits; audit entries.
- *Dependencies:* Phase 2.
- *Acceptance:* AC-WF; version bumps only on definition change; cross-user access gives 404.
- *Deliverables:* workflow endpoints and tests.

**Phase 4 — Workflow engine & actions**

- *Tasks:* template resolver; state machine with compare-and-set; runner (8.4) callable synchronously; actions: transform, python\_function (+ registry), database, email, http\_request with `SafeHttpClient` (no integrations yet); `/actions` catalogue; `ExecutionService.create_and_enqueue` (enqueue behind an interface); execution read endpoints (`GET /executions`, `/{id}`).
- *Dependencies:* Phase 3.
- *Acceptance:* engine unit tests cover all transitions; SSRF matrix passes; running the engine in-process on a sample workflow yields persisted step states.
- *Deliverables:* engine and actions packages with ≥90% coverage on engine and SSRF code.

**Phase 5 — Celery + Redis**

- *Tasks:* Celery app and config (11.2); `run_execution` task; execute/retry/cancel endpoints; idempotency keys; outbox sweeper; reaper; heartbeats; `worker` and `scheduler` Compose services.
- *Dependencies:* Phase 4.
- *Acceptance:* AC-EXEC; retry/backoff behaviour verified; killing the worker mid-run leads to recovery; Redis stop/start does not lose a queued execution.
- *Deliverables:* tasks package, e2e smoke script.

**Phase 6 — Scheduling & webhooks**

- *Tasks:* schedule trigger validation and `next_run_at` computation (timezone/DST); `scheduler.tick`; activation hooks creating schedule/webhook rows; webhook endpoint with HMAC, replay protection, rate limit; secret rotation; trigger registry.
- *Dependencies:* Phase 5.
- *Acceptance:* AC-SCHED, AC-WEBHOOK; concurrent ticks create one execution per due schedule.
- *Deliverables:* triggers package and tests.

**Phase 7 — Integrations**

- *Tasks:* Fernet `MultiFernet` crypto; integration CRUD with write-only credentials; in-use check; credential injection into `http_request`; `allowed_hosts` enforcement.
- *Dependencies:* Phase 4 (can run in parallel with 6).
- *Acceptance:* AC-INT; credentials never appear in API responses, logs or step outputs (tests assert this).
- *Deliverables:* integration endpoints and tests.

**Phase 8 — Monitoring, logging, admin**

- *Tasks:* `execution_logs` writes and `GET /executions/{id}/logs`; complete audit coverage per 18.4; admin endpoints; worker heartbeat keys; stats cache; cleanup task; log-redaction tests.
- *Dependencies:* Phases 5–7.
- *Acceptance:* AC-ADMIN, AC-OBS; one request ID traces from API log to worker log.
- *Deliverables:* admin API, retention job.

**Phase 9 — Frontend**

- *Tasks:* Vite app per section 16; API client with refresh logic; all pages; nginx image; `ui` Compose profile.
- *Dependencies:* Phases 2–8 API stable.
- *Acceptance:* a user can complete the E2E journey in the browser: register → create workflow → activate → run → watch steps complete; admin pages work.
- *Deliverables:* frontend, Vitest suite, smoke checklist.

**Phase 10 — Testing & security hardening**

- *Tasks:* fill gaps in 19.2; failure tests; coverage gates; security headers; bandit/pip-audit clean; review every endpoint for ownership filters; load check of NFR-01/02/04.
- *Dependencies:* all prior.
- *Acceptance:* 19.3 targets met; no HIGH findings; failure-test list passes.
- *Deliverables:* test report in `docs/TESTING.md`.

**Phase 11 — Docker, CI/CD, documentation**

- *Tasks:* final Dockerfiles and hardening (SEC-17); finalise CI; Dependabot; all docs in section 30; demo seed script (sample workflows); README quick start verified on a clean clone.
- *Dependencies:* all prior.
- *Acceptance:* Definition of Done (section 29).
- *Deliverables:* complete repository.

---

## 24. Acceptance Criteria

Format: **Given / When / Then**. Each numbered outcome MUST be covered by at least one automated test whose name or docstring cites the criteria ID.

### AC-AUTH — Authentication

**AC-AUTH-1 Register.** *Given* registration is enabled and the email is unused, *when* `POST /auth/register` is called with a valid body, *then* (1) 201 returns the profile without any hash, (2) role is `user`, (3) the password is stored as an Argon2id hash, (4) an `auth.register` audit row exists. *When* the email exists (any case), *then* 409 `EMAIL_ALREADY_REGISTERED`. *When* the password is shorter than 10 characters, *then* 422.

**AC-AUTH-2 Login and lockout.** *Given* a registered user, *when* correct credentials are posted, *then* a token pair is returned and `expires_in` equals 900. *When* the password is wrong, *then* 401 `INVALID_CREDENTIALS`, identical to the unknown-email response. *When* five consecutive failures occur, *then* the sixth attempt (even with the right password) returns 429 `ACCOUNT_LOCKED` with `Retry-After`, and after the lock expires login succeeds and resets the counter.

**AC-AUTH-3 Refresh rotation.** *Given* a valid refresh token R1, *when* `POST /auth/refresh` is called, *then* a new pair is returned and R1 is revoked. *When* R1 is presented again, *then* 401 `REFRESH_TOKEN_REUSED` and the new token R2 also stops working.

**AC-AUTH-4 Logout.** *When* `POST /auth/logout` is called with the refresh token, *then* 204; the refresh token no longer works; the same access token is rejected with 401 `TOKEN_REVOKED` until it would have expired.

**AC-AUTH-5 Token validation.** An expired access token returns 401 `TOKEN_EXPIRED`; a tampered token or one with `alg=none` returns 401 `TOKEN_INVALID`; a token for a disabled user returns 403 `ACCOUNT_DISABLED`.

**AC-AUTH-6 Password reset.** *When* a reset is requested for an unknown or known email, *then* 202 in both cases with equal bodies. *When* the emailed token is confirmed with a valid new password, *then* 204, the token is single-use, all refresh tokens are revoked and the new password works.

### AC-WF — Workflow management

**AC-WF-1 Create and read.** *Given* an authenticated user, *when* `POST /workflows` is called with a valid definition, *then* 201, status `draft`, version 1, one `workflow_versions` row. Another user's `GET /workflows/{id}` returns 404.

**AC-WF-2 Update and versioning.** *When* `PUT` changes a step, *then* version becomes 2 and version 1 remains retrievable unchanged. *When* only the description changes, *then* the version stays the same. *When* `expected_version` is stale, *then* 409 `VERSION_CONFLICT`.

**AC-WF-3 Validation.** Each rule in 7.2.1 produces its documented error code; `POST /workflows/validate` returns all errors in one response; a forward template reference returns `INVALID_REFERENCE`.

**AC-WF-4 Activate/deactivate.** *When* activating a workflow with zero steps, *then* 422 `WORKFLOW_NO_STEPS`. *When* activating a valid scheduled workflow, *then* status `active` and a schedule row with correct `next_run_at` exists; deactivating deactivates the schedule. Activating an already-active workflow re-synchronises its schedule/webhook rows and returns 200.

**AC-WF-5 Clone and delete.** Clone returns a `draft` copy named `<name> (copy)` with no schedule and no webhook secret. Delete returns 204, hides the workflow from lists, cancels its queued executions, and keeps its execution history readable.

**AC-WF-6 List.** Filtering by `status`, `q`, and `sort` works; `page_size` over 100 returns 422; `total` is correct.

### AC-EXEC — Execution

**AC-EXEC-1 Manual execution.** *Given* an authenticated user, an `active` workflow and a valid `http_request` step, *when* `POST /workflows/{id}/execute` is called, *then*: (1) the workflow is validated as active and owned; (2) an execution row and one `pending` `step_executions` row per step are created in one transaction; (3) the task is enqueued and `enqueued_at` set; (4) the API returns 202 with the execution ID; (5) a worker claims the execution and moves it to `running`; (6) each step's status, timings and output are persisted as it completes; (7) the final status `succeeded` is persisted with `finished_at` and `duration_ms`; (8) `GET /executions/{id}` shows all steps and `GET /executions/{id}/logs` shows ordered entries; (9) on a retryable failure the step enters `waiting_retry` with exponential backoff and the execution finishes per policy.

**AC-EXEC-2 Inactive workflow.** *When* the workflow is `draft` or `inactive`, *then* 409 `WORKFLOW_NOT_ACTIVE` and no execution row is created.

**AC-EXEC-3 Idempotency.** *When* the same `Idempotency-Key` is sent twice, *then* the second response is 200 with the same execution ID and exactly one execution exists.

**AC-EXEC-4 Retry then succeed.** *Given* an upstream that returns 503 twice then 200, with `max_attempts=3`, *then* the step ends `succeeded` with `retry_count=2`, the execution ends `succeeded`, and logs record both retries with their delays.

**AC-EXEC-5 Retry exhaustion.** *Given* an upstream that always returns 503, *then* after the last attempt the step is `failed` with `RETRIES_EXHAUSTED`, remaining steps are `skipped`, the execution is `failed` with `failed_step_id`, and `POST /executions/{id}/retry` creates a new execution with `retry_of_execution_id` set.

**AC-EXEC-6 Cancellation.** *When* a `queued` or `waiting_retry` execution is cancelled, *then* it becomes `cancelled` immediately. *When* a `running` execution is cancelled, *then* it becomes `cancelled` after the current step ends and no later step starts. Cancelling a finished execution returns 409.

**AC-EXEC-7 Timeout.** An execution exceeding `settings.timeout_seconds` ends `timed_out`; a step exceeding its timeout is failed or retried per 8.8.

**AC-EXEC-8 Crash recovery.** *Given* a `running` execution whose heartbeat is older than 5 minutes, *when* the reaper runs, *then* it is re-queued and completes; after 3 recoveries it is `failed` with `WORKER_LOST`.

**AC-EXEC-9 Concurrency limit.** With 3 active executions, a 4th manual execute returns 429 `WORKFLOW_CONCURRENCY_LIMIT`.

**AC-EXEC-10 Redis outage.** *Given* Redis is down, *when* a user executes a workflow, *then* 202 with `queued` status and the row exists; *when* Redis returns, *then* the sweeper enqueues it within 60 s and it completes.

### AC-SCHED — Scheduling

A cron workflow with `* * * * *` (allowed minimum) creates one execution per minute, never two for the same minute even with two concurrent `tick` runs; `once` fires once and deactivates; `Europe/London` schedules honour DST; an invalid cron or timezone is rejected with `INVALID_CRON` / `INVALID_TIMEZONE`; a schedule due >15 minutes in the past is skipped and logged; a disabled owner's schedule never fires.

### AC-WEBHOOK — Webhook

A correctly signed request returns 202 and creates one execution with `trigger.payload` equal to the body. Bad signature → 401 `INVALID_SIGNATURE`; timestamp outside ±300 s → 401; same delivery ID again → 200 `duplicate: true` with no new execution; body >256 KB → 413; non-JSON body with valid signature → 400; inactive/deleted workflow → 404; 61st request in a minute → 429. After secret rotation the old secret fails immediately.

### AC-INT — Integrations

Create returns field names but never values; the database stores only ciphertext; an `http_request` step with `integration_id` sends the right auth header (verified via mock server) and no step output, log line or API response contains the credential; `allowed_hosts` mismatch fails the step; deleting an in-use integration returns 409; another user's integration cannot be referenced (step fails `INTEGRATION_NOT_FOUND`, creation/activation rejects).

### AC-ACTION — Actions

`http_request` blocks every case in 14.1 item 10, enforces 1 MB response cap and timeouts, and extracts fields. `python_function` runs only registered functions, rejects unknown names, and no code string is accepted anywhere. `database` only touches the caller's records and enforces quotas. `email` rejects CR/LF in subject and over-limit recipients, and respects the daily cap. `transform` implements every operation with documented type errors.

### AC-ADMIN — Admin

Non-admins get 403 on every `/admin/*` route. Admin can list and filter users, disable a user (their sessions stop working, schedules deactivate, queued executions cancel), cannot disable or demote themselves, can view failed executions without payloads, view stats, workers and audit logs, and update known settings; each change creates an audit row.

### AC-OBS — Observability

Every response carries `X-Request-ID`; error bodies include the same ID; the ID appears in API logs and in worker logs for the execution it created; logs are valid JSON; tests prove passwords, tokens and integration secrets never appear in captured logs; `/health` is 200 with dependencies down; `/health/ready` is 503 when Postgres or Redis is unreachable.

### AC-DOCKER — Operability

On a clean clone, `cp .env.example .env && docker compose up --build` yields healthy `postgres`, `redis`, `migrate` (exit 0), `api`, `worker`, `scheduler`; the README quick-start journey (register, create, activate, run, view result) succeeds against it; `docker compose down && up` preserves data.

---

## 25. Edge Cases

| # | Case | Specified behaviour |
| --- | --- | --- |
| 1 | Duplicate workflow execution | With `Idempotency-Key`: the original execution is returned (200). Without a key: a new execution is created, subject to the concurrency limit. The UI disables the Run button while a request is in flight. |
| 2 | Concurrent executions | Up to 3 active per workflow; the 4th manual/webhook call gets 429 `WORKFLOW_CONCURRENCY_LIMIT`; scheduled occurrences are skipped and audited. Different workflows are independent. |
| 3 | Deleted workflow with pending job | Delete cancels `queued`/`waiting_retry` executions and sets `cancel_requested` on `running` ones. If a worker nevertheless claims an execution whose workflow is deleted, it ends `cancelled` with `error_code=WORKFLOW_DELETED`. History stays readable. |
| 4 | Disabled user with scheduled workflow | Disabling deactivates the user's schedules, cancels their queued executions and requests cancellation of running ones. `scheduler.tick` additionally refuses to fire for inactive owners. Re-enabling does not resume schedules automatically; the owner calls `activate` again (idempotent re-sync). Webhooks of disabled owners return 404. |
| 5 | Invalid cron expression | Rejected on every save and on activation with 422 `INVALID_CRON` (syntax, or interval under 60 s). Never stored in a schedule row. |
| 6 | Expired JWT | 401 `TOKEN_EXPIRED`; the client refreshes once and retries. |
| 7 | Revoked refresh token | 401 `REFRESH_TOKEN_INVALID` (revoked/unknown) or `REFRESH_TOKEN_REUSED` (rotated token replayed; family revoked). User must log in again. |
| 8 | Worker crash | 8.8: redelivery plus reaper; at-least-once step execution; `WORKER_LOST` after 3 recoveries. |
| 9 | Redis outage | 8.8: executions accepted and stored; limiter and denylist fail open with WARNING; sweeper drains later; `/health/ready` 503. |
| 10 | PostgreSQL outage | 8.8: API 503 `DATABASE_UNAVAILABLE`; worker autoretry; reaper heals; nothing is lost because nothing lives only in memory. |
| 11 | External API timeout | `http_request` timeout is retryable; after `max_attempts` the step fails `RETRIES_EXHAUSTED` (cause `STEP_TIMEOUT`). |
| 12 | External API rate limit (429) | Retryable. `Retry-After` (seconds or HTTP date) is honoured up to 600 s; if the wait would pass the execution deadline, the step fails immediately with `UPSTREAM_RATE_LIMITED` instead of waiting. |
| 13 | Malformed webhook | Order of checks: size → required headers → timestamp window → signature → JSON parse. Bad JSON with a valid signature gets 400 `MALFORMED_WEBHOOK`; any signature failure gets 401 regardless of body. |
| 14 | Webhook replay | Old timestamp → 401; repeated delivery ID within 24 h → 200 `duplicate: true`, no execution. |
| 15 | Huge API response | Stream aborted at 1 MB; step fails permanently `RESPONSE_TOO_LARGE`; no partial body stored. |
| 16 | Workflow with zero steps | Allowed as draft; activation 422 `WORKFLOW_NO_STEPS`; a worker meeting an empty version fails it with `WORKFLOW_NO_STEPS` (defensive). |
| 17 | Too many steps | More than 20 → 422 `WORKFLOW_TOO_MANY_STEPS` on any save. |
| 18 | Circular references | Impossible: references only to earlier steps; no workflow-to-workflow calls in V1. Forward/self references rejected at save. |
| 19 | Duplicate webhook | De-duplicated by delivery ID only. Identical payloads with different delivery IDs produce separate executions (documented). |
| 20 | Retry exhaustion | Step `failed` (`RETRIES_EXHAUSTED`), execution `failed`; the row is the dead-letter record; manual retry creates a new execution. |
| 21 | Edit while running | Executions are pinned to a version; edits create a new version and never affect running executions. |
| 22 | Retry of an old execution | Re-runs the originally pinned version, even if newer versions exist; requires the workflow to be `active`. |
| 23 | Integration deleted/changed mid-run | Deletion is blocked while referenced by a current version; if credentials are replaced mid-run the step uses whatever is stored when it starts; a missing integration fails permanently `INTEGRATION_NOT_FOUND`. |
| 24 | Clock skew / DST | Server stores UTC only; schedule computation uses `zoneinfo`; nonexistent local times skipped, ambiguous fire once. |
| 25 | Step output too large | Permanent `OUTPUT_TOO_LARGE`; nothing stored. |

---

## 26. MVP Scope (V1)

Implement exactly the following; everything else is V2.

- Accounts: register, login, refresh rotation, logout, password reset, lockout, `user`/`admin` roles, profile.
- Workflows: CRUD, soft delete, versioning, activate/deactivate, clone, list/search, validate endpoint.
- Triggers: manual, schedule (once/cron/timezone), webhook (HMAC).
- Actions: `http_request` (SSRF-safe), `python_function` (registered functions), `database` (sandbox table), `email`, `transform`.
- Engine: linear steps, templates, retries with backoff, timeouts, cancellation, idempotency keys, crash recovery, durable outbox.
- Monitoring: execution and step records, logs, retry/cancel, health endpoints.
- Integrations: encrypted credential store with host allow-list.
- Admin: users, executions, stats, workers, settings, audit logs.
- Platform: rate limiting, audit logging, structured logging, Docker Compose, GitHub Actions CI, pytest suite meeting 19.3.
- Frontend: form-based dashboard per section 16.

## 27. Future Scope (V2+)

None of these may influence V1 schema or code beyond what is stated; do not add placeholders for them.

- Visual drag-and-drop builder; branching and conditional logic; parallel steps; loops.
- Workflow templates and marketplace; import/export of definitions.
- OAuth-based integrations; more actions (Slack, Git hosting, SQL connectors).
- Advanced analytics (success-rate trends, step latency percentiles) and Prometheus/OpenTelemetry metrics.
- Multi-tenancy (organisations, teams, shared workflows), fine-grained RBAC.
- Distributed workers across hosts, queue prioritisation, HA scheduler with leader election.
- Email verification, MFA, SSO.
- Kubernetes manifests/Helm, managed cloud deployment, blue/green rollout.
- Workflow-to-workflow calls and sub-workflows (requires cycle detection).
- Execution payload encryption and per-step sensitive-output marking.

---

## 28. AI Coding Agent Instructions (for Antigravity)

### 28.1 Operating protocol

1. **Read this entire SRS before writing code.** Save it as `docs/SRS.md`. Then create `docs/PROGRESS.md`: a checklist with one line per phase task in section 23 and one per acceptance criterion in section 24 (`- [ ] AC-EXEC-4`). Update it after every task.
2. **The SRS is the source of truth.** Never silently invent missing requirements. When something is genuinely unspecified, choose the simplest option consistent with the decisions in 1.1, record it in `docs/DECISIONS.md` (ID, decision, reason), and continue.
3. **Identify contradictions first.** Before Phase 1, scan the SRS for conflicts (e.g. a field named differently in two places). List them in `docs/DECISIONS.md` with the resolution you chose; if a conflict blocks a security property, stop and ask the owner.
4. **Work phase by phase** (section 23). Do not start a phase until the prior phase's acceptance criteria pass. After each major task: run `ruff`, `mypy`, and `pytest`; fix failures before moving on. Never skip, delete or weaken a failing test to proceed.
5. **Follow the architecture** (section 15): routers call services, services call repositories, the engine is framework-free, tasks are thin. Do not add layers, patterns or libraries that the SRS does not call for.

### 28.2 Engineering rules

| # | Rule |
| --- | --- |
| 1 | Prefer simple, maintainable solutions; no unnecessary abstractions, no speculative generality, no V2 features. |
| 2 | Use type hints everywhere; `mypy` clean. Follow PEP 8 via `ruff`; meaningful names; small functions. |
| 3 | Never hard-code secrets; read all configuration through `Settings`; keep `.env` out of git. |
| 4 | Never disable or bypass a security check (SSRF guard, auth, HMAC, rate limits, header checks) to make something work. If a test needs a relaxation, use the documented test-only flag and nothing else. |
| 5 | Validate every API input with Pydantic; handle errors explicitly with the error classes in 13.2; never leak internals. |
| 6 | Use transactions deliberately: services own boundaries; repositories never commit; step-state commits follow 8.4. |
| 7 | Make background work idempotent and resumable as specified in 8.7; every state change uses compare-and-set. |
| 8 | Every schema change gets an Alembic migration; never edit an applied migration; `alembic check` must pass. |
| 9 | Add tests for all business logic and every behaviour in 19.2; cite acceptance-criteria IDs in test names. |
| 10 | Never log secrets or payloads (18.3); add a test when you add a new place that handles credentials. |
| 11 | Update documentation (section 30) in the same change as the code it describes. |
| 12 | Keep the application runnable through Docker Compose at the end of every phase; fix Compose breakage immediately. |
| 13 | Write clear setup instructions and verify them by following them on a clean checkout. |
| 14 | Commit per task with a clear message; keep the working tree green. |
| 15 | Do not add dependencies casually: justify each in `docs/DECISIONS.md`; prefer the standard library; pin versions via `uv.lock`; run `pip-audit` after additions. |

### 28.3 Prohibited actions

No `eval`/`exec`/`pickle`/`subprocess`/`os.system` in application code; no raw SQL string building; no wildcard CORS in production; no storing plaintext credentials; no user-supplied code execution; no direct outbound HTTP outside `SafeHttpClient`; no SQLite for tests; no auto-generated placeholders such as `pass`/`TODO` left in shipped code without a tracked entry in `docs/PROGRESS.md`.

### 28.4 When blocked

If a requirement cannot be met (library limitation, environment issue), document the cause and the smallest deviation in `docs/DECISIONS.md`, implement the safest fallback, and flag it in the final report. Do not claim a requirement is done if its test does not pass.

---

## 29. Definition of Done

The agent MAY declare the project complete only when ALL are true, with evidence recorded in `docs/PROGRESS.md`:

- [ ] Every phase task and every acceptance criterion (section 24) is checked and backed by a passing test or documented manual verification.
- [ ] Edge cases 1–25 (section 25) each have a test or an explicit note on why they are covered elsewhere.
- [ ] `cp .env.example .env && docker compose up --build` on a clean clone starts all services healthy; `migrate` exits 0; the README quick-start journey works end to end.
- [ ] `ruff check`, `ruff format --check` and `mypy app` pass; `alembic upgrade head` and `alembic check` pass on an empty database.
- [ ] `pytest` passes with coverage ≥80% overall and ≥90% on engine, security and SSRF modules; the e2e test passes against Compose.
- [ ] `bandit`, `pip-audit`, and image scan report no unaddressed HIGH/CRITICAL findings.
- [ ] SSRF test matrix (14.1) passes; secrets never appear in logs, API responses or step outputs (tests prove it).
- [ ] Failure scenarios in 19.2 (retry success, retry exhaustion, timeout, worker crash recovery, Redis outage, DB outage, malformed/replayed webhook) are demonstrated by tests.
- [ ] GitHub Actions workflow is present and passes locally-simulated steps (or on GitHub if a remote exists).
- [ ] Dashboard supports the full journey and the admin views in section 16.
- [ ] All documents in section 30 exist, are accurate to the implementation, and contain no placeholder text.
- [ ] `docs/DECISIONS.md` lists every deviation or interpretation; no secrets exist in the repository history (`gitleaks` clean).
- [ ] A final report summarises: what was built, test and coverage numbers, known limitations (at-least-once step execution, no email verification, single scheduler), and how to run everything.

---

## 30. Documentation Requirements

| File | Contents |
| --- | --- |
| `README.md` | What FlowForge is; feature list; architecture diagram; prerequisites; quick start (`.env`, `docker compose up`); creating the admin; running a sample workflow with curl and in the dashboard; running tests/lint; project structure; links to other docs; screenshots; limitations. |
| `docs/ARCHITECTURE.md` | Layers and responsibilities, component diagram, request and execution sequence diagrams (Mermaid), engine state machines, Redis vs PostgreSQL usage, failure-handling matrix, extension guides for new triggers and actions, key decisions and trade-offs. |
| `docs/API.md` | Conventions, auth flow, every endpoint with request/response examples, error catalogue, rate limits, webhook signing guide with sample code (Python and curl), pagination. Kept consistent with the generated OpenAPI. |
| `docs/DATABASE.md` | Table-by-table schema, ERD (Mermaid), indexes and why, normalisation notes, migration workflow, retention rules. |
| `docs/SECURITY.md` | Threat model summary, controls per SEC item, SSRF design, secret and key management and rotation, hardening checklist, vulnerability reporting, known limitations. |
| `docs/TESTING.md` | Test layers and markers, how to run each, fixtures, coverage results, failure-test catalogue, how to add tests. |
| `docs/DEPLOYMENT.md` | Environment variables, production-style Compose, reverse proxy/TLS notes, backups, scaling workers, upgrade and migration procedure, future CI/CD deployment and Kubernetes outlook. |
| `CONTRIBUTING.md` | Dev setup, branching and commit conventions, code style, how to add an action/trigger, PR checklist, running CI locally. |
| `docs/PROGRESS.md`, `docs/DECISIONS.md`, `docs/SRS.md` | Agent checklist, decision log, and this specification. |

---

## 31. Glossary

| Term | Meaning |
| --- | --- |
| Workflow | A named automation: one trigger plus an ordered list of steps. |
| Definition | The JSON document describing a workflow's trigger, variables, settings and steps. |
| Version | Immutable snapshot of a definition; executions pin to one. |
| Trigger | What starts a workflow: manual, schedule or webhook. |
| Step | One configured action instance inside a workflow. |
| Action | A plugin type that performs work (`http_request`, `python_function`, `database`, `email`, `transform`). |
| Execution | One run of a workflow version; the unit of monitoring and retry. |
| Step execution | The recorded state of one step within an execution. |
| Context | The JSON object (`trigger`, `vars`, `steps`) from which templates are resolved. |
| Template | A `{{ path }}` lookup in a step config string. |
| Claim | The atomic transition `queued`/`waiting_retry` → `running` that gives a worker exclusive ownership. |
| Outbox sweeper | Beat task that enqueues committed `queued` executions not yet dispatched. |
| Reaper | Beat task that recovers `running` executions with stale heartbeats. |
| Dead-letter record | A permanently `failed` execution retained for inspection and manual retry. |
| Idempotency key | Client-supplied key making a request safe to repeat. |
| HMAC | Keyed hash used to sign webhook requests. |
| SSRF | Server-side request forgery: tricking the server into calling internal addresses. |
| Fernet | Symmetric authenticated encryption from the `cryptography` library. |
| Refresh-token family | The chain of rotated refresh tokens issued from one login; revoked together on reuse. |
| At-least-once | Delivery guarantee under which a step may run more than once after a crash. |
| RBAC | Role-based access control. |
| SRS | Software Requirements Specification (this document). |
