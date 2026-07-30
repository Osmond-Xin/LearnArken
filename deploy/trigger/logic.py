"""Pure decision logic for the demo trigger function (SPEC day10).

Kept free of GCP imports so the unit tests exercise it directly:
token resolution, start rate-limiting, and the page-state mapping.
"""

from __future__ import annotations

import hmac
import math

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


# --- Start lock -------------------------------------------------------------
#
# Two visitors clicking *Start* in the same instant can both read TERMINATED and
# both call `instances.start`. Measured on the deployed project (Part 1c), that
# is harmless — the call is idempotent at GCE and produced one machine with one
# `lastStartTimestamp` — so this lock is defence in depth, ruled in by Yi Xin on
# 2026-07-29 after the measurement, not a fix for an observed fault.
#
# The CAS primitive is GCE's own `labelFingerprint` precondition: writing labels
# with a stale fingerprint fails 412, so exactly one of two concurrent writers
# wins. That keeps the lock inside the API and the IAM role the function already
# uses — no Firestore, no second service that can be down, which was the whole
# argument against locking in the first place.
START_LOCK_LABEL = "demo-start-lock"
START_LOCK_TTL_S = 120  # covers read→start; the 5-minute floor takes over after
# A lock stamped later than this many seconds ahead of now is not a lock, it is
# a broken value: clock skew between the writer and this reader is seconds, not
# minutes (red team 2026-07-29 P1).
START_LOCK_MAX_SKEW_S = 5


def start_lock_seconds_left(label_value: str | None, now: float) -> float:
    """Seconds a live start lock still holds; 0.0 when it is free.

    **Every unusable value fails open**, because of what the two failure
    directions cost. This lock guards an operation measured to be idempotent at
    GCE, so releasing too eagerly costs at most a duplicate start that GCE
    absorbs. Honouring a value nobody can read costs every visitor a Start
    button that does nothing — the one outcome this whole page exists to avoid.

    Unusable means: absent, empty, non-numeric, non-finite (`inf`/`nan` both
    parse as floats and would otherwise wedge the comparison), or stamped in the
    future. The first version of this clamped a future timestamp to `TTL`, which
    reads like a bound but is not one: `9999999999` returns `TTL` on *every*
    call and holds the lock until that date arrives (red team 2026-07-29 P1 —
    the implementer's own test asserted the bug as if it were the fix).
    """
    try:
        taken = float(label_value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(taken) or taken > now + START_LOCK_MAX_SKEW_S:
        return 0.0
    return max(0.0, START_LOCK_TTL_S - (now - taken))


def plan_start_lock(labels: dict[str, str], now: float) -> dict[str, str] | None:
    """The label set to write to take the lock, or None if someone else holds it.

    Pure so the whole decision is testable: `main.py` only performs the
    fingerprint-conditional write and reports whether it won.
    """
    if start_lock_seconds_left(labels.get(START_LOCK_LABEL), now) > 0:
        return None
    # Label values accept [a-z0-9_-]{0,63}; a decimal epoch qualifies. Rounded
    # up, so the lock covers at least the TTL rather than up to a second less.
    return {**labels, START_LOCK_LABEL: str(math.ceil(now))}


def release_start_lock(labels: dict[str, str]) -> dict[str, str]:
    """The label set with the lock dropped — for the path where the winner's
    `instances.start` then failed. Leaving the lock to expire would answer the
    next visitor with `starting` for two minutes while nothing is starting, and
    a zone stockout (observed here on 2026-07-29) is exactly when someone
    retries (red team 2026-07-29 P2)."""
    return {key: value for key, value in labels.items() if key != START_LOCK_LABEL}


def page_state(instance_status: str | None, app_ready: bool) -> str:
    """Map (GCE status, app self-check) to the visitor-facing state."""
    if instance_status == "RUNNING":
        return "running" if app_ready else "starting"
    if instance_status in _STARTING:
        return "starting"
    if instance_status in _CLOSING:
        return "closing"
    return "closed"
