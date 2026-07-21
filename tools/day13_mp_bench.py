"""multiprocessing scaling benchmark for package validation (Day 13, Decision 1).

Measures whether per-DM-file multiprocessing sharding gives a **real** speedup on
validation, and reports it honestly (INV-5): wall time as a **distribution** over
repeats (not a single point), worker count, speedup, and the parallel efficiency
gap that the Amdahl serial fraction (L3 cross-file resolution) + pool overhead
open up. Every sharded run is asserted **byte-equivalent to the single-process
baseline** (Decision 1b) — the benchmark fails loudly if parallel findings differ.

The corpus is toy-scale (single-digit-to-~10 DM files per package): the honest,
expected result is that a too-small corpus does **not** speed up — pool spawn and
pickle overhead dominate work this small (Decision 1c). A flat or negative curve
is a *valid, reported* outcome, not a failure to hide.

    uv run python tools/day13_mp_bench.py [--packages samples/package-a ...]
                                          [--repeats 5] [--workers 1 2 4 8]

Output is frozen at eval/results/day13-mp-scaling.json.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import statistics
import time
from pathlib import Path

from learnarken.validation.engine import analyze_package, list_package_files
from learnarken.validation.parallel import analyze_package_sharded

_OUT = Path("eval/results/day13-mp-scaling.json")


def _timed(fn, repeats: int) -> dict[str, float]:
    """Run `fn` `repeats` times, return the wall-time distribution (seconds)."""
    samples: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return {
        "median": statistics.median(samples),
        "min": min(samples),
        "max": max(samples),
        "samples": [round(s, 6) for s in samples],
    }


def _verdict(scaling: list[dict]) -> str:
    best = max(scaling, key=lambda row: row["speedup"])
    if best["speedup"] < 1.05:
        return (
            f"No speedup: best was {best['speedup']:.2f}x at {best['workers']} workers. "
            "Corpus too small — pool spawn + pickle overhead dominate work this cheap "
            "(expected, Decision 1c)."
        )
    return (
        f"Best {best['speedup']:.2f}x at {best['workers']} workers "
        f"(efficiency {best['efficiency']:.2f}); knee where added workers stop paying "
        "is set by the L3 serial fraction + per-shard pickle/spawn overhead."
    )


def _bench_package(package: str, workers: list[int], repeats: int) -> dict:
    directory = Path(package)
    files = list_package_files(directory)
    serial_report, _ = analyze_package(directory)

    baseline = _timed(lambda: analyze_package(directory), repeats)
    serial_median = baseline["median"]

    scaling: list[dict] = []
    for w in workers:
        report, _ = analyze_package_sharded(directory, workers=w)
        equivalent = report.model_dump() == serial_report.model_dump()
        if not equivalent:
            raise AssertionError(
                f"{package} workers={w}: sharded findings differ from serial baseline "
                "(Decision 1b violated)"
            )
        wall = _timed(lambda w=w: analyze_package_sharded(directory, workers=w), repeats)
        effective_shards = min(w, len(files))
        speedup = serial_median / wall["median"] if wall["median"] else 0.0
        ideal = float(effective_shards)
        scaling.append(
            {
                "workers": w,
                "effective_shards": effective_shards,
                "wall_s": wall,
                "speedup": round(speedup, 3),
                "ideal_speedup": ideal,
                "efficiency": round(speedup / ideal, 3) if ideal else 0.0,
                "equivalent_to_baseline": equivalent,
            }
        )

    return {
        "files": len(files),
        "findings": len(serial_report.findings),
        "serial_baseline_s": baseline,
        "scaling": scaling,
        "serial_fraction": "L3 cross-file resolution (_resolve_dm_identities + "
        "_crossfile_findings) needs the whole package and runs in the serial merge — "
        "the concrete Amdahl serial fraction.",
        "verdict": _verdict(scaling),
        "caveat": f"Toy scale: {len(files)} DM files. A too-small corpus may not speed "
        "up (Decision 1c); results do not extrapolate to a large ingestion corpus.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--packages",
        nargs="+",
        default=["samples/package-a", "samples/package-b", "samples/package-c"],
    )
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 2, 4, 8])
    args = parser.parse_args()

    results = {
        "experiment": "mp-scaling — per-DM-file validation sharding (Day 13, Decision 1)",
        "platform": {
            "start_method": mp.get_start_method(),
            "cpu_count": os.cpu_count(),
            "note": "macOS default start method is 'spawn' (re-imports per worker, "
            "costlier than fork); a Docker CPU quota can make cpu_count() overstate "
            "usable cores (scan A2).",
        },
        "repeats": args.repeats,
        "packages": {p: _bench_package(p, args.workers, args.repeats) for p in args.packages},
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2) + "\n")
    print(f"wrote {_OUT}")
    for pkg, data in results["packages"].items():
        print(f"  {pkg} ({data['files']} files): {data['verdict']}")


if __name__ == "__main__":
    main()
