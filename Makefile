SHELL := /bin/bash

PYTHON ?= python3
BACKEND_VENV := backend/.venv
BACKEND_PYTHON := $(BACKEND_VENV)/bin/python
BACKEND_PIP := $(BACKEND_VENV)/bin/pip

.PHONY: help install install-backend install-frontend dev start fixtures test test-backend test-frontend lint lint-backend lint-frontend build clean docker-build docker-up docker-down docker-logs

help:
	@echo "DolosMeta development commands"
	@echo "  make install       Install backend and frontend dependencies"
	@echo "  make dev           Start API and UI locally"
	@echo "  make fixtures      Regenerate deterministic test fixtures"
	@echo "  make test          Run backend and frontend tests"
	@echo "  make lint          Run backend and frontend linters"
	@echo "  make build         Create the production frontend build"
	@echo "  make docker-up     Build and start the local container stack"

install: install-backend install-frontend

install-backend:
	@test -f backend/pyproject.toml || (echo "backend/pyproject.toml is missing" >&2; exit 1)
	@test -x "$(BACKEND_PYTHON)" || $(PYTHON) -m venv "$(BACKEND_VENV)"
	"$(BACKEND_PIP)" install --upgrade pip
	"$(BACKEND_PIP)" install -e "./backend[dev]"

install-frontend:
	npm ci

dev start:
	./start.sh

fixtures:
	$(PYTHON) scripts/generate_fixtures.py

test: test-backend test-frontend

test-backend:
	@test -x "$(BACKEND_PYTHON)" || (echo "Run 'make install-backend' first" >&2; exit 1)
	cd backend && .venv/bin/python -m pytest -q

test-frontend:
	npm test

lint: lint-backend lint-frontend

lint-backend:
	@test -x "$(BACKEND_PYTHON)" || (echo "Run 'make install-backend' first" >&2; exit 1)
	cd backend && .venv/bin/python -m ruff check .

lint-frontend:
	npm run lint

build:
	npm run build

clean:
	rm -rf dist .next .vinext coverage
	find backend -type d -name __pycache__ -prune -exec rm -rf {} +
	find backend -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

docker-build:
	docker compose build

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f
