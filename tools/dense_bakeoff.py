"""Day 4a dense bake-off: BGE-M3 vs Qwen3-Embedding-8B (+ historical MiniMax).

HISTORY: the original three-way run included MiniMax embo-01 (R@5 0.500 —
the measured length bias). The Day 4 adjudication removed the MiniMax client
from the architecture; to reproduce that historical row, run this script at
commit `b414fa4`. Current runs cover the two local providers.

The winner becomes DEFAULT_PROVIDER (Yi Xin, 2026-07-16 — "用数字开门").
Every provider is consumed through the same LangChain `Embeddings` interface,
ranked by exact cosine in Python (no ANN, no engine — pure model comparison),
and scored by the Day 3 evaluation harness against the golden set.

    uv run python tools/dense_bakeoff.py [--golden eval/golden/day4.jsonl]

Writes eval/results/day4-bakeoff.json (the artifact the README/notes tables
are generated from — red-team day4 #16) and docs/notes/day4-dense-bakeoff.md.
Deterministic given the pinned model revisions (INV-5): no sampling anywhere.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import NamedTuple

from learnarken.chunking import chunk_package
from learnarken.embedding.providers import get_embeddings
from learnarken.retrieval.evaluate import (
    evaluate_strategy,
    load_golden,
    resolve_anchors,
    unresolved_anchors,
)

PACKAGES = ("samples/package-a", "samples/package-c")
PROVIDERS = ("bge-m3", "qwen3-8b")
OUT = Path("docs/notes/day4-dense-bakeoff.md")
ARTIFACT = Path("eval/results/day4-bakeoff.json")


class _Scored(NamedTuple):
    chunk: object
    score: float


def cosine(a: list[float], b: list[float]) -> float:
    # Providers are configured to L2-normalize, so the dot product is the cosine.
    return sum(x * y for x, y in zip(a, b, strict=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default="eval/golden/day4.jsonl")
    parser.add_argument("--providers", nargs="*", default=list(PROVIDERS))
    args = parser.parse_args()

    golden = load_golden(args.golden)
    rows = [json.loads(line) for line in Path(args.golden).read_text().splitlines() if line.strip()]
    category = {r["query_id"]: r.get("category", "?") for r in rows}
    reviewed = {r["query_id"] for r in rows if r.get("relevance_reviewed")}

    chunks = [c for pkg in PACKAGES for c in chunk_package(pkg, "structure")]
    anchors = {a for q in golden for a in q.relevant}
    resolved = resolve_anchors(list(PACKAGES), anchors)
    missing = unresolved_anchors(anchors, resolved)
    if missing:
        print(f"WARNING: {len(missing)} unresolved anchors: {sorted(missing)[:4]} ...")

    print(f"{len(golden)} queries ({len(reviewed)} human-reviewed) · {len(chunks)} chunks\n")
    results: dict[str, dict] = {}

    for name in args.providers:
        print(f"=== {name}")
        emb = get_embeddings(name)
        t0 = time.perf_counter()
        doc_vectors = emb.embed_documents([c.text for c in chunks])
        t_docs = time.perf_counter() - t0
        t0 = time.perf_counter()
        query_vectors = {q.query_id: emb.embed_query(q.query) for q in golden}
        t_queries = time.perf_counter() - t0

        def search(query_text: str, k: int, _qv=query_vectors, _dv=doc_vectors, _g=golden):
            qv = next(_qv[q.query_id] for q in _g if q.query == query_text)
            ranked = sorted(zip(chunks, _dv, strict=True), key=lambda cv: -cosine(qv, cv[1]))[:k]
            return [_Scored(c, cosine(qv, v)) for c, v in ranked]

        overall = evaluate_strategy(chunks, search, golden, resolved)
        by_cat = {}
        for cat in sorted({category[q.query_id] for q in golden}):
            subset = [q for q in golden if category[q.query_id] == cat]
            by_cat[cat] = evaluate_strategy(chunks, search, subset, resolved)
        results[name] = {
            "overall": overall,
            "by_category": by_cat,
            "sec_embed_docs": round(t_docs, 1),
            "sec_embed_queries": round(t_queries, 1),
        }
        print(f"    overall: {overall}")

    from learnarken.embedding.providers import pinned_revisions

    ARTIFACT.write_text(
        json.dumps(
            {
                "golden": args.golden,
                "n_queries": len(golden),
                "n_reviewed": len(reviewed),
                "n_chunks": len(chunks),
                "model_revisions": pinned_revisions(),
                "results": results,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    _write_report(results, len(golden), len(reviewed), len(chunks))
    print(f"\nartifact -> {ARTIFACT}\nreport -> {OUT}")
    return 0


def _write_report(results: dict, n_all: int, n_human: int, n_chunks: int) -> None:
    n_answerable = next(iter(results.values()))["overall"]["n_evaluated"]
    lines = [
        "# Day 4a dense bake-off — BGE-M3 / Qwen3-Embedding-8B (MiniMax row: historical)",
        "",
        "> **AI-generated** (Claude, implementer), 2026-07-16, per Yi Xin's",
        "> direction: three dense rows, the winner becomes the default provider.",
        "> Harness: exact cosine in Python over structure chunks of package-a+c",
        f"> ({n_chunks} chunks); scored by the Day 3 evaluation code against",
        f"> eval/golden/day4.jsonl ({n_all} queries, {n_human} human-reviewed;",
        f"> ranking metrics over the answerable n={n_answerable}). Tables are",
        "> generated by this script from eval/results/day4-bakeoff.json —",
        "> do not hand-edit (red-team day4 #16). Reproduce:",
        "> `uv run python tools/dense_bakeoff.py`",
        "",
        "## Overall",
        "",
        "| Provider | R@5 | R@10 | MRR | nDCG@10 | embed docs (s) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, r in results.items():
        o = r["overall"]
        lines.append(
            f"| {name} | {o['recall@5']} | {o['recall@10']} | {o['mrr']} | {o['ndcg@10']} "
            f"| {r['sec_embed_docs']} |"
        )
    lines += ["", "## Per category (Recall@5, answerable queries)", ""]
    categories = sorted(next(iter(results.values()))["by_category"])
    cat_n = {
        c: next(iter(results.values()))["by_category"][c]["n_evaluated"] for c in categories
    }
    lines.append("| Provider | " + " | ".join(f"{c} (n={cat_n[c]})" for c in categories) + " |")
    lines.append("| --- |" + " --- |" * len(categories))
    for name, r in results.items():
        cells = [str(r["by_category"][c]["recall@5"]) for c in categories]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Notes: dense retrieval always returns k hits, so `zero_hit_rate` is 0",
        "for every provider by construction — refusal is Day 5's job, and the",
        "no_answer / identifier_perturbation categories are scored on that",
        "basis (they read 0 here; the BM25 row is where refusal-by-absence",
        "shows). Latency is embed time on this machine (M5 Max), not a serving",
        "claim (INV-7).",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
