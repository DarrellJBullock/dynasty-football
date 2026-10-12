# Dynasty Football: Next Gen — developer commands. Run `make help` for a list.

SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend
VENV := $(BACKEND)/.venv
PY := $(VENV)/bin/python

# Homebrew's postgresql@17 is keg-only (not on PATH); fall back to whatever is on PATH.
PG_BIN := $(shell brew --prefix postgresql@17 2>/dev/null)/bin
PG := $(if $(wildcard $(PG_BIN)/createdb),$(PG_BIN)/,)

DB_NAME ?= dynasty_football
TEST_DB_NAME ?= dynasty_football_test

# Unity (docs/design/depth-and-unity.md §4): the editor the project is pinned to
# (unity/ProjectSettings/ProjectVersion.txt), as Unity Hub installs it on macOS.
UNITY_VERSION := $(shell sed -n 's/^m_EditorVersion: //p' unity/ProjectSettings/ProjectVersion.txt 2>/dev/null)
UNITY ?= /Applications/Unity/Hub/Editor/$(UNITY_VERSION)/Unity.app/Contents/MacOS/Unity
E2E_DB_NAME ?= dynasty_football_e2e
TEST_DATABASE_URL ?= postgresql+psycopg://localhost:5432/$(TEST_DB_NAME)

.PHONY: help setup setup-backend setup-frontend db-start db-create migrate seed reseed worker perf \
        dev-backend dev-frontend test test-backend test-backend-fast test-frontend lint build \
        e2e-setup e2e unity-test unity-build

help: ## Show available commands
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[33m%-18s\033[0m %s\n", $$1, $$2}'

setup: setup-backend setup-frontend db-create migrate seed ## One-time setup: deps, databases, schema, sample league

setup-backend: ## Create the Python venv and install backend deps
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -e "$(BACKEND)[dev]"
	@test -f $(BACKEND)/.env || cp $(BACKEND)/.env.example $(BACKEND)/.env

setup-frontend: ## Install frontend deps
	npm --prefix $(FRONTEND) install

db-start: ## Start PostgreSQL via Homebrew services
	brew services start postgresql@17

db-create: ## Create the dev and test databases (no-op if they exist)
	-$(PG)createdb $(DB_NAME) 2>/dev/null || true
	-$(PG)createdb $(TEST_DB_NAME) 2>/dev/null || true
	-$(PG)createdb $(E2E_DB_NAME) 2>/dev/null || true

migrate: ## Apply database migrations
	cd $(BACKEND) && .venv/bin/alembic upgrade head

seed: ## Create the sample fictional league (only if the DB is empty)
	cd $(BACKEND) && .venv/bin/python -m app.seed

perf: ## Time every API read on a league with seasons played (its own database)
	-$(PG)createdb dynasty_football_perf 2>/dev/null || true
	cd $(BACKEND) && DATABASE_URL=postgresql+psycopg://localhost:5432/dynasty_football_perf .venv/bin/alembic upgrade head
	cd $(BACKEND) && DATABASE_URL=postgresql+psycopg://localhost:5432/dynasty_football_perf .venv/bin/python -m app.perf build --seasons 3
	cd $(BACKEND) && DATABASE_URL=postgresql+psycopg://localhost:5432/dynasty_football_perf .venv/bin/python -m app.perf measure --budget-ms 300 --max-queries 80

reseed: ## Wipe all game data and regenerate the sample league
	cd $(BACKEND) && .venv/bin/python -m app.seed --reset

dev-backend: ## Run the API at http://localhost:8000 (docs at /docs), with a job worker
	cd $(BACKEND) && WORKER_EMBEDDED=1 .venv/bin/uvicorn app.main:app --reload --port 8000

worker: ## Run a background job worker on its own (dev-backend already runs one)
	cd $(BACKEND) && .venv/bin/python -m app.worker

dev-frontend: ## Run the web app at http://localhost:3000
	npm --prefix $(FRONTEND) run dev

test: test-backend test-frontend ## Run all tests (backend against PostgreSQL)

test-backend: ## Backend tests against the PostgreSQL test database
	cd $(BACKEND) && TEST_DATABASE_URL=$(TEST_DATABASE_URL) .venv/bin/pytest

test-backend-fast: ## Backend tests against in-memory SQLite (no services needed)
	cd $(BACKEND) && .venv/bin/pytest

test-frontend: ## Frontend unit and component tests
	npm --prefix $(FRONTEND) test

lint: ## Lint and typecheck everything
	cd $(BACKEND) && .venv/bin/ruff check app tests
	npm --prefix $(FRONTEND) run lint
	npm --prefix $(FRONTEND) run typecheck

e2e-setup: ## One-time: e2e database + Playwright's Chromium
	-$(PG)createdb $(E2E_DB_NAME) 2>/dev/null || true
	cd $(BACKEND) && DATABASE_URL=postgresql+psycopg://localhost:5432/$(E2E_DB_NAME) .venv/bin/alembic upgrade head
	cd $(FRONTEND) && npx playwright install chromium

unity-test: ## Unity's edit-mode tests (needs Unity installed; results in unity/Logs/)
	"$(UNITY)" -batchmode -nographics -projectPath unity -runTests -testPlatform EditMode \
	  -testResults "$(CURDIR)/unity/Logs/test-results.xml" -logFile -

unity-build: ## Build the Unity viewer for the web into frontend/public/unity (needs Unity)
	"$(UNITY)" -batchmode -nographics -quit -projectPath unity \
	  -executeMethod Dynasty.BuildScript.BuildWebGL -buildOutput "$(CURDIR)/$(FRONTEND)/public/unity" -logFile -

e2e: ## End-to-end tests in a real browser (own DB and ports 8001/3001)
	cd $(BACKEND) && DATABASE_URL=postgresql+psycopg://localhost:5432/$(E2E_DB_NAME) .venv/bin/alembic upgrade head
	npm --prefix $(FRONTEND) run e2e

build: ## Production build of the frontend
	npm --prefix $(FRONTEND) run build
