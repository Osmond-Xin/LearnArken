"""Cloud Function (gen2) gating the on-demand demo VM (SPEC day10).

Three routes behind one HTTP entrypoint, every one token-gated:

- ``GET  /?t=<token>``          -> the status/guide page (index.html)
- ``GET  /api/state?t=<token>`` -> {state, vm_ip, services} for the page's poll
- ``POST /api/start?t=<token>`` -> rate-limited ``instances.start`` + notify

The function is the *stopped-half* status source (compute API); once the VM
runs, the page polls the VM's status shim directly for the live countdown.
A visitor learns readiness from the page itself. Email is **optional and off**
in production (2026-07-29: applications go out via LinkedIn and web forms, so
there is no sending mailbox) — the click record is the function log, keyed by
recipient label. Email failures never break the page (best effort).

Environment: GCP_PROJECT, GCP_ZONE, VM_NAME, TOKENS_JSON, DEMO_GATE_KEY;
optionally SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS + NOTIFY_EMAIL.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import smtplib
import time
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import functions_framework
from google.cloud import compute_v1
from logic import (
    START_LOCK_LABEL,
    is_rate_limited,
    page_state,
    plan_start_lock,
    record_start,
    release_start_lock,
    resolve_token,
    start_floor_seconds_left,
)

# INFO must actually be emitted. Python's default root level is WARNING and the
# last-resort handler drops anything below it, so the click record — the ONLY
# interest signal now that email is off — was written and silently discarded
# (found by reading the deployed function's logs, 2026-07-29). Cloud Run
# captures stderr, so a basicConfig at import is enough.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo-trigger")
logger.setLevel(logging.INFO)

# Applied to every response: token-bearing pages/APIs must not be cached by
# browsers or proxies, and must not leak the token via Referer or framing
# (day10 #6/#15).
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
}


def _tok_tag(token: str) -> str:
    """A short hash prefix for logs — never the raw token (day10 #6/#13)."""
    return hashlib.sha256(token.encode()).hexdigest()[:8] if token else "none"


_PAGE = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
_TOKENS: dict[str, str] = json.loads(os.environ.get("TOKENS_JSON", "{}"))
_GATE_KEY = os.environ.get("DEMO_GATE_KEY", "")
# Per-instance memory: best-effort rate limit + ready-email dedupe. A cold
# start forgets both; the hard cost fences live on the VM and the budget.
_start_history: dict[str, float] = {}
_ready_notified: set[str] = set()


def _instance() -> compute_v1.Instance:
    client = compute_v1.InstancesClient()
    return client.get(
        project=os.environ["GCP_PROJECT"],
        zone=os.environ["GCP_ZONE"],
        instance=os.environ["VM_NAME"],
    )


def _last_start_epoch(instance: compute_v1.Instance) -> float | None:
    """`lastStartTimestamp` (RFC3339) as epoch seconds, or None if unset/odd."""
    raw = getattr(instance, "last_start_timestamp", "") or ""
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def _external_ip(instance: compute_v1.Instance) -> str | None:
    for nic in instance.network_interfaces:
        for cfg in nic.access_configs:
            if cfg.nat_i_p:
                return cfg.nat_i_p
    return None


# Start-lock outcomes. Three, not two: "somebody else is starting it" and "the
# lock machinery is broken" must not lead to the same response, or a missing IAM
# permission turns every Start click into a 200 that starts nothing (red team
# 2026-07-29 P1 — and the deployed custom role really did lack
# `compute.instances.setLabels`, so this was live, not theoretical).
LOCK_WON, LOCK_HELD, LOCK_ERROR = "won", "held", "error"
# HTTP codes GCE returns when the fingerprint we sent was already superseded.
_LOCK_CONTENDED_CODES = (409, 412)
# After a write failure, stop trying for a while: pointless label writes under a
# broken permission or a rate limit are pure churn (red team 2026-07-29 P2).
_LOCK_WRITE_BACKOFF_S = 300
# Bounded wait on the start operation itself; the function's HTTP budget is 60 s.
_START_OP_TIMEOUT_S = 20
_lock_write_broken_until = 0.0


def _set_labels(labels: dict[str, str], fingerprint: str) -> None:
    compute_v1.InstancesClient().set_labels(
        project=os.environ["GCP_PROJECT"],
        zone=os.environ["GCP_ZONE"],
        instance=os.environ["VM_NAME"],
        instances_set_labels_request_resource=compute_v1.InstancesSetLabelsRequest(
            labels=labels,
            label_fingerprint=fingerprint,
        ),
    )


def _lock_is_live(instance: compute_v1.Instance, now: float) -> bool:
    return plan_start_lock(dict(instance.labels or {}), now) is None


def _take_start_lock(instance: compute_v1.Instance, now: float, tag: str) -> tuple[str, str | None]:
    """Try to take the start lock; returns (outcome, the value we wrote).

    The compare-and-swap is GCE's `labelFingerprint` precondition: the write
    carries the fingerprint read a moment ago, so of two concurrent writers the
    loser is told the fingerprint is stale. Losing is not an error for the
    visitor, because whoever won is starting the very machine they asked for
    (same reasoning as S-07).

    **Anything unresolved is `LOCK_ERROR`, and the caller starts the VM anyway.**
    The lock is defence in depth over an operation measured to be idempotent at
    GCE; it is not permitted to become a new hard dependency in front of the one
    call this function exists to make.
    """
    global _lock_write_broken_until
    labels = plan_start_lock(dict(instance.labels or {}), now)
    if labels is None:
        logger.info("start lock held by a concurrent request tag=%s", tag)
        return LOCK_HELD, None
    # Backoff is consulted only *after* establishing that no live lock exists.
    # Checking it first let one transient write failure make this function
    # instance ignore a lock the other instance legitimately holds — the fix
    # growing its own bug (red team round 2, 2026-07-29 P2).
    if now < _lock_write_broken_until:
        logger.warning("start lock skipped: label writes failed recently tag=%s", tag)
        return LOCK_ERROR, None
    try:
        _set_labels(labels, instance.label_fingerprint)
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code in _LOCK_CONTENDED_CODES:
            # A stale fingerprint does **not** prove a starter won the race: any
            # label edit invalidates it. Re-read before telling a visitor their
            # demo is starting when nothing is (red team round 2 P2).
            try:
                fresh = _instance()
            except Exception:
                logger.exception("start lock re-read failed after %s tag=%s", code, tag)
                return LOCK_ERROR, None
            if _lock_is_live(fresh, now):
                logger.info("start lock lost the fingerprint race (%s) tag=%s", code, tag)
                return LOCK_HELD, None
            logger.info("labels changed under us (%s) but no lock is held tag=%s", code, tag)
            return LOCK_ERROR, None
        # Permission, quota, outage: name it. "another request holds it, or the
        # write failed" made a broken deployment indistinguishable from healthy
        # contention in the logs (red team 2026-07-29 P2).
        _lock_write_broken_until = now + _LOCK_WRITE_BACKOFF_S
        logger.exception(
            "start lock write failed (%s: %s) tag=%s — starting unlocked",
            type(exc).__name__,
            code,
            tag,
        )
        return LOCK_ERROR, None
    return LOCK_WON, labels[START_LOCK_LABEL]


def _release_start_lock(value: str) -> None:
    """Best-effort release after the winner's own start failed.

    Re-reads the instance because our own write invalidated the fingerprint we
    were holding — and checks the lock still carries **our** value before
    dropping it. Without that check, a start that hung past the TTL would come
    back and delete the lock a later request had legitimately taken (red team
    round 2, 2026-07-29 P2). Never raises: this runs on a path that is already
    returning an error to the visitor.
    """
    try:
        instance = _instance()
        labels = dict(instance.labels or {})
        if labels.get(START_LOCK_LABEL) != value:
            logger.info("start lock not released: it is no longer the one we took")
            return
        _set_labels(release_start_lock(labels), instance.label_fingerprint)
    except Exception:
        logger.exception("start lock release failed (it will expire on its own)")


def _await_start(operation) -> None:
    """Surface an asynchronous start failure as an exception.

    `instances.start` returns a zone operation: the API call succeeding only
    means GCE accepted the request. A stockout — observed here on 2026-07-29 —
    can land on the *operation*, and the previous version reported that as
    `starting`, recorded the token's hour, and never released the lock (red team
    round 2, 2026-07-29 P2).

    Bounded, because the caller is an HTTP request with a 60 s budget. Still
    running when the wait expires is not a failure: the visitor is told
    `starting`, which is exactly what it is.
    """
    waiter = getattr(operation, "result", None)
    if not callable(waiter):
        return
    try:
        waiter(timeout=_START_OP_TIMEOUT_S)
    except TimeoutError:
        logger.info(
            "start operation still running after %ss — reported as starting", _START_OP_TIMEOUT_S
        )


def _app_status(ip: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{ip}:8110/demo/status", timeout=4) as resp:
            return json.load(resp)
    except Exception:
        return None


def _notify(subject: str, body: str) -> None:
    """Best-effort email — never let mail break the page.

    Optional by design (Yi Xin, 2026-07-29): applications go out through
    LinkedIn and web forms, not from a mailbox, so there is no Gmail account to
    send from. With SMTP unset this is a clean no-op and the click record lives
    in the function log instead (see `_log_visit`) — not an exception swallowed
    by the handler below, which would look identical to a real delivery failure.
    """
    if not all(os.environ.get(name) for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS")):
        return
    try:
        msg = EmailMessage()
        msg["From"] = os.environ["SMTP_USER"]
        msg["To"] = os.environ["NOTIFY_EMAIL"]
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as smtp:
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            smtp.send_message(msg)
    except Exception:
        logger.exception("notification email failed (ignored)")


def _json(payload: dict, code: int = 200):
    return (json.dumps(payload), code, {"Content-Type": "application/json", **_SECURITY_HEADERS})


@functions_framework.http
def demo_gate(request):
    token = request.args.get("t", "")
    recipient = resolve_token(token, _TOKENS)
    if recipient is None:
        logger.warning("rejected request: unknown token tag=%s", _tok_tag(token))
        return (
            "Forbidden: missing or unknown token.",
            403,
            {"Content-Type": "text/plain", **_SECURITY_HEADERS},
        )

    path = request.path.rstrip("/") or "/"

    if path == "/" and request.method == "GET":
        # The click record. With email optional (Yi Xin, 2026-07-29: applications
        # go out via LinkedIn and web forms, so there is no sending mailbox), the
        # function log is the *only* channel that answers "who opened the link" —
        # so it logs the recipient label, not just the token's hash tag.
        #   gcloud functions logs read learnarken-demo-gate --region=us-central1 \
        #     --gen2 --limit=50 | grep 'demo link opened'
        logger.info("demo link opened by recipient=%s tag=%s", recipient, _tok_tag(token))
        return (
            _PAGE,
            200,
            {"Content-Type": "text/html; charset=utf-8", **_SECURITY_HEADERS},
        )

    if path == "/api/state" and request.method == "GET":
        instance = _instance()
        ip = _external_ip(instance)
        app_status = _app_status(ip) if instance.status == "RUNNING" and ip else None
        ready = bool(app_status and app_status.get("status") == "ready")
        state = page_state(instance.status, ready)
        # The demo link carries the shared gate key so the visitor's Streamlit
        # (and the backend) accept their session (day10 #1). The key lives only
        # in the function's env, never in client JS.
        demo_url = f"http://{ip}:8501/?k={_GATE_KEY}" if ready and ip else None
        if state == "running" and recipient not in _ready_notified:
            _ready_notified.add(recipient)
            # Never mail `demo_url`: it embeds DEMO_GATE_KEY, and mail is stored,
            # forwarded and indexed far beyond this inbox (day10 red team R-12).
            # The visitor gets the keyed link from the page; this is only a ping.
            _notify(
                f"[LearnArken demo] ready — {recipient}",
                "Stack is up and the self-check passed; the status page has "
                "handed the visitor their demo link.",
            )
        return _json(
            {
                "state": state,
                "demo_url": demo_url,
                "services": (app_status or {}).get("services"),
                "idle_seconds": (app_status or {}).get("idle_seconds"),
            }
        )

    if path == "/api/start" and request.method == "POST":
        now = time.time()
        # State first, limits second. Rate-limiting before knowing whether a
        # start is even needed turned an already-running stack into a 429: a
        # lost response, a double click or a browser retry showed the visitor an
        # error while their demo was booting fine (round-2 red team). Nothing is
        # limited unless a real, billable start is about to be issued.
        instance = _instance()
        if instance.status not in ("TERMINATED", "SUSPENDED"):
            return _json({"state": "starting"})

        if is_rate_limited(_start_history, token, now):
            return _json(
                {"error": "rate limited: this link can start the stack once per hour"}, 429
            )
        # The floor survives a function cold start because it reads the VM, not
        # this instance's memory (R-15).
        left = start_floor_seconds_left(_last_start_epoch(instance), now)
        if left > 0:
            return _json(
                {
                    "error": "rate limited: the stack was started very "
                    f"recently, retry in {int(left)}s"
                },
                429,
            )
        # Last gate before the only billable call in this function: exactly one
        # concurrent request may proceed. Placed after the limits so a request
        # that was going to be refused anyway never churns the VM's labels.
        # LOCK_ERROR deliberately falls through to the start — see _take_start_lock.
        lock, lock_value = _take_start_lock(instance, now, _tok_tag(token))
        if lock == LOCK_HELD:
            return _json({"state": "starting"})
        try:
            operation = compute_v1.InstancesClient().start(
                project=os.environ["GCP_PROJECT"],
                zone=os.environ["GCP_ZONE"],
                instance=os.environ["VM_NAME"],
            )
            # The API returning is only GCE *accepting* the request; the failure
            # can land on the operation (red team round 2 P2).
            _await_start(operation)
        except Exception:
            # A zone stockout is a real, observed outcome (e2-highmem-8 was
            # unavailable in us-central1-a on 2026-07-29). Say so instead of
            # returning a 500 the page renders as a dead button.
            logger.exception("instances.start failed tag=%s", _tok_tag(token))
            if lock_value is not None:
                # Hand the lock back rather than letting it answer the next
                # visitor with "starting" for two minutes while nothing is
                # starting — and a stockout is exactly when someone retries.
                _release_start_lock(lock_value)
            return _json(
                {"error": "the demo host could not be started right now — please retry shortly"},
                503,
            )
        # Recorded only after the start call actually succeeded, so a transient
        # Compute API error does not burn the recipient's hour (day10 #9).
        record_start(_start_history, token, now)
        _ready_notified.discard(recipient)
        logger.info("VM start issued by recipient=%s tag=%s", recipient, _tok_tag(token))
        _notify(
            f"[LearnArken demo] started by {recipient}",
            f"Token holder '{recipient}' clicked start at {time.strftime('%F %T %z')}.",
        )
        return _json({"state": "starting"})

    return _json({"error": "not found"}, 404)
