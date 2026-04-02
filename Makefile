.PHONY: install run dev test lint typecheck check clean

install:            ## Install production dependencies
	uv sync

run:                ## Start the app (opens browser at localhost:5001)
	uv run python app.py

dev:                ## Install all dependencies including dev tools
	uv sync --group dev

test:               ## Run tests
	uv run pytest

lint:               ## Lint with Ruff
	uv run ruff check .

typecheck:          ## Type-check with Pyright
	uv run pyright

check: lint typecheck test   ## Run lint + typecheck + tests

clean:              ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true

help:               ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
