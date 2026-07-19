#!/usr/bin/env bash
# VM variant of tools/run_demo.sh (SPEC day10): same stack, two differences —
# Streamlit binds 0.0.0.0 so the visitor can reach it, and the demo env
# (DEMO_PUBLIC / DEMO_GATE_KEY / LEARNARKEN_TRACE_DISABLED / quotas) is
# inherited from the systemd EnvironmentFile. The docker containers are NOT
# started here: a separate root-owned unit owns them, so this process (and the
# app user) never needs Docker-socket access (day10 #11). The FastAPI backend
# stays on loopback; only Streamlit (:8501) and the status shim (:8110) are
# public.
set -euo pipefail
cd "$(dirname "$0")/../.."

echo "waiting for vespa + neo4j ..."
for _ in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:8080/state/v1/health >/dev/null 2>&1 \
    && curl -fsS http://127.0.0.1:7474 >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

uv run python tools/demo_preflight.py

uv run uvicorn learnarken.api.app:app --host 127.0.0.1 --port 8100 &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM

echo "waiting for the backend at http://127.0.0.1:8100 ..."
ready=0
for _ in $(seq 1 120); do
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
  echo "backend did not become healthy within 120s (fail closed)" >&2
  exit 1
fi

# maxUploadSize is defense-in-depth: uploads are already refused in public mode
# (DEMO_PUBLIC), but this caps Streamlit's own buffering regardless (day10 #4).
uv run --group demo streamlit run demo/streamlit_app.py \
  --server.address 0.0.0.0 --server.port 8501 --server.headless true \
  --server.maxUploadSize 3
