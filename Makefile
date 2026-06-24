# Athlete AI Training Hub — developer commands
# Windows: run inside Git Bash, or use the docker compose commands directly.

COMPOSE = docker compose
DEV = docker compose -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: help up dev down logs ps migrate makemigration revision test test-cov \
        shell-api shell-db seed import import-athlete lint fmt clean

help:
	@echo "Athlete AI Training Hub"
	@echo "  make up            - build & start the full stack (detached)"
	@echo "  make dev           - start with live-reload (foreground)"
	@echo "  make down          - stop everything"
	@echo "  make logs          - tail all logs"
	@echo "  make migrate       - apply DB migrations (alembic upgrade head)"
	@echo "  make makemigration m=msg - autogenerate a migration"
	@echo "  make seed          - create bootstrap admin + 2 demo athletes"
	@echo "  make seed-knowledge- populate the training-knowledge base (RAG)"
	@echo "  make import        - run a sample import job (CSV)"
	@echo "  make test          - run the backend test suite"
	@echo "  make test-cov      - run tests with coverage report"
	@echo "  make shell-api     - shell into the api container"
	@echo "  make shell-db      - psql into postgres"

up:
	$(COMPOSE) up -d --build

dev:
	$(DEV) up --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

migrate:
	$(COMPOSE) exec api alembic upgrade head

makemigration:
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(m)"

seed:
	$(COMPOSE) exec api python -m app.scripts.seed

seed-knowledge:
	$(COMPOSE) exec api python -m app.scripts.seed_knowledge

import:
	$(COMPOSE) exec api python -m app.scripts.sample_import

import-athlete:
	$(COMPOSE) exec api python -m app.scripts.import_athlete --athlete $(ATHLETE) --email $(EMAIL)

test:
	$(COMPOSE) exec api pytest -q

test-cov:
	$(COMPOSE) exec api pytest --cov=app --cov-report=term-missing

shell-api:
	$(COMPOSE) exec api bash

shell-db:
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-athlete} -d $${POSTGRES_DB:-athlete_hub}

clean:
	$(COMPOSE) down -v
