PYTHON ?= python
PIP ?= $(PYTHON) -m pip
BACKEND_HOST ?= 0.0.0.0
BACKEND_PORT ?= 8000
DASHBOARD_HOST ?= 127.0.0.1
DASHBOARD_PORT ?= 3000
LEGACY_DASHBOARD_PORT ?= 8501

.PHONY: help install install-dashboard dev-backend dev-dashboard dev-dashboard-legacy test lint format compile smoke seed-vector-cases backfill-vector-embeddings clean

help:
	@echo "Sahayak 1092 developer commands"
	@echo "  make install        Install Python dependencies"
	@echo "  make install-dashboard Install Next.js dashboard dependencies"
	@echo "  make dev-backend    Run FastAPI backend locally"
	@echo "  make dev-dashboard  Run Next.js dashboard locally"
	@echo "  make dev-dashboard-legacy Run legacy Streamlit dashboard"
	@echo "  make test           Run pytest"
	@echo "  make lint           Run ruff checks"
	@echo "  make format         Run ruff formatter"
	@echo "  make compile        Compile backend/dashboard Python files"
	@echo "  make smoke          Run compile + tests"
	@echo "  make seed-vector-cases          Seed Supabase resolved cases with embeddings"
	@echo "  make backfill-vector-embeddings Backfill missing resolved-case embeddings"
	@echo "  make clean          Remove local Python caches"

install:
	$(PIP) install --prefer-binary -r requirements.txt

install-dashboard:
	npm --prefix dashboard install

dev-backend:
	$(PYTHON) -m uvicorn backend.app:app --host $(BACKEND_HOST) --port $(BACKEND_PORT) --reload

dev-dashboard:
	npm --prefix dashboard run dev -- --hostname $(DASHBOARD_HOST) --port $(DASHBOARD_PORT)

dev-dashboard-legacy:
	$(PYTHON) -m streamlit run dashboard/app.py --server.port $(LEGACY_DASHBOARD_PORT)

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check backend dashboard tests

format:
	$(PYTHON) -m ruff format backend dashboard tests

compile:
	$(PYTHON) -m compileall backend dashboard/app.py tests

smoke: compile test

seed-vector-cases:
	$(PYTHON) -m backend.vector_admin seed

backfill-vector-embeddings:
	$(PYTHON) -m backend.vector_admin backfill

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
