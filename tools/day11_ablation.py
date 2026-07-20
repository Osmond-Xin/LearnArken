"""Day 11 Ablation Runner.

Runs the ablation for both the old golden set (day4) and the new multi-hop set (day11),
using the 6 modes (bm25, dense, hybrid, hybrid-rerank, hybrid-graph, hybrid-graph-rerank),
and compiles them into eval/results/day11-ablation.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from learnarken import graph  # noqa: E402
from learnarken.retrieval import (  # noqa: E402
    MANIFEST_PATH,
    run_ablation,
)

PACKAGES = [REPO_ROOT / "samples" / "package-a", REPO_ROOT / "samples" / "package-c"]
OUT = REPO_ROOT / "eval" / "results" / "day11-ablation.json"
MODES = ("bm25", "dense", "hybrid", "hybrid-rerank", "hybrid-graph", "hybrid-graph-rerank")


def main() -> int:
    if not graph.is_up():
        raise SystemExit("Neo4j is unreachable — refusing to run graph modes (fail closed)")
    manifest_graph = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("graph")
    if manifest_graph is not None and manifest_graph != graph.stats():
        raise SystemExit(
            f"graph state {graph.stats()} does not match the manifest's recorded "
            f"sync {manifest_graph} — stale graph relative to the last index run"
        )

    print("Running ablation on old golden set (day4.jsonl)...")
    # Load categories for day4
    categories_day4 = {}
    day4_path = REPO_ROOT / "eval" / "golden" / "day4.jsonl"
    for line in day4_path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.strip().startswith("#"):
            row = json.loads(line)
            if "category" in row:
                categories_day4[row["query_id"]] = row["category"]

    report_day4 = run_ablation(
        PACKAGES,
        day4_path,
        modes=MODES,
        ks=(5, 10),
        strategy="structure",
        categories=categories_day4 or None,
    )
    report_day4["seed"] = 42

    print("Running ablation on new multi-hop set (day11-multihop.jsonl)...")
    # Load categories for day11
    categories_day11 = {}
    day11_path = REPO_ROOT / "eval" / "golden" / "day11-multihop.jsonl"
    for line in day11_path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.strip().startswith("#"):
            row = json.loads(line)
            if "category" in row:
                categories_day11[row["query_id"]] = row["category"]

    report_day11 = run_ablation(
        PACKAGES,
        day11_path,
        modes=MODES,
        ks=(5, 10),
        strategy="structure",
        categories=categories_day11 or None,
    )
    report_day11["seed"] = 42

    output = {
        "note": (
            "Day 11 ablation (spec day11 Key Decision 4): hybrid vs hybrid+graph, old "
            "and new sets reported separately. Deterministic (retrieval only, no "
            "sampling); metrics verified identical across two runs (including "
            "before/after the corpus-authoritative graph-sync fix, red-team day11 #1). "
            "p50 rows share the day4 artifact convention (bm25/dense modes run first "
            "and absorb MLX warm-up)."
        ),
        "seed": 42,
        "old_set": report_day4,
        "multihop_set": report_day11,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=1) + "\n", encoding="utf-8")
    print(f"Successfully generated {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
