"""Pure decision logic for the demo trigger function (SPEC day10).

Kept free of GCP imports so the unit tests exercise it directly:
token resolution, start rate-limiting, and the page-state mapping.
"""

from __future__ import annotations

import hmac

MIN_START_INTERVAL_S = 60 * 60  # one start per token per hour (Decision 4)
# Global anti-hammering floor on real machine starts, enforced from the VM's own
# lastStartTimestamp so it survives function cold starts (red team R-15).
MIN_GLOBAL_START_INTERVAL_S = 5 * 60

# GCE instance statuses, mapped onto the page's four visitor-facing states
# (Decision 3: closed / starting / running / closing — every state has a next
# action, an unknown status fails closed to "closed").
_STARTING = {"PROVISIONING", "STAGING", "REPAIRING"}
_CLOSING = {"STOPPING", "SUSPENDING"}


def resolve_token(token: str, tokens: dict[str, str]) -> str | None:
    """Return the recipient label for a valid token, else None.

    Scans every entry with a constant-time compare so a mismatch reveals
    nothing about how close the guess was.
    """
    found = None
    for known, recipient in tokens.items():
        if hmac.compare_digest(token.encode(), known.encode()):
            found = recipient
    return found


def start_floor_seconds_left(last_start_epoch: float | None, now: float) -> float:
    """Seconds until another *machine* start is allowed, from the VM's own
    `lastStartTimestamp`.

    The per-token history below lives in one function instance's memory, so a
    cold start or the second instance forgets it entirely (red team R-15). This
    floor is global, needs no extra IAM permission and no writes, and survives
    everything.

    Deliberately much shorter than the per-token hour: this one is anti-hammering
    only. Making it an hour would lock out a *legitimate* second recipient who
    clicks after the idle watchdog powered the VM off — one visitor would consume
    the whole hour for everybody. Returns 0.0 when a start is allowed.
    """
    if last_start_epoch is None:
        return 0.0
    return max(0.0, MIN_GLOBAL_START_INTERVAL_S - (now - last_start_epoch))


def is_rate_limited(history: dict[str, float], token: str, now: float) -> bool:
    """Read-only per-token rate check (in-memory per function instance).

    The hard cost fences are elsewhere (30-min idle shutdown, budget alerts);
    this only stops casual restart-hammering. Kept read-only so a start that
    never happens (transient Compute API error) does not burn the token's hour
    (day10 #9) — the caller records the timestamp only after a real start.
    """
    last = history.get(token)
    return last is not None and now - last < MIN_START_INTERVAL_S


def record_start(history: dict[str, float], token: str, now: float) -> None:
    """Mark a *successful* start so the next one is rate-limited."""
    history[token] = now


def page_state(instance_status: str | None, app_ready: bool) -> str:
    """Map (GCE status, app self-check) to the visitor-facing state."""
    if instance_status == "RUNNING":
        return "running" if app_ready else "starting"
    if instance_status in _STARTING:
        return "starting"
    if instance_status in _CLOSING:
        return "closing"
    return "closed"
