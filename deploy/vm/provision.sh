#!/usr/bin/env bash
# One-time provisioning of the on-demand demo VM (SPEC day10).
# Run as root on a fresh Debian 12 GCE instance (see deploy/runbook.md):
#   sudo bash provision.sh <git-clone-url>
# Idempotent-ish: safe to re-run after a partial failure.
# The .env (MINIMAX_* etc.) is NOT handled here — scp it separately
# (runbook step 4); this script stops and tells you if it is missing.
set -euo pipefail

REPO_URL="${1:?usage: provision.sh <git-clone-url>}"
APP_HOME=/opt/learnarken
REPO_DIR="$APP_HOME/LearnArken"

# Pinned images (day10 #12: no :latest — a rebuild must be reproducible).
# After the first successful pull, pin digests too:
#   docker inspect --format '{{index .RepoDigests 0}}' learnarken-neo4j
NEO4J_IMAGE="neo4j:2025.06.0"
VESPA_IMAGE="vespaengine/vespa:8"

apt-get update
apt-get install -y docker.io git curl python3

# App user WITHOUT the docker group: the docker group is root-equivalent, and
# only the root-owned learnarken-containers.service touches the socket (#11).
id learnarken >/dev/null 2>&1 || useradd -r -m -d "$APP_HOME" -s /bin/bash learnarken

if [ ! -d "$REPO_DIR/.git" ]; then
  sudo -u learnarken git clone "$REPO_URL" "$REPO_DIR"
fi

# uv manages its own Python 3.12; the systemd shim/watchdog use system python3.
sudo -u learnarken bash -c 'command -v ~/.local/bin/uv >/dev/null 2>&1 \
  || curl -LsSf https://astral.sh/uv/install.sh | sh'
sudo -u learnarken bash -c "cd $REPO_DIR && ~/.local/bin/uv sync --group demo"

if [ ! -f "$REPO_DIR/.env" ]; then
  echo "STOP: $REPO_DIR/.env is missing — scp it from the dev machine (runbook step 4)," >&2
  echo "then re-run this script. (Fail closed: no key material is created here.)" >&2
  exit 1
fi

# Public-demo env. DEMO_GATE_KEY must be filled with the shared key that the
# Cloud Function embeds in the visitor link (runbook step 6); provisioning
# leaves a placeholder so the app fails closed (locked) until it is set.
if [ ! -f "$APP_HOME/demo.env" ]; then
  cat > "$APP_HOME/demo.env" <<'EOF'
DEMO_PUBLIC=1
LEARNARKEN_TRACE_DISABLED=1
DEMO_MAX_LLM_CALLS=200
DEMO_MAX_CONCURRENCY=2
DEMO_GATE_KEY=CHANGE-ME-must-match-the-Cloud-Function-link-key
EOF
  chown learnarken:learnarken "$APP_HOME/demo.env"
  chmod 600 "$APP_HOME/demo.env"
fi

# Containers: loopback-bound (docs/local-services.md); the only public ports on
# this VM are Streamlit :8501 and the shim :8110.
docker inspect learnarken-vespa >/dev/null 2>&1 || docker run -d \
  --name learnarken-vespa --hostname vespa-container \
  -p 127.0.0.1:8080:8080 -p 127.0.0.1:19071:19071 "$VESPA_IMAGE"
docker inspect learnarken-neo4j >/dev/null 2>&1 || docker run -d \
  --name learnarken-neo4j \
  -p 127.0.0.1:7474:7474 -p 127.0.0.1:7687:7687 \
  -e NEO4J_AUTH=neo4j/learnarken "$NEO4J_IMAGE"

echo "waiting for vespa config server + neo4j ..."
for _ in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:19071/state/v1/health >/dev/null 2>&1 \
    && curl -fsS http://127.0.0.1:7474 >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

# Feed everything once: deploys the Vespa app package, indexes package-a+c,
# syncs the Neo4j graph, and pulls the embedding model into the HF cache
# (multi-GB — this is the slow step, done once so cold boots never download).
sudo -u learnarken bash -c \
  "cd $REPO_DIR && ~/.local/bin/uv run learnarken index samples/package-a samples/package-c --strategy structure"

install -m 644 "$REPO_DIR"/deploy/vm/systemd/*.service "$REPO_DIR"/deploy/vm/systemd/*.timer \
  /etc/systemd/system/
# PATH for uv inside the demo unit
mkdir -p /etc/systemd/system/learnarken-demo.service.d
cat > /etc/systemd/system/learnarken-demo.service.d/path.conf <<EOF
[Service]
Environment=PATH=$APP_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
EOF
systemctl daemon-reload
systemctl enable --now \
  learnarken-containers.service learnarken-demo.service \
  learnarken-shim.service learnarken-watchdog.timer

echo "provisioned. Set DEMO_GATE_KEY in $APP_HOME/demo.env, then:"
echo "  systemctl restart learnarken-demo && curl -s http://127.0.0.1:8110/demo/status"
