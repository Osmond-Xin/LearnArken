.PHONY: test lint fmt demo

test:
	uv run pytest

# One-command demo (SPEC day6): fail-closed preflight, then FastAPI
# (127.0.0.1:8100) + Streamlit (127.0.0.1:8501). Ctrl-C stops both.
demo:
	bash tools/run_demo.sh

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .
