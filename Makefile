.DEFAULT_GOAL := help

PYTHON ?= python
PIP ?= pip

.PHONY: help install fmt lint type test cov run clean reset hooks

help:  ## Show available targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## Install package in editable mode with dev extras
	$(PIP) install -e ".[dev]"

hooks:  ## Install pre-commit hooks
	pre-commit install

fmt:  ## Format code with ruff
	ruff format quorum tests

lint:  ## Lint with ruff (auto-fix safe issues)
	ruff check --fix quorum tests

type:  ## Type-check with mypy
	mypy quorum

test:  ## Run the test suite
	pytest -v

cov:  ## Tests with coverage report
	pytest --cov=quorum --cov-report=term-missing --cov-report=html

run:  ## Execute the pipeline
	$(PYTHON) -m quorum

clean:  ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov coverage.xml .coverage
	rm -rf build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +

reset: clean  ## Also wipe outputs and the HAPI cache
	rm -rf outputs/*
	touch outputs/.gitkeep
