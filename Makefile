VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help install dev test lint format typecheck run run-debug clean

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  install    Install the package into the venv"
	@echo "  dev        Install the package with dev dependencies (pytest, ruff, mypy)"
	@echo "  test       Run lint, typecheck, and the full test suite"
	@echo "  lint       Run ruff linter"
	@echo "  format     Apply ruff formatter"
	@echo "  typecheck  Run mypy static type checker"
	@echo "  run        Start the bot"
	@echo "  run-debug  Start the bot with debug logging enabled"
	@echo "  clean      Remove __pycache__, egg-info, and dist directories"

install:
	$(PIP) install .

dev:
	$(PIP) install ".[dev]"

test:
	$(PYTHON) -m ruff check src/orca_bot tests
	$(PYTHON) -m mypy src/orca_bot
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src/orca_bot tests

format:
	$(PYTHON) -m ruff format src/orca_bot tests

typecheck:
	$(PYTHON) -m mypy src/orca_bot

run:
	$(PYTHON) -m orca_bot

run-debug:
	$(PYTHON) -m orca_bot --debug

clean:
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -not -path "./.venv/*" -exec rm -rf {} +
	find . -type d -name dist -not -path "./.venv/*" -exec rm -rf {} +
