"""Public-demo safety envelope (SPEC day10, red-team day10 #1/#2/#4/#5).

When the backend runs on the internet-exposed VM (``DEMO_PUBLIC=1``) the
loopback assumptions of day 6 no longer hold, so this module adds the fences
the red team required — all fail-closed (INV-4), all off by default so local
``make demo`` and the test suite are unchanged:

- **LLM spend cap** — a process-global daily call quota + a concurrency
  semaphore around the generation path. MiniMax spend is *not* GCP billing, so
  the $20 budget alert cannot see it; this is the only real cost fence on the
  query path. Over quota / at capacity ⇒ refuse, never queue-and-spend.
- **Shared gate key** — state-changing/spending routes require an
  ``X-Demo-Key`` matching ``DEMO_GATE_KEY``; the visitor receives it only by
  arriving through the token status page. A drive-by IP scanner has no key.
- **Upload kill switch** — uploads mutate the shared live corpus and persist
  across visitors, so they are refused outright in public mode.

Quotas reset with the process; the VM is short-lived and auto-shuts after 30
idle minutes, so a per-boot in-memory counter is the right scope.
"""

from __future__ import annotations

import hmac
import os
import threading
import time
from contextlib import contextmanager


class DemoQuotaExceeded(RuntimeError):
    """Spend/concurrency fence tripped — the caller must fail closed (INV-4)."""


# provision.sh seeds demo.env with this so the operator must replace it; the
# guard treats it (and any too-short value) as *unset* so a forgotten
# placeholder fails closed (locked) rather than shipping a working default
# secret (day10 verify: new-issue "known default gate key accepted").
_PLACEHOLDER_KEY = "CHANGE-ME-must-match-the-Cloud-Function-link-key"
_MIN_KEY_LEN = 16


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class DemoGuard:
    def __init__(self) -> None:
        self.public = os.environ.get("DEMO_PUBLIC") == "1"
        key = os.environ.get("DEMO_GATE_KEY", "")
        # A placeholder or weak key counts as unconfigured ⇒ key_ok always False
        # ⇒ the public app stays locked until a real key is set (fail closed).
        self.gate_key = "" if key == _PLACEHOLDER_KEY or len(key) < _MIN_KEY_LEN else key
        self.max_calls = _int_env("DEMO_MAX_LLM_CALLS", 200)  # per VM boot
        self.max_concurrency = _int_env("DEMO_MAX_CONCURRENCY", 2)
        self.allow_upload = os.environ.get("DEMO_ALLOW_UPLOAD") == "1"
        self._lock = threading.Lock()
        self._calls = 0
        self._active = 0
        self._window_start = time.time()

    def key_ok(self, provided: str | None) -> bool:
        """Constant-time compare; open (True) when not in public mode."""
        if not self.public:
            return True
        if not self.gate_key or not provided:
            return False
        return hmac.compare_digest(provided.encode(), self.gate_key.encode())

    def uploads_allowed(self) -> bool:
        return self.allow_upload or not self.public

    @contextmanager
    def llm_slot(self):
        """Reserve one generation slot or raise DemoQuotaExceeded.

        No-op outside public mode. The count is checked *and* incremented under
        the lock so concurrent requests cannot both slip past the last slot.
        """
        if not self.public:
            yield
            return
        with self._lock:
            if self._calls >= self.max_calls:
                raise DemoQuotaExceeded(
                    "the public demo has reached its daily question limit; "
                    "please try again later (fail closed)"
                )
            if self._active >= self.max_concurrency:
                raise DemoQuotaExceeded(
                    "the public demo is busy answering another question; "
                    "please retry in a moment (fail closed)"
                )
            self._calls += 1
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1


GUARD = DemoGuard()
