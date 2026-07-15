"""Retrieval entry points (Day 3, docs/specs/day3.md).

Builds an in-process BM25 index over a package's chunks and runs the golden-set
evaluation comparing chunking strategies. No index persistence — the corpus is
tiny (spec Out of Scope).
"""

from __future__ import annotations

from pathlib import Path

from learnarken.chunking import chunk_package
from learnarken.chunking.base import Chunk, applies_to
from learnarken.retrieval.bm25 import BM25Index, ScoredChunk, tokenize
from learnarken.retrieval.evaluate import (
    GoldenQuery,
    evaluate_strategy,
    load_golden,
    resolve_anchor_texts,
)

__all__ = [
    "BM25Index",
    "ScoredChunk",
    "tokenize",
    "search_package",
    "run_eval",
]


def search_package(
    package_dir: str | Path,
    query: str,
    strategy: str = "structure",
    k: int = 10,
    context: dict[str, str] | None = None,
) -> list[ScoredChunk]:
    """Chunk, optionally 排除场合-filter, index, and search — one call, no state."""
    chunks = chunk_package(package_dir, strategy=strategy)
    if context:
        chunks = [c for c in chunks if applies_to(c, context)]
    return BM25Index(chunks).search(query, k=k)


def run_eval(
    package_dirs: list[str | Path],
    golden_path: str | Path,
    ks: tuple[int, ...] = (5, 10),
    strategies: tuple[str, ...] = ("structure", "recursive"),
) -> dict:
    """Run each strategy over the golden set; returns metrics keyed by strategy."""
    golden: list[GoldenQuery] = load_golden(golden_path)
    anchors = {a for q in golden for a in q.relevant}
    anchor_texts = resolve_anchor_texts(package_dirs, anchors)

    results: dict[str, dict] = {}
    for strategy in strategies:
        chunks: list[Chunk] = []
        for pkg in package_dirs:
            chunks.extend(chunk_package(pkg, strategy=strategy))
        index = BM25Index(chunks)
        results[strategy] = evaluate_strategy(chunks, index.search, golden, anchor_texts, ks=ks)
    return {
        "golden": str(golden_path),
        "n_queries": len(golden),
        "packages": [str(p) for p in package_dirs],
        "results": results,
    }
