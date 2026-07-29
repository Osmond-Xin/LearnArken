#!/usr/bin/env bash
# One-time provisioning of the on-demand demo VM (SPEC day10).
# Run as root on a fresh Debian 12 GCE instance (see deploy/runbook.md):
#   sudo bash provision.sh <git-clone-url> [<commit-sha>]
# Idempotent-ish: safe to re-run after a partial failure.
# The .env (MINIMAX_* etc.) is NOT handled here — scp it separately
# (runbook step 4); this script stops and tells you if it is missing.
set -euo pipefail

# Phase log (red team R-19): a provision that dies leaves a machine that costs
# money, so where it died must be one line, not a scrollback hunt.
phase() { echo "=== [$(date -u +%H:%M:%S)] $* ==="; }

# Only one provision at a time: two concurrent runs would race `uv sync`, the
# Vespa deploy and the index, and each one's EXIT trap would clear the other's
# provisioning sentinel — re-arming the unreachable-strike mid-provision
# (round-2 red team).
exec 9>/run/learnarken-provision.lock
flock -n 9 || { echo "another provision run holds the lock — refusing" >&2; exit 1; }

# Emergency backstop, BEFORE apt and git. Arming the real watchdog needs the
# repo cloned, so a stalled mirror or a hanging clone would still leave a
# RUNNING, unfenced VM — the exact R-01 failure, just earlier in the script
# (round-2 red team). This transient timer needs nothing from the repo.
systemd-run --on-active=3h --timer-property=AccuracySec=1min \
  --unit=learnarken-emergency-poweroff --collect /sbin/poweroff >/dev/null 2>&1 || true

REPO_URL="${1:?usage: provision.sh <git-clone-url> [<commit-sha>]}"
REPO_SHA="${2:-}"
APP_HOME=/opt/learnarken
REPO_DIR="$APP_HOME/LearnArken"

# Pinned images (day10 #12: no :latest — a rebuild must be reproducible).
# Digests are the ones actually pulled on 2026-07-29, the first time this script
# ran on a real machine: a tag is mutable, and `vespaengine/vespa:8` in
# particular is a moving major-version tag (red team R-16). Re-pin deliberately,
# never silently:
#   docker inspect --format '{{index .RepoDigests 0}}' learnarken-vespa
NEO4J_IMAGE="neo4j@sha256:f43cf862a088473a45a6a639f518af89ae6b1a742b6f6efe8317a4cc3ddb00a0"
VESPA_IMAGE="vespaengine/vespa@sha256:cdb44e35f837b38f5f63199a2035f6a17f121d50e02dc9b0ca54e2c7fdfa184a"

phase 'installing packages'
apt-get update
apt-get install -y docker.io git curl python3

# App user WITHOUT the docker group: the docker group is root-equivalent, and
# only the root-owned learnarken-containers.service touches the socket (#11).
id learnarken >/dev/null 2>&1 || useradd -r -m -d "$APP_HOME" -s /bin/bash learnarken

phase 'cloning repo'
if [ ! -d "$REPO_DIR/.git" ]; then
  sudo -u learnarken git clone "$REPO_URL" "$REPO_DIR"
fi
# Pinning only the URL of this script pinned the *script*, not the application
# it deploys: `main` can move between the two, and an existing checkout can be
# any age (round-2 red team). With a SHA, what runs is what was reviewed.
if [ -n "$REPO_SHA" ]; then
  sudo -u learnarken git -C "$REPO_DIR" fetch --quiet origin "$REPO_SHA"
  sudo -u learnarken git -C "$REPO_DIR" checkout --quiet --detach "$REPO_SHA"
  echo "  checked out $REPO_SHA"
else
  echo "  WARNING: no commit sha given — deploying whatever this checkout holds:" >&2
  sudo -u learnarken git -C "$REPO_DIR" rev-parse HEAD >&2
fi

# ---------------------------------------------------------------------------
# Arm the cost fences BEFORE anything slow or fragile (deploy red team R-01).
#
# Provisioning used to install the watchdog last, after the container pulls and
# the multi-GB model download. On 2026-07-29 provisioning failed twice and left
# a RUNNING, unfenced VM billing for ~4.5 h — the fences that make this design
# affordable only existed on the happy path. They now exist from here on.
#
# The watchdog would otherwise power the machine off mid-provision (the API it
# probes is not up yet), so a sentinel suppresses *only* the unreachable-API
# strike. The uptime hard cap is never suppressed, and the sentinel lives in
# /run (tmpfs) so a reboot re-arms the full fence even if provisioning died.
# ---------------------------------------------------------------------------
phase 'arming cost fences before anything slow'
install -m 644 "$REPO_DIR"/deploy/vm/systemd/*.service "$REPO_DIR"/deploy/vm/systemd/*.timer \
  /etc/systemd/system/
mkdir -p /etc/systemd/system/learnarken-demo.service.d
cat > /etc/systemd/system/learnarken-demo.service.d/path.conf <<EOF
[Service]
Environment=PATH=$APP_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
EOF
systemctl daemon-reload
touch /run/learnarken-provisioning
trap 'rm -f /run/learnarken-provisioning' EXIT
systemctl enable --now learnarken-watchdog.timer
# The real fence is armed; the pre-clone backstop has done its job.
systemctl stop learnarken-emergency-poweroff.timer >/dev/null 2>&1 || true

# uv manages its own Python 3.12; the systemd shim/watchdog use system python3.
sudo -u learnarken bash -c 'command -v ~/.local/bin/uv >/dev/null 2>&1 \
  || curl -LsSf https://astral.sh/uv/install.sh | sh'
# --locked: provisioning a live public VM must install the tested resolution,
# not whatever resolves today (R-16).
sudo -u learnarken bash -c "cd $REPO_DIR && ~/.local/bin/uv sync --group demo --locked"

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
# `docker inspect` succeeds for a container that merely *exists*, including a
# stopped one — so on any re-run after a reboot the old `inspect || run` skipped
# creation and then nothing started the containers, leaving provisioning to wait
# on the health of two exited containers until the next `docker exec` failed
# (R-04, second half; seen for real on 2026-07-29). Create it or start it.
# Starting an existing container also has to check WHICH IMAGE it was created
# from, or pinning digests changes nothing on any machine that already has a
# container from the old mutable tag: it would simply be restarted and the run
# would "pass" while serving the unpinned image (round-2 red team).
start_or_run() {
  local name="$1" image="${@: -1}"
  shift
  if docker inspect "$name" >/dev/null 2>&1; then
    local have want
    have="$(docker inspect -f '{{.Image}}' "$name")"
    want="$(docker inspect -f '{{.Id}}' "$image" 2>/dev/null || true)"
    if [ -n "$want" ] && [ "$have" != "$want" ]; then
      echo "  $name was built from a different image — recreating"
      docker rm -f "$name" >/dev/null
      docker run -d --name "$name" "$@" >/dev/null
      return
    fi
    docker start "$name" >/dev/null
  else
    docker run -d --name "$name" "$@" >/dev/null
  fi
}

phase 'starting containers'
start_or_run learnarken-vespa --hostname vespa-container \
  -p 127.0.0.1:8080:8080 -p 127.0.0.1:19071:19071 "$VESPA_IMAGE"
start_or_run learnarken-neo4j \
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
# The loop used to fall through silently on timeout, so a dead container was
# reported four steps later as a confusing `docker exec` failure (R-19).
curl -fsS http://127.0.0.1:19071/state/v1/health >/dev/null 2>&1 \
  && curl -fsS http://127.0.0.1:7474 >/dev/null 2>&1 || {
  echo "STOP: vespa config server and/or neo4j never became healthy:" >&2
  docker ps -a --format '  {{.Names}} {{.Status}}' >&2
  exit 1
}

# Deploy the Vespa application package as root. vespa/store.py deploy() shells
# out to `docker cp`/`docker exec`, and the learnarken user is deliberately not
# in the docker group (#11) — so the index run below would die on the socket
# (R-03). Doing it here means that run finds Vespa up and never calls deploy().
#
# Unconditional, from a cleared staging dir (R-04): gating this on "is :8080
# answering?" would skip the deploy on every re-run, so a changed application
# package would never reach the engine while the corpus manifest recorded the
# new local schema digest — the index would attest a schema it is not serving.
# `docker cp` also merges rather than replaces, hence the rm.
phase 'deploying the vespa application package (root)'
# -u root only for the removal: `docker cp` lands root-owned files, while
# `docker exec` defaults to the image's `vespa` user and cannot delete them.
# `vespa deploy` below stays on the default user, as the image intends.
docker exec -u root learnarken-vespa rm -rf /tmp/learnarken-app
docker cp "$REPO_DIR/src/learnarken/vespa/app/." learnarken-vespa:/tmp/learnarken-app
docker exec learnarken-vespa vespa deploy --wait 120 /tmp/learnarken-app
echo "waiting for the vespa query container ..."
for _ in $(seq 1 150); do
  curl -fsS http://127.0.0.1:8080/state/v1/health >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS http://127.0.0.1:8080/state/v1/health >/dev/null 2>&1 || {
  echo "STOP: vespa deployed but the query container never came up" >&2; exit 1; }

# Feed everything once: indexes package-a+c, syncs the Neo4j graph, and pulls
# the embedding model into the HF cache (multi-GB — this is the slow step,
# done once so cold boots never download).
phase 'indexing corpus + warming the model cache (slowest step)'
sudo -u learnarken bash -c \
  "cd $REPO_DIR && ~/.local/bin/uv run learnarken index samples/package-a samples/package-c --strategy structure"

# The units were installed and the watchdog armed near the top (R-01); the
# serving units come up only now that there is something to serve.
phase 'starting serving units'
systemctl enable --now \
  learnarken-containers.service learnarken-demo.service learnarken-shim.service

echo "provisioned. Set DEMO_GATE_KEY in $APP_HOME/demo.env, then:"
echo "  systemctl restart learnarken-demo && curl -s http://127.0.0.1:8110/demo/status"
