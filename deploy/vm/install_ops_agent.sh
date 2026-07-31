#!/usr/bin/env bash
# Ship the VM's journal to Cloud Logging (2026-07-30).
# Run as root on the demo VM:  sudo bash install_ops_agent.sh
#
# Why this exists: a real visitor arrived on 2026-07-30, clicked start, and the
# VM ran its full 34 minutes — and the only trace anywhere was the gate
# function's "demo link opened" line. Everything the visitor did *on* the demo
# lived in journald on an ephemeral machine and died with it. This makes the
# journal outlive the boot.
#
# Its own script, not a block inside provision.sh, because the VM it is meant
# for is already provisioned: re-running provision.sh would re-pull containers,
# re-sync uv and redeploy Vespa to install one agent. provision.sh calls this
# too, so a machine built from scratch gets it as well. Idempotent.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root: sudo bash $0" >&2
  exit 1
fi

# Exit codes, so a caller can tell "logging was never asked for" apart from
# "logging was asked for and is broken" — provision.sh treats the first as a
# machine deliberately built without an identity and the second as fatal
# (round-2 red team P1).
EX_NOT_REQUESTED=78

# Least privilege is the whole design of this VM (it carried no service account
# at all until today), so the agent gets exactly one credential — logWriter —
# and this check fails closed rather than installing an agent that will spend
# the boot retrying 403s. See deploy/runbook.md §9 for the grant.
SCOPES_URL='http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/scopes'
if ! scopes=$(curl -fsS -H 'Metadata-Flavor: Google' "$SCOPES_URL" 2>/dev/null); then
  echo "this VM has no service account attached — nothing could be sent anywhere." >&2
  echo "attach one first (runbook §9) if this machine is meant to keep logs." >&2
  exit "$EX_NOT_REQUESTED"
fi
case "$scopes" in
  *logging.write* | *cloud-platform*) ;;
  *)
    echo "service account is attached but lacks the logging.write scope:" >&2
    echo "$scopes" >&2
    exit 1
    ;;
esac

# Google's apt repo, signed key, major version 2 — piping Google's install
# script into a root shell would install whatever it resolves to today and is
# not reviewable.
install -d -m 755 /usr/share/keyrings
KEYRING=/usr/share/keyrings/cloud.google.gpg
FINGERPRINT_FILE=/etc/learnarken-ops-agent.keyfingerprint
if [ ! -s "$KEYRING" ]; then
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o "$KEYRING"
fi
# Trust on first use, checked on every use. A fingerprint copied out of a doc
# from memory would be worse than no check at all — this records what was
# actually trusted the first time and refuses to continue if it ever changes.
# Compare it against Google's published key once, by hand, and it is pinned.
current_fp=$(gpg --show-keys --with-colons "$KEYRING" | awk -F: '/^fpr:/ {print $10; exit}')
if [ -s "$FINGERPRINT_FILE" ]; then
  if [ "$current_fp" != "$(cat "$FINGERPRINT_FILE")" ]; then
    echo "the Google apt signing key changed since this VM first trusted it:" >&2
    echo "  recorded: $(cat "$FINGERPRINT_FILE")" >&2
    echo "  now:      $current_fp" >&2
    echo "refusing to install. Verify against Google's published key by hand." >&2
    exit 1
  fi
else
  printf '%s\n' "$current_fp" > "$FINGERPRINT_FILE"
  echo "recorded apt signing key fingerprint: $current_fp"
fi

cat > /etc/apt/sources.list.d/google-cloud-ops-agent.list <<'EOF'
deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt google-cloud-ops-agent-bookworm-2 main
EOF
apt-get update

# Exact version, then held: "major 2" still lets an unattended upgrade swap the
# agent under a live demo. The version is whatever the repo offers the first
# time this runs, and is then *enforced* — a re-run against a machine whose
# agent drifted (or was never held) refuses rather than reporting success over
# an unknown build (round-2 red team P2).
VERSION_FILE=/etc/learnarken-ops-agent.version
if ! dpkg -s google-cloud-ops-agent >/dev/null 2>&1; then
  AGENT_VERSION=$(apt-cache policy google-cloud-ops-agent | awk '/Candidate:/ {print $2}')
  [ -n "$AGENT_VERSION" ] && [ "$AGENT_VERSION" != "(none)" ] || {
    echo "no google-cloud-ops-agent candidate in the repo — refusing" >&2
    exit 1
  }
  apt-get install -y "google-cloud-ops-agent=$AGENT_VERSION"
  printf '%s\n' "$AGENT_VERSION" > "$VERSION_FILE"
fi

installed=$(dpkg-query -W -f='${Version}' google-cloud-ops-agent)
if [ -s "$VERSION_FILE" ] && [ "$installed" != "$(cat "$VERSION_FILE")" ]; then
  echo "installed ops agent $installed does not match the pinned $(cat "$VERSION_FILE")." >&2
  echo "Upgrading is a deliberate act:" >&2
  echo "  apt-mark unhold google-cloud-ops-agent && apt-get install -y google-cloud-ops-agent" >&2
  echo "  then record the new version in $VERSION_FILE and re-run this script." >&2
  exit 1
fi
# Re-applied every run, not only on first install: an unheld package is one
# unattended upgrade away from changing under a live demo. The flip side is that
# a held package stops receiving security fixes — the upgrade path above is the
# intended way out, and it is a decision, not a default.
apt-mark hold google-cloud-ops-agent >/dev/null
echo "ops agent version: $installed (held)"

# Metrics are deliberately off: sending them needs monitoring.metricWriter,
# which this VM's service account does not have, so leaving the built-in metrics
# pipeline enabled would produce a steady stream of 403s in the agent's own log
# for the whole boot. Logs are what was asked for; metrics are not worth a
# second role.
install -d -m 755 /etc/google-cloud-ops-agent
cat > /etc/google-cloud-ops-agent/config.yaml <<'EOF'
logging:
  receivers:
    journal:
      type: systemd_journald
  service:
    pipelines:
      journal:
        receivers: [journal]
metrics:
  service:
    pipelines:
      default_pipeline:
        receivers: []
EOF

systemctl enable google-cloud-ops-agent
systemctl restart google-cloud-ops-agent

# A scope is not a permission. The scope check at the top passes even when the
# IAM role was never granted or was later removed, and the agent then spends the
# whole boot retrying 403s while the operator believes the visit is being
# recorded. So: emit a marker, give the agent a moment, and read its own log for
# a refusal. Silence here is the only evidence available on-box that ingestion
# is actually working — the VM cannot read Cloud Logging back (logWriter is
# write-only, deliberately).
MARKER="learnarken-ops-smoke $(date -u +%FT%TZ)"
logger -t learnarken-ops-smoke -- "$MARKER"
sleep 20
if journalctl -u google-cloud-ops-agent --since '2 min ago' --no-pager 2>/dev/null \
  | grep -qiE 'permissiondenied|403|unauthenticated'; then
  echo "the agent is being refused by Cloud Logging — check the IAM grant:" >&2
  journalctl -u google-cloud-ops-agent --since '2 min ago' --no-pager \
    | grep -iE 'permissiondenied|403|unauthenticated' | tail -5 >&2
  exit 1
fi

cat <<EOF
ops agent installed; journald now ships to Cloud Logging.
Confirm from your laptop that the marker arrived (the VM cannot check for you):
  gcloud logging read 'resource.type="gce_instance" AND textPayload:"$MARKER"' --limit=1
EOF
