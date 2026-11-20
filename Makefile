# FlowForge — Development Makefile
# SRS §20.4: standard operational commands

.PHONY: help up down restart logs ps test lint fmt migrate revision shell clean

help:
	@echo "FlowForge Management Commands:"
	@echo "  make up          Start the Docker Compose stack"
	@echo "  make down        Stop the Docker Compose stack"
	@echo "  make restart     Restart all services"
	@echo "  make logs        Tail service logs"
	@echo "  make ps          View service status"
	@echo "  make test        Run tests inside the test container / virtualenv"
	@echo "  make lint        Run ruff and mypy"
	@echo "  make fmt         Auto-format code with ruff"
	@echo "  make migrate     Run alembic upgrade head"
	@echo "  make revision    Generate a new Alembic migration: make revision m='message'"
	@echo "  make shell       Open a shell inside the API container"
	@echo "  make clean       Remove cached Python and test artifacts"

up:
	docker compose up --build -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

ps:
	docker compose ps

test:
	docker compose exec api pytest backend/tests --cov=app --cov-fail-under=80

lint:
	docker compose exec api ruff check backend/app backend/tests
	docker compose exec api mypy backend/app

fmt:
	docker compose exec api ruff check --fix backend/app backend/tests
	docker compose exec api ruff format backend/app backend/tests

migrate:
	docker compose exec api alembic upgrade head

revision:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

shell:
	docker compose exec api /bin/bash

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
