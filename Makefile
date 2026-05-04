PYTHON ?= python
PIP ?= $(PYTHON) -m pip
BACKEND_HOST ?= 0.0.0.0
BACKEND_PORT ?= 8000
DASHBOARD_PORT ?= 8501

.PHONY: help install dev-backend dev-dashboard test lint format compile smoke seed-vector-cases backfill-vector-embeddings clean

help:
	@echo "Sahayak 1092 developer commands"
	@echo "  make install        Install Python dependencies"
	@echo "  make dev-backend    Run FastAPI backend locally"
	@echo "  make dev-dashboard  Run Streamlit dashboard locally"
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

dev-backend:
	$(PYTHON) -m uvicorn backend.app:app --host $(BACKEND_HOST) --port $(BACKEND_PORT) --reload

dev-dashboard:
	$(PYTHON) -m streamlit run dashboard/app.py --server.port $(DASHBOARD_PORT)

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check backend dashboard tests

format:
	$(PYTHON) -m ruff format backend dashboard tests

compile:
	$(PYTHON) -m compileall backend dashboard

smoke: compile test

seed-vector-cases:
	$(PYTHON) -m backend.vector_admin seed

backfill-vector-embeddings:
	$(PYTHON) -m backend.vector_admin backfill

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
