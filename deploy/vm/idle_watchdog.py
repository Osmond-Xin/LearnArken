"""Idle watchdog for the on-demand demo VM (SPEC day10, Decision 4).

Runs as a systemd oneshot on a 1-minute timer. Every fence fails toward
*off* — the machine costs money, so any ambiguity resolves to shutdown:

- business-idle >= IDLE_LIMIT_S (30 min)            -> shutdown
- uptime >= HARD_CAP_S (3 h), even if active        -> shutdown (fence ②)
- /demo/status unreachable FAIL_LIMIT runs in a row -> shutdown

The idle clock comes from the API's `/demo/status` (loopback), which only
business endpoints advance — status polling never resets it (unknowns T1).
The consecutive-failure count lives under /run (tmpfs, cleared on boot).
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import urllib.request
from pathlib import Path

STATUS_URL = "http://127.0.0.1:8100/demo/status"
IDLE_LIMIT_S = 30 * 60
HARD_CAP_S = 3 * 60 * 60
FAIL_LIMIT = 10  # x 1-minute timer = 10 minutes of unreachable/unparseable API
FAIL_COUNT_FILE = Path("/run/learnarken-watchdog-fails")

KEEP = "keep"
SHUTDOWN_IDLE = "shutdown_idle"
SHUTDOWN_CAP = "shutdown_cap"


def decide(
    idle_seconds: float,
    uptime_seconds: float,
    idle_limit_s: float = IDLE_LIMIT_S,
    hard_cap_s: float = HARD_CAP_S,
) -> str:
    """Pure decision: the hard cap wins over everything, then the idle fence."""
    if uptime_seconds >= hard_cap_s:
        return SHUTDOWN_CAP
    if idle_seconds >= idle_limit_s:
        return SHUTDOWN_IDLE
    return KEEP


def vm_uptime_seconds() -> float:
    """True VM uptime from the kernel — not the API process's start time.

    The API can restart (systemd Restart=on-failure) and reset its own clock;
    the hard cap must track the machine, so a restart cannot grant a fresh 3h
    (day10 #3). Unreadable /proc/uptime returns +inf ⇒ the cap fires (fail
    closed toward shutdown).
    """
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return math.inf


def _finite(value: object) -> float | None:
    """Coerce a status field to a finite number, else None (bad input)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _read_fail_count() -> int:
    try:
        return int(FAIL_COUNT_FILE.read_text())
    except (OSError, ValueError):
        return 0


def _strike(reason: str) -> None:
    """Count a fail-closed strike; shut down once the API is persistently bad."""
    fails = _read_fail_count() + 1
    FAIL_COUNT_FILE.write_text(str(fails))
    print(f"watchdog: {reason}, strike {fails}/{FAIL_LIMIT}")
    if fails >= FAIL_LIMIT:
        _shutdown("api unreachable/invalid — fail closed to off")


def _shutdown(reason: str) -> None:
    print(f"watchdog: shutting down ({reason})")
    subprocess.run(["systemctl", "poweroff"], check=False)


def main() -> int:
    # The hard cap is enforced from kernel uptime regardless of the API — a
    # wedged or malformed backend can never hold the VM past HARD_CAP_S.
    if vm_uptime_seconds() >= HARD_CAP_S:
        _shutdown(SHUTDOWN_CAP)
        return 0

    try:
        with urllib.request.urlopen(STATUS_URL, timeout=10) as resp:
            status = json.load(resp)
    except Exception as exc:
        _strike(f"status unreachable ({type(exc).__name__})")
        return 0

    idle = _finite(status.get("idle_seconds")) if isinstance(status, dict) else None
    if idle is None:
        # Reachable but malformed/renamed field: treat as a strike, never crash
        # (a persistently bad schema must fail closed, not run forever).
        _strike("status missing a finite idle_seconds")
        return 0

    FAIL_COUNT_FILE.write_text("0")
    action = decide(idle, vm_uptime_seconds())
    if action == KEEP:
        print(f"watchdog: keep (idle {idle:.0f}s)")
    else:
        _shutdown(action)
    return 0


if __name__ == "__main__":
    sys.exit(main())
