# FlowForge

*A Python-based workflow automation and background job processing platform.*

FlowForge allows users to define linear automation workflows triggered manually, on a schedule, or via signed webhooks. It is built with a focus on reliability, relational database design, asynchronous execution safety, and robust error handling.

---

## Architecture & Technology Stack

- **Backend Runtime:** Python 3.12
- **API Framework:** FastAPI with sync endpoints in threadpools
- **ORM & Database:** SQLAlchemy 2.0 (synchronous), psycopg3 driver, PostgreSQL 16
- **Migrations:** Alembic
- **Ephemeral State & Queue:** Redis 7, Celery 5.4+
- **Security:** Argon2id password hashing, Fernet symmetric encryption, HS256 JWT
- **Observability:** `structlog` JSON-structured logging with automatic redaction and request correlation IDs

---

## Getting Started

### 1. Prerequisites
- Docker & Docker Compose
- Python 3.12 and `uv` (for local development outside containers)

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your local secrets
```

### 3. Run with Docker Compose
```bash
# Build and start PostgreSQL, Redis, Migrate, API, and Mailpit
docker compose up --build

# In another terminal, check liveness:
curl http://localhost:8000/health

# Check readiness (validates PostgreSQL, Redis, and Alembic migrations):
curl http://localhost:8000/health/ready
```

### 4. Running Tests & Linting
```bash
# Run unit and integration tests with coverage:
make test

# Run linter and type-checker:
make lint

# Auto-format codebase:
make fmt
```

---

## Phase 1 Implementation Status

Phase 1 provides the foundational skeleton and database architecture:
- [x] Full project scaffold and directory tree
- [x] All 13 PostgreSQL tables defined in SQLAlchemy 2.0 with constraints, relations, and indexes
- [x] Initial Alembic migration (`0001_initial_schema.py`)
- [x] Pydantic Settings with startup validation
- [x] Structured JSON logging with key-based sensitive data redaction
- [x] Request ID middleware, Security headers, and Global body limit backstop
- [x] Liveness (`/health`) and Readiness (`/health/ready`) endpoints
- [x] Docker Compose stack (PostgreSQL, Redis, Migrate service, FastAPI API, Mailpit)
- [x] Pytest suite with strict SQLite rejection and configuration validation tests
