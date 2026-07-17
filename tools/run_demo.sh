#!/usr/bin/env bash
# make demo: preflight (fail closed), then FastAPI + Streamlit on loopback.
# Ctrl-C stops both. Single uvicorn worker on purpose: the local embedding
# and reranker models are per-process resident (SPEC day6).
set -euo pipefail
cd "$(dirname "$0")/.."

uv run python tools/demo_preflight.py

uv run uvicorn learnarken.api.app:app --host 127.0.0.1 --port 8100 &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM

echo "waiting for the backend at http://127.0.0.1:8100 ..."
ready=0
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8100/health >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "backend exited during startup (fail closed)" >&2
    exit 1
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  # Never start the frontend against a dead backend (fail closed, day6 #6).
  echo "backend did not become healthy within 60s (fail closed)" >&2
  exit 1
fi

uv run --group demo streamlit run demo/streamlit_app.py \
  --server.address 127.0.0.1 --server.port 8501 --server.headless true
