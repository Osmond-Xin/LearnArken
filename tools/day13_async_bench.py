"""asyncio orchestration benchmark (Day 13, Decision 7).

Compares a **sync baseline** against **asyncio orchestration** for the I/O-bound
fan-out this project actually has: evaluating the ToT repair candidates (each a
blocking LLM + sandbox job). Reports wall time, task count, concurrency limit, and
success/timeout/error counts (Decision 7c/7d). If there is no clear benefit the
tool records why (too few tasks / CPU-bound / rate limit) — a flat result is valid.

Two modes:
- `--simulate SECONDS` (default 0.3): deterministic sleep jobs that stand in for
  I/O latency, isolating the orchestration overhead reproducibly (no live LLM). The
  headline mechanic — overlapping N waits under a Semaphore — is exact here.
- `--live [--findings N]`: the real ToT candidate jobs on package-b (subscription-
  bounded LLM, noisier wall-clock; not run in CI).

    uv run python tools/day13_async_bench.py [--simulate 0.3] [--limit 6]
    uv run python tools/day13_async_bench.py --live --findings 2

Output is frozen at eval/results/day13-async.json.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from learnarken.perf.orchestrate import run_bounded_sync

_OUT = Path("eval/results/day13-async.json")


def _simulate_jobs(count: int, seconds: float):
    def make(i: int):
        def _job() -> int:
            time.sleep(seconds)
            return i

        return _job

    return [make(i) for i in range(count)]


def _live_jobs(package: str, n_findings: int):
    from learnarken.repair.tot import build_candidate_jobs
    from learnarken.validation import analyze_package

    report, _ = analyze_package(package)
    jobs = []
    for finding in report.findings[:n_findings]:
        jobs.extend(build_candidate_jobs(finding, package))
    return jobs


def _time_sync(jobs) -> tuple[float, list]:
    start = time.perf_counter()
    results = [job() for job in jobs]
    return time.perf_counter() - start, results


def _bench(jobs, limit: int, timeout: float) -> dict:
    sync_wall, _ = _time_sync(jobs)

    start = time.perf_counter()
    outcomes = run_bounded_sync(jobs, limit=limit, timeout=timeout)
    async_wall = time.perf_counter() - start

    status_counts = {"success": 0, "timeout": 0, "error": 0}
    for outcome in outcomes:
        status_counts[outcome.status] += 1

    speedup = sync_wall / async_wall if async_wall else 0.0
    return {
        "task_count": len(jobs),
        "concurrency_limit": limit,
        "task_timeout_s": timeout,
        "sync_wall_s": round(sync_wall, 4),
        "async_wall_s": round(async_wall, 4),
        "speedup": round(speedup, 3),
        "outcomes": status_counts,
    }


def _verdict(bench: dict, mode: str) -> str:
    if bench["speedup"] >= 1.3:
        return (
            f"asyncio overlapped the I/O waits: {bench['speedup']:.2f}x "
            f"({bench['sync_wall_s']}s → {bench['async_wall_s']}s) at limit "
            f"{bench['concurrency_limit']} over {bench['task_count']} tasks. This is the "
            "win of an event loop for waiting-type work (no data race, single thread)."
        )
    return (
        f"No clear benefit ({bench['speedup']:.2f}x). Likely: too few tasks "
        f"({bench['task_count']}) to amortize orchestration, or the jobs are not "
        "wait-dominated (CPU/rate-limited). Honest flat result (Decision 7c)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulate", type=float, default=0.3, help="sleep seconds/job")
    parser.add_argument("--limit", type=int, default=6, help="number of simulated jobs")
    parser.add_argument("--concurrency", type=int, default=3, help="Semaphore limit")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--live", action="store_true", help="use real ToT candidate jobs")
    parser.add_argument("--findings", type=int, default=2)
    parser.add_argument("--package", default="samples/package-b")
    args = parser.parse_args()

    if args.live:
        jobs = _live_jobs(args.package, args.findings)
        mode = f"live — {args.findings} package-b findings x 3 candidates"
    else:
        jobs = _simulate_jobs(args.limit, args.simulate)
        mode = f"simulate — {args.limit} jobs x {args.simulate}s I/O latency"

    bench = _bench(jobs, args.concurrency, args.timeout)
    result = {
        "experiment": "asyncio orchestration vs sync — I/O-bound ToT candidate fan-out "
        "(Day 13, Decision 7)",
        "mode": mode,
        "division_of_labor": "asyncio orchestrates I/O waits only; blocking jobs run in "
        "worker threads (asyncio.to_thread). CPU-bound work stays on multiprocessing "
        "(perf.shard). No async def wraps a CPU hotspot (Decision 7a/7e).",
        "contract": "Semaphore-bounded, per-task timeout, non fail-fast; each task "
        "recorded as success/timeout/error (Decision 7d).",
        **bench,
        "verdict": _verdict(bench, mode),
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {_OUT}")
    print(f"  {result['verdict']}")


if __name__ == "__main__":
    main()
