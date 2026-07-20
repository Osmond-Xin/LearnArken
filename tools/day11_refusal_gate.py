"""Day 11 T3 refusal-regression gate (spec acceptance 4).

The graph route pulls structurally-related "high-quality noise" — the risk is
that no-answer traps stop refusing because a linked entity's neighborhood
scores above the threshold gate (tutorial 14 failure mode 5, scan T3). This
measures the *deterministic* refusal layer (Day 5 threshold gate: reranker
top-1 score < measured threshold ⇒ refuse; no LLM involved) over every
no-answer trap in the old and new golden sets, under `hybrid` vs
`hybrid-graph` candidates.

Pass criterion (per-query, not just aggregate — red-team day11 #4): every
trap that `hybrid` refuses must still be refused under `hybrid-graph`; an
aggregate-rate comparison alone could hide one trap flipping to "answer"
offset by another flipping to "refuse". The aggregate rate is still reported
for context.

Fails closed like `run_ablation` (red-team day11 #3): if Neo4j is down this
script refuses to run rather than silently measuring `hybrid` against an
empty graph arm and calling the result "hybrid-graph".

Writes eval/results/day11-refusal-gate.json (INV-5 frozen artifact).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from learnarken import graph  # noqa: E402
from learnarken.answer.engine import load_threshold  # noqa: E402
from learnarken.chunking import chunk_package  # noqa: E402
from learnarken.retrieval import (  # noqa: E402
    MANIFEST_PATH,
    _dedupe_chunks,
    _mode_retriever,
    verify_corpus,
)
from learnarken.retrieval.evaluate import load_golden  # noqa: E402
from learnarken.retrieval.hybrid import CANDIDATE_K, rerank_scored  # noqa: E402

PACKAGES = [REPO_ROOT / "samples" / "package-a", REPO_ROOT / "samples" / "package-c"]
GOLDEN_SETS = {
    "day4": REPO_ROOT / "eval" / "golden" / "day4.jsonl",
    "day11-multihop": REPO_ROOT / "eval" / "golden" / "day11-multihop.jsonl",
}
OUT = REPO_ROOT / "eval" / "results" / "day11-refusal-gate.json"


def main() -> int:
    # Neo4j checked first — it is this script's mode-specific precondition and
    # a cheap network ping, checked before the costlier Vespa manifest/engine
    # verification (also makes the fail-closed path hermetically testable
    # without live Vespa — red-team day11 #11 residual gap).
    if not graph.is_up():
        raise SystemExit(
            "Neo4j is unreachable — refusing to measure 'hybrid-graph' against an "
            "empty graph arm and report it as the graph mode (fail closed, mirrors "
            "run_ablation's GRAPH_MODES check)"
        )
    manifest_graph = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("graph")
    if manifest_graph is not None and manifest_graph != graph.stats():
        raise SystemExit(
            f"graph state {graph.stats()} does not match the manifest's recorded "
            f"sync {manifest_graph} — stale graph relative to the last "
            "`learnarken index` run (fail closed, mirrors run_ablation)"
        )
    chunks = _dedupe_chunks(
        [c for pkg in PACKAGES for c in chunk_package(pkg, strategy="structure")]
    )
    verify_corpus(chunks, "structure")  # same fail-closed gate as the ablation
    threshold = load_threshold()

    traps = [
        (name, q) for name, path in GOLDEN_SETS.items() for q in load_golden(path) if not q.relevant
    ]
    report: dict = {"threshold": threshold, "n_traps": len(traps), "modes": {}, "per_query": []}
    rows: dict[str, dict[str, bool]] = {}
    for mode in ("hybrid", "hybrid-graph"):
        retriever = _mode_retriever(mode, chunks, k=CANDIDATE_K, strategy="structure")
        refused = 0
        for name, q in traps:
            ranked = rerank_scored(q.query, retriever.invoke(q.query), k=1)
            top1 = ranked[0][1] if ranked else 0.0
            decision = top1 < threshold
            refused += decision
            rows.setdefault(q.query_id, {"set": name})[mode] = decision
            rows[q.query_id][f"{mode}_top1"] = round(top1, 4)
        report["modes"][mode] = {
            "refused": refused,
            "refusal_rate": round(refused / len(traps), 4),
        }
    report["per_query"] = [{"query_id": k, **v} for k, v in sorted(rows.items())]
    # Per-query non-regression is the real gate (red-team day11 #4): a trap
    # that hybrid correctly refuses must not start answering under
    # hybrid-graph. The aggregate rate comparison is kept only as a summary,
    # not the pass/fail criterion.
    regressions = sorted(
        query_id for query_id, row in rows.items() if row["hybrid"] and not row["hybrid-graph"]
    )
    report["regressions"] = regressions
    report["pass"] = not regressions
    OUT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(
        f"traps={len(traps)} threshold={threshold} "
        f"hybrid={report['modes']['hybrid']['refusal_rate']} "
        f"hybrid-graph={report['modes']['hybrid-graph']['refusal_rate']} "
        f"regressions={regressions} pass={report['pass']}"
    )
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
