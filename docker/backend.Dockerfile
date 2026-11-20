# FlowForge — Multi-stage Backend Dockerfile
# SRS §20.2: python:3.12-slim builder + runtime, non-root user flowforge (UID 10001)

# ── Stage 1: Build stage ───────────────────────────────────────────────────
FROM python:3.15-slim AS builder

WORKDIR /build

# Install uv for fast, reliable dependency installation
COPY --from=ghcr.io/astral-sh/uv:0.5.21 /uv /uvx /bin/

# Install build dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml (and uv.lock when available)
COPY backend/pyproject.toml ./
# If uv.lock exists, it will be copied, otherwise uv will resolve
COPY backend/uv.lock* ./

# Sync dependencies into /opt/venv (without dev dependencies)
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN if [ -f uv.lock ]; then \
        uv sync --frozen --no-dev --no-install-project; \
    else \
        uv sync --no-dev --no-install-project; \
    fi


# ── Stage 2: Runtime stage ─────────────────────────────────────────────────
FROM python:3.15-slim AS runtime

# Runtime env vars
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

WORKDIR /app

# Create unprivileged application user
RUN groupadd -g 10001 flowforge && \
    useradd -u 10001 -g flowforge -s /bin/bash -m flowforge && \
    mkdir -p /app && chown -R flowforge:flowforge /app

# Copy virtual environment from builder stage
COPY --from=builder --chown=flowforge:flowforge /opt/venv /opt/venv

# Copy backend application, alembic config and migrations
COPY --chown=flowforge:flowforge backend/app ./app
COPY --chown=flowforge:flowforge backend/alembic ./alembic
COPY --chown=flowforge:flowforge backend/alembic.ini ./alembic.ini
COPY --chown=flowforge:flowforge backend/pyproject.toml ./pyproject.toml

# Switch to unprivileged user
USER flowforge

# Default healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

# Default command: start FastAPI with uvicorn (SRS §20.3)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
