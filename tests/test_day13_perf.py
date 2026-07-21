"""Day 13 performance experiments — mp sharding + asyncio orchestration (hermetic).

No live services. The mp equivalence test is the load-bearing one (Decision 1b):
sharded validation must be byte-identical to the single-process baseline. The
orchestration tests assert the Decision 7d contract: Semaphore-bounded, per-task
timeout, non fail-fast (one task's failure/timeout never sinks the others).
"""

from __future__ import annotations

import threading
import time

import pytest

from learnarken.perf.orchestrate import run_bounded_sync
from learnarken.perf.shard import make_shards, run_sharded
from learnarken.validation.engine import analyze_package
from learnarken.validation.parallel import analyze_package_sharded

# --- generic shard runner -------------------------------------------------


def test_make_shards_splits_evenly_and_preserves_order():
    assert make_shards([1, 2, 3, 4, 5], 2) == [[1, 2, 3], [4, 5]]
    assert make_shards([1, 2, 3], 3) == [[1], [2], [3]]
    # fewer items than workers → fewer shards (small corpus can't use all workers)
    assert make_shards([1, 2], 8) == [[1], [2]]
    assert make_shards([], 4) == []


def test_make_shards_rejects_zero_workers():
    with pytest.raises(ValueError, match="n must be >= 1"):
        make_shards([1, 2], 0)


def _square_shard(items):
    return [x * x for x in items]


def test_run_sharded_inprocess_flattens_in_order():
    # workers<=1 runs in-process (no pickling), preserving shard order.
    out = run_sharded([[1, 2], [3, 4]], _square_shard, workers=1)
    assert out == [1, 4, 9, 16]


# --- mp validation equivalence (Decision 1b) — the load-bearing test ------


@pytest.mark.parametrize("package", ["samples/package-a", "samples/package-b"])
@pytest.mark.parametrize("workers", [1, 2, 4])
def test_sharded_validation_equals_serial_baseline(package, workers):
    serial, _ = analyze_package(package)
    sharded, _ = analyze_package_sharded(package, workers=workers)
    # Byte-equivalent findings (Decision 1b) — the whole point of the abstraction.
    assert sharded.model_dump() == serial.model_dump()


# --- fail-closed BREX rule execution (red-team #4) ------------------------


def test_brex_rule_exception_fails_closed_not_crash(monkeypatch):
    """A rule that raises must become a BREX-999 finding, not crash the package
    (INV-4). This is what makes running _process_file on a byte-identical dup
    safe, closing the sharded-vs-serial equivalence gap without a pre-dedup pass."""
    from learnarken.validation import engine
    from learnarken.validation.report import Severity

    class _BoomRule:
        rule_id = "BREX-BOOM"
        severity = Severity.ERROR
        fix_hint = ""

        def check(self, root, dm, path):
            raise RuntimeError("rule bug")

    monkeypatch.setattr(engine, "BREX_RULES", [_BoomRule()])
    report, _ = engine.analyze_package("samples/package-a")  # valid DMs reach L2
    boom = [f for f in report.findings if f.rule_id == "BREX-999"]
    assert boom and "BREX-BOOM raised" in boom[0].message


# --- asyncio orchestration contract (Decision 7d) -------------------------


def test_run_bounded_all_success_in_order():
    jobs = [(lambda i=i: i * 10) for i in range(5)]
    outcomes = run_bounded_sync(jobs, limit=3, timeout=5.0)
    assert [o.index for o in outcomes] == [0, 1, 2, 3, 4]
    assert all(o.status == "success" for o in outcomes)
    assert [o.value for o in outcomes] == [0, 10, 20, 30, 40]


def test_run_bounded_timeout_does_not_cancel_siblings():
    def slow() -> str:
        time.sleep(2.0)
        return "slow"

    jobs = [lambda: "fast-a", slow, lambda: "fast-b"]
    outcomes = run_bounded_sync(jobs, limit=3, timeout=0.3)
    assert outcomes[0].status == "success" and outcomes[0].value == "fast-a"
    assert outcomes[1].status == "timeout"  # the slow one times out
    assert outcomes[2].status == "success" and outcomes[2].value == "fast-b"  # sibling survives


def test_run_bounded_error_is_captured_not_raised():
    def boom() -> str:
        raise RuntimeError("kaboom")

    jobs = [lambda: "ok", boom]
    outcomes = run_bounded_sync(jobs, limit=2, timeout=5.0)
    assert outcomes[0].status == "success"
    assert outcomes[1].status == "error"
    assert "kaboom" in outcomes[1].error


def test_run_bounded_rejects_nonpositive_timeout():
    with pytest.raises(ValueError, match="timeout must be a positive"):
        run_bounded_sync([lambda: 1], limit=1, timeout=0)


def test_run_bounded_sync_refuses_inside_running_loop():
    """Called from async code, it raises a clear config error instead of the
    confusing asyncio.run 'already running loop' (red-team P2)."""
    import asyncio

    async def inner():
        with pytest.raises(RuntimeError, match="cannot run inside an existing event loop"):
            run_bounded_sync([lambda: 1], limit=1, timeout=1.0)

    asyncio.run(inner())


def test_run_bounded_respects_concurrency_limit():
    lock = threading.Lock()
    state = {"current": 0, "max": 0}

    def worker() -> int:
        with lock:
            state["current"] += 1
            state["max"] = max(state["max"], state["current"])
        time.sleep(0.1)
        with lock:
            state["current"] -= 1
        return 1

    jobs = [worker for _ in range(6)]
    run_bounded_sync(jobs, limit=2, timeout=5.0)
    assert state["max"] <= 2  # the Semaphore held the line
