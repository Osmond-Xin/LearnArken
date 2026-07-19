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
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BACKEND_STATUS_URL = "http://127.0.0.1:8100/demo/status"
BIND = ("0.0.0.0", 8110)
CACHE_TTL_S = 3.0  # collapse a flood of pollers into one backend probe / 3s (day10 #10)

_cache_lock = threading.Lock()
_cache: dict[str, object] = {"at": 0.0, "code": 0, "payload": None}


def _fetch_status() -> tuple[int, dict]:
    """Backend probe behind a tiny TTL cache so a poll flood cannot amplify
    into one backend hit per request (day10 #10). Fail closed on error."""
    now = time.time()
    with _cache_lock:
        if _cache["payload"] is not None and now - float(_cache["at"]) < CACHE_TTL_S:
            return int(_cache["code"]), _cache["payload"]  # type: ignore[return-value]
    try:
        with urllib.request.urlopen(BACKEND_STATUS_URL, timeout=5) as resp:
            code, payload = 200, json.load(resp)
    except Exception:
        code, payload = 502, {"status": "unreachable"}
    with _cache_lock:
        _cache.update(at=now, code=code, payload=payload)
    return code, payload


class StatusHandler(BaseHTTPRequestHandler):
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
    ThreadingHTTPServer(BIND, StatusHandler).serve_forever()


if __name__ == "__main__":
    main()
