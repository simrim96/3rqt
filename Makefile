# Three Racqwen in a Trenchcoat — gate locale minima (equivalente della CI).
.PHONY: check lint test doctor sync

sync:
	uv sync

lint:
	uv run ruff check src tests scripts
	uv run ruff format --check src tests scripts

test:
	uv run pytest

check: lint test

doctor:
	uv run python scripts/check_nodes.py
