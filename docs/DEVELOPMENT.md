# FlowForge — Development Guide

## Local Setup

### Prerequisites
- Docker & Docker Compose
- Python 3.12 (optional if running inside Docker)
- uv package manager (recommended)

### Quick Start
1. Copy environment template:
   ```bash
   cp .env.example .env
   ```
2. Start the services with Docker Compose:
   ```bash
   docker compose up --build
   ```
3. Verify health status:
   ```bash
   curl http://localhost:8000/health
   ```
