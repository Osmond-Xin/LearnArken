"""Public read-only status shim for the on-demand demo VM (SPEC day10).

The FastAPI backend stays loopback-only (its day-6 security envelope is
unchanged); the only things exposed to the internet on the VM are Streamlit
(:8501) and this shim (:8110), which serves exactly one path — a GET proxy of
the loopback `/demo/status` self-check. Everything else is refused. CORS is
open on purpose: the status page (served from the Cloud Function origin)
polls this directly for the live countdown.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BACKEND_STATUS_URL = "http://127.0.0.1:8100/demo/status"
BIND = ("0.0.0.0", 8110)
CACHE_TTL_S = 3.0  # collapse a flood of pollers into one backend probe / 3s (day10 #10)

_cache_lock = threading.Lock()
_cache: dict[str, object] = {"at": 0.0, "code": 0, "payload": None}


def _public_view(payload: dict) -> dict:
    """Only the fields the status page needs.

    The backend payload also carries `started_at` and `last_business_activity`,
    which let anyone holding the VM's IP reconstruct when the demo was used and
    by roughly how much (deploy red team R-18). The page needs liveness and a
    countdown, nothing else.
    """
    if not isinstance(payload, dict):
        return {"status": "unreachable"}
    return {key: payload[key] for key in ("status", "services", "idle_seconds") if key in payload}


def _fetch_status() -> tuple[int, dict]:
    """Backend probe behind a tiny TTL cache so a poll flood cannot amplify
    into one backend hit per request (day10 #10). Fail closed on error.

    The lock is held across the fetch (single-flight): releasing it first meant
    that every poller arriving in the window between expiry and refill launched
    its own backend request, so the cache stopped collapsing the flood exactly
    when the flood was largest (R-18).
    """
    with _cache_lock:
        if _cache["payload"] is not None and time.time() - float(_cache["at"]) < CACHE_TTL_S:
            return int(_cache["code"]), _cache["payload"]  # type: ignore[return-value]
        try:
            with urllib.request.urlopen(BACKEND_STATUS_URL, timeout=5) as resp:
                code, payload = 200, _public_view(json.load(resp))
        except Exception as exc:
            # The one failure worth a line in the journal: the public page is
            # showing "unreachable" and this says why (R-19).
            print(f"shim: backend probe failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            code, payload = 502, {"status": "unreachable"}
        # Stamped after the fetch, not before: a probe slower than CACHE_TTL_S
        # would otherwise be born expired, so every waiting poller took the lock
        # and made its own 5 s backend call in turn (round-2 red team).
        _cache.update(at=time.time(), code=code, payload=payload)
        return code, payload


class StatusHandler(BaseHTTPRequestHandler):
    timeout = 10  # per-connection read timeout; a silent client is dropped

    def _reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if self.path.split("?")[0] != "/demo/status":
            self._reply(404, {"error": "not found"})
            return
        code, payload = _fetch_status()
        self._reply(code, payload)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # journald noise control; systemd captures stderr if needed


def main() -> None:
    server = ThreadingHTTPServer(BIND, StatusHandler)
    # Bound what a public port can hold: daemon threads so a stalled peer cannot
    # keep the process alive, and a read timeout so a slowloris client cannot
    # pin a thread indefinitely (R-18).
    server.daemon_threads = True
    server.timeout = 10
    server.serve_forever()


if __name__ == "__main__":
    main()
