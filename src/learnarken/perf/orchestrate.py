"""asyncio orchestration for I/O-bound fan-out (Day 13, Decision 7).

The **only** asyncio in the project, and strictly an *orchestration* layer: it
schedules waiting-type work (LLM candidate calls + sandbox subprocess exec) with a
concurrency limit and per-task timeout. It never wraps a CPU hotspot — the blocking
candidate jobs run in worker threads via `asyncio.to_thread` (the `run_in_executor`
pattern, Decision 7e), and asyncio's job is purely to overlap their waits.

Contract (Decision 7d): a `Semaphore(limit)` bounds concurrency; every task has a
timeout; a single task's failure/timeout does **not** cancel its siblings (non
fail-fast) — each is captured as a `TaskOutcome{status: success|timeout|error}`.
This is the CPU/IO division of labor from Decision 7a: multiprocessing is for
CPU-bound work (`learnarken.perf.shard`); this is for I/O-bound orchestration.

**Timeout semantics — read this (red-team P1).** `asyncio.timeout` around
`asyncio.to_thread(job)` bounds *the orchestrator's wait*, not the worker thread:
a thread cannot be cancelled, so a truly hung `job` keeps running after its
`TaskOutcome(timeout)` is returned and the semaphore slot is released. The wait is
bounded and reported correctly, but the underlying work is only bounded by *its
own* hard timeout. That is why every real job here already carries one — the LLM
client has a request timeout and the sandbox subprocess has `SandboxPolicy.timeout_s`
(a SIGKILL-backed `subprocess` timeout). This orchestrator's timeout is the
*outer* bound on how long we *wait*; the *inner* hard stop belongs to the job. Do
not rely on this timeout to reclaim a runaway thread — give the job a real one.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass
class TaskOutcome[R]:
    """One orchestrated task's result. `status` is one of success/timeout/error
    (Decision 7d); `value` is set only on success."""

    index: int
    status: str  # "success" | "timeout" | "error"
    value: R | None = None
    error: str = ""
    wall_s: float = 0.0


async def _run_one[R](
    index: int,
    job: Callable[[], R],
    semaphore: asyncio.Semaphore,
    timeout: float,
) -> TaskOutcome[R]:
    async with semaphore:
        start = time.perf_counter()
        try:
            async with asyncio.timeout(timeout):
                # Blocking job (LLM call + sandbox subprocess) → a worker thread;
                # asyncio only orchestrates the wait, never runs CPU here (7e).
                value = await asyncio.to_thread(job)
        except TimeoutError:
            return TaskOutcome(index=index, status="timeout", wall_s=time.perf_counter() - start)
        except Exception as exc:  # noqa: BLE001 — a task's failure is captured, not raised
            return TaskOutcome(
                index=index,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                wall_s=time.perf_counter() - start,
            )
        return TaskOutcome(
            index=index, status="success", value=value, wall_s=time.perf_counter() - start
        )


async def run_bounded[R](
    jobs: Sequence[Callable[[], R]],
    *,
    limit: int,
    timeout: float,
) -> list[TaskOutcome[R]]:
    """Run blocking `jobs` concurrently under a `Semaphore(limit)` with a per-task
    `timeout`, returning outcomes in job order. One task's timeout/error does not
    cancel the others (non fail-fast, Decision 7d)."""
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    if not (timeout > 0):  # also rejects NaN (red-team P3)
        raise ValueError(f"timeout must be a positive number, got {timeout!r}")
    semaphore = asyncio.Semaphore(limit)
    tasks = [_run_one(i, job, semaphore, timeout) for i, job in enumerate(jobs)]
    outcomes = await asyncio.gather(*tasks)
    return sorted(outcomes, key=lambda o: o.index)


def run_bounded_sync[R](
    jobs: Sequence[Callable[[], R]],
    *,
    limit: int,
    timeout: float,
) -> list[TaskOutcome[R]]:
    """Blocking entry point (drives the event loop) for callers that are not
    themselves async — e.g. the ToT candidate runner and the async benchmark.

    Refuses to run inside an existing event loop (red-team P2): `asyncio.run`
    would raise a confusing 'cannot be called from a running event loop'. An async
    caller (FastAPI/Jupyter) must `await run_bounded(...)` directly instead."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # no running loop — safe to drive our own
    else:
        raise RuntimeError(
            "run_bounded_sync() cannot run inside an existing event loop; "
            "await run_bounded(...) directly from async code."
        )
    return asyncio.run(run_bounded(jobs, limit=limit, timeout=timeout))
