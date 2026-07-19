"""Cloud Function (gen2) gating the on-demand demo VM (SPEC day10).

Three routes behind one HTTP entrypoint, every one token-gated:

- ``GET  /?t=<token>``          -> the status/guide page (index.html)
- ``GET  /api/state?t=<token>`` -> {state, vm_ip, services} for the page's poll
- ``POST /api/start?t=<token>`` -> rate-limited ``instances.start`` + notify

The function is the *stopped-half* status source (compute API); once the VM
runs, the page polls the VM's status shim directly for the live countdown.
Emails go to Yi Xin only (click + first-ready); a visitor learns readiness
from the page itself. Email failures never break the page (best effort).

Environment: GCP_PROJECT, GCP_ZONE, VM_NAME, TOKENS_JSON,
SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS, NOTIFY_EMAIL.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import time
import urllib.request
from email.message import EmailMessage
from pathlib import Path

import hashlib

import functions_framework
from google.cloud import compute_v1

from logic import is_rate_limited, page_state, record_start, resolve_token

logger = logging.getLogger("demo-trigger")

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


def _external_ip(instance: compute_v1.Instance) -> str | None:
    for nic in instance.network_interfaces:
        for cfg in nic.access_configs:
            if cfg.nat_i_p:
                return cfg.nat_i_p
    return None


def _app_status(ip: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{ip}:8110/demo/status", timeout=4) as resp:
            return json.load(resp)
    except Exception:
        return None


def _notify(subject: str, body: str) -> None:
    """Best-effort email to Yi Xin — never let mail break the page."""
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
            _notify(
                f"[LearnArken demo] ready — {recipient}",
                f"Stack is up and self-check passed. Demo: {demo_url}",
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
        if is_rate_limited(_start_history, token, now):
            return _json(
                {"error": "rate limited: this link can start the stack once per hour"}, 429
            )
        instance = _instance()
        if instance.status in ("TERMINATED", "SUSPENDED"):
            compute_v1.InstancesClient().start(
                project=os.environ["GCP_PROJECT"],
                zone=os.environ["GCP_ZONE"],
                instance=os.environ["VM_NAME"],
            )
            # Record only after the start call actually succeeded, so a transient
            # Compute API error does not burn the recipient's hour (day10 #9).
            record_start(_start_history, token, now)
            _ready_notified.discard(recipient)
            logger.info("VM start issued tag=%s", _tok_tag(token))
            _notify(
                f"[LearnArken demo] started by {recipient}",
                f"Token holder '{recipient}' clicked start at {time.strftime('%F %T %z')}.",
            )
        return _json({"state": "starting"})

    return _json({"error": "not found"}, 404)
