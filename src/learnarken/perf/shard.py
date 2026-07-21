"""Generic shard runner for CPU-bound work (Day 13, Decision 1; INV-2).

Sharding sits **behind this abstraction**: workers receive a shard *description*
(e.g. a list of file paths), read their own slice, and return **picklable**
results — no shared mutable state, no live objects crossing the process boundary
(the INV-2 form: "sharding behind an abstraction, no shared-memory shortcut").
Single-machine `ProcessPoolExecutor` today; the same interface fits a distributed
queue later, which is the whole point of INV-2.

This is the CPU-bound tool only. I/O-bound orchestration is
`learnarken.perf.orchestrate` (asyncio) — the two are never mixed (Decision 7a/7e).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor


def make_shards[T](items: Sequence[T], n: int) -> list[list[T]]:
    """Split `items` into up to `n` contiguous, near-equal shards, order
    preserved. When there are fewer items than workers, returns fewer shards
    (effective parallelism is capped by the item count — a small corpus cannot
    use all workers, Day 13 Decision 1c)."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    items = list(items)
    if not items:
        return []
    n = min(n, len(items))
    quotient, remainder = divmod(len(items), n)
    shards: list[list[T]] = []
    start = 0
    for i in range(n):
        size = quotient + (1 if i < remainder else 0)
        shards.append(items[start : start + size])
        start += size
    return shards


def run_sharded[T, R](
    shards: Sequence[Sequence[T]],
    worker_fn: Callable[[Sequence[T]], list[R]],
    *,
    workers: int,
) -> list[R]:
    """Map `worker_fn` over `shards` and flatten, **preserving shard order** so
    the merged result is deterministic. `workers <= 1` runs in-process (no pool);
    `workers > 1` uses a `ProcessPoolExecutor`. `worker_fn` must be picklable (a
    module-level function or a `functools.partial` of one) — no closures/lambdas,
    since spawn re-imports it in the child.

    Deterministic ordering is a correctness requirement, not a nicety: the caller
    (validation) folds these back in sorted-file order to stay byte-equivalent to
    the single-process baseline (Decision 1b)."""
    shard_list = [list(s) for s in shards]
    if not shard_list:
        return []
    if workers <= 1:
        results_per_shard = [worker_fn(s) for s in shard_list]
    else:
        # Cap actual processes at the useful maximum (red-team P2): never spawn
        # more workers than there are shards or CPUs — workers=10000 must not
        # become a local resource DoS.
        cpu = os.cpu_count() or 1
        pool_size = min(workers, len(shard_list), cpu)
        with ProcessPoolExecutor(max_workers=pool_size) as executor:
            results_per_shard = list(executor.map(worker_fn, shard_list))
    flat: list[R] = []
    for part in results_per_shard:
        flat.extend(part)
    return flat
