"""Retrieval entry points (Day 3, docs/specs/day3.md).

Builds an in-process BM25 index over a package's chunks and runs the golden-set
evaluation comparing chunking strategies. No index persistence — the corpus is
tiny (spec Out of Scope).
"""

from __future__ import annotations

from pathlib import Path

from learnarken.chunking import chunk_package
from learnarken.chunking.base import Chunk, applies_to
from learnarken.loader import MAX_FILE_BYTES
from learnarken.package import NotAPackageError
from learnarken.retrieval.bm25 import BM25Index, ScoredChunk, tokenize
from learnarken.retrieval.evaluate import (
    GoldenQuery,
    evaluate_strategy,
    load_golden,
    resolve_anchors,
    unresolved_anchors,
)

__all__ = [
    "BM25Index",
    "ScoredChunk",
    "tokenize",
    "search_package",
    "run_eval",
]


def _dedupe_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Drop byte-identical duplicates (same chunk_id) and refuse conflicting ones.

    Passing the same package twice would otherwise index a chunk twice and let a
    single relevant chunk be counted repeatedly in a ranked list, pushing
    recall/nDCG above 1.0 (red-team R3). Identical chunk_ids are the same
    document → deduplicated; the same (dmc, source_path) with a *different*
    chunk_id means conflicting content across packages → refused.
    """
    by_id: dict[str, Chunk] = {}
    by_anchor: dict[tuple[str, str], str] = {}
    for c in chunks:
        anchor = (c.dmc, c.source_path)
        if anchor in by_anchor and by_anchor[anchor] != c.chunk_id:
            raise ValueError(
                f"conflicting chunk content across packages for {c.dmc} {c.source_path} "
                "— evaluate these packages separately"
            )
        by_anchor[anchor] = c.chunk_id
        by_id.setdefault(c.chunk_id, c)
    return list(by_id.values())


def search_package(
    package_dir: str | Path,
    query: str,
    strategy: str = "structure",
    k: int = 10,
    context: dict[str, str] | None = None,
    skip_bad: bool = False,
) -> list[ScoredChunk]:
    """Chunk, optionally 排除场合-filter, index, and search — one call, no state."""
    chunks = chunk_package(package_dir, strategy=strategy, skip_bad=skip_bad)
    if context:
        chunks = [c for c in chunks if applies_to(c, context)]
    return BM25Index(chunks).search(query, k=k)


def run_eval(
    package_dirs: list[str | Path],
    golden_path: str | Path,
    ks: tuple[int, ...] = (5, 10),
    strategies: tuple[str, ...] = ("structure", "recursive"),
    skip_bad: bool = False,
) -> dict:
    """Run each strategy over the golden set; returns metrics keyed by strategy.

    Fails closed if any answerable golden anchor does not resolve to an element
    in the corpus (golden ↔ corpus drift would otherwise silently shrink the
    evaluated set and flatter the scores — red-team #3).
    """
    golden: list[GoldenQuery] = load_golden(golden_path)
    # Validate package dirs up front so a bad --package reports "not a package"
    # rather than being misdiagnosed as golden/corpus drift (red-team R4).
    for pkg in package_dirs:
        pkg_path = Path(pkg)
        if not pkg_path.is_dir():
            raise NotAPackageError(f"not a directory: {pkg}")
        dm_files = sorted(pkg_path.glob("DMC-*.xml"))
        if not dm_files:
            raise NotAPackageError(f"no data modules (DMC-*.xml) in: {pkg}")
        # Refuse oversized files before anchor resolution reads any bytes (R4).
        oversized = [p.name for p in dm_files if p.stat().st_size > MAX_FILE_BYTES]
        if oversized:
            raise ValueError(f"data module(s) exceed the {MAX_FILE_BYTES}-byte cap: {oversized}")
    anchors = {a for q in golden for a in q.relevant}
    resolved = resolve_anchors(package_dirs, anchors)
    missing = unresolved_anchors(anchors, resolved)
    if missing:
        listing = "; ".join(f"{dmc} {xpath}" for dmc, xpath in sorted(missing))
        raise ValueError(
            f"{len(missing)} golden anchor(s) do not resolve in the given packages "
            f"(check --package and the golden set): {listing}"
        )

    results: dict[str, dict] = {}
    for strategy in strategies:
        raw: list[Chunk] = []
        for pkg in package_dirs:
            raw.extend(chunk_package(pkg, strategy=strategy, skip_bad=skip_bad))
        chunks = _dedupe_chunks(raw)
        index = BM25Index(chunks)
        results[strategy] = evaluate_strategy(chunks, index.search, golden, resolved, ks=ks)
    return {
        "golden": str(golden_path),
        "n_queries": len(golden),
        "packages": [str(p) for p in package_dirs],
        "results": results,
    }
