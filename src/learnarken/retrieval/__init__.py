"""Retrieval entry points (Day 3 BM25 → Day 4a modes → Day 11 graph modes).

Six modes over the same chunk set (docs/specs/day4.md, day11.md):
  bm25                in-process, offline (Day 3 path, unchanged)
  dense               Vespa nearestNeighbor via the default embedding provider
  hybrid              BM25 + dense fused by RRF (LangChain EnsembleRetriever)
  hybrid-rerank       hybrid candidates re-scored by a local cross-encoder
  hybrid-graph        BM25 + dense + graph expansion, three-way RRF (Day 11)
  hybrid-graph-rerank hybrid-graph candidates re-scored by the cross-encoder

Dense/hybrid modes need `learnarken index` to have fed Vespa with the same
package + strategy first, and fail closed (INV-4) when Vespa/embeddings are
unavailable — never a silent downgrade to bm25. Graph modes additionally need
the Neo4j graph that the same `index` run synced (spec day11 T7).
"""

from __future__ import annotations

import time
from pathlib import Path

from learnarken.chunking import chunk_package
from learnarken.chunking.base import Chunk, applies_to
from learnarken.chunking.documents import from_document
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

MODES = ("bm25", "dense", "hybrid", "hybrid-rerank", "hybrid-graph", "hybrid-graph-rerank")
GRAPH_MODES = ("hybrid-graph", "hybrid-graph-rerank")  # Day 11: need Neo4j up
# The pre-Day-11 mode set — kept as the CLI ablation default so the existing
# `learnarken eval ablation` command does not silently gain a Neo4j dependency
# (red-team day11 #9); graph modes are opt-in via --modes.
DEFAULT_ABLATION_MODES = ("bm25", "dense", "hybrid", "hybrid-rerank")

__all__ = [
    "BM25Index",
    "DEFAULT_ABLATION_MODES",
    "GRAPH_MODES",
    "MODES",
    "ScoredChunk",
    "tokenize",
    "search_package",
    "index_package",
    "run_eval",
    "run_ablation",
    "verify_corpus",
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
    mode: str = "bm25",
) -> list[ScoredChunk]:
    """Chunk, optionally 排除场合-filter, and search under the chosen mode.

    bm25 stays offline and filters *before* scoring (Day 3 semantics). The
    Vespa-backed modes retrieve first and filter after — the engine holds the
    already-fed corpus — so a filter can return fewer than k results; honest,
    not padded. Default is bm25 so the bare CLI works with no services up
    (deviation from the spec's AI-drafted `hybrid-rerank` default, noted there).
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {MODES}")
    chunks = corpus_chunks(package_dir, strategy=strategy, skip_bad=skip_bad)
    if mode == "bm25":
        if context:
            chunks = [c for c in chunks if applies_to(c, context)]
        return BM25Index(chunks).search(query, k=k)

    # 排除场合 filtering happens after retrieval for Vespa modes, so an
    # inapplicable chunk at rank ≤ k must not evict the applicable answer at
    # k+1 (red-team day4 #14). Overfetch bound = the full corpus: exact at
    # this scale, so the post-filter cut provably loses nothing. The bound
    # only holds within the engine's top-k cap — beyond it, refuse rather
    # than silently return an incomplete filter (red-team day4 C3).
    fetch_k = max(k, len(chunks)) if context else k
    if context:
        from learnarken.vespa.store import MAX_TOP_K

        if fetch_k > MAX_TOP_K:
            raise ValueError(
                f"排除场合 filtering needs a full-corpus overfetch of {fetch_k} chunks, "
                f"above the engine cap {MAX_TOP_K} — refusing an incomplete filter "
                "(fail closed); push the applicability predicate engine-side first"
            )
    retriever = _mode_retriever(
        mode, chunks, k=fetch_k, strategy=strategy, package=Path(package_dir).name
    )
    ranked = [from_document(d) for d in retriever.invoke(query)]
    # The engine may only answer with this package's chunks (red-team day4
    # C1/C2): a stale index, or another directory sharing this basename,
    # would otherwise be silently cited.
    local_ids = {c.chunk_id for c in chunks}
    foreign = sorted(c.chunk_id for c in ranked if c.chunk_id not in local_ids)
    if foreign:
        raise ValueError(
            f"engine returned chunk(s) not in this package's corpus {foreign[:3]} — "
            "stale or colliding index; re-run `learnarken index` (fail closed)"
        )
    if context:
        ranked = [c for c in ranked if applies_to(c, context)]
    # Fused/reranked orderings have no single comparable score — rank is the
    # honest output (scores from different arms are incommensurable).
    return [ScoredChunk(rank=i + 1, score=0.0, chunk=c) for i, c in enumerate(ranked[:k])]


def _mode_retriever(
    mode: str, chunks: list[Chunk], k: int, strategy: str, package: str | None = None
):
    from learnarken.retrieval import hybrid as _hybrid
    from learnarken.retrieval.dense import VespaDenseRetriever

    if mode == "dense":
        return VespaDenseRetriever(k=k, strategy=strategy, package=package)
    if mode == "hybrid":
        return _hybrid.hybrid_retriever(
            chunks, k=max(k, _hybrid.CANDIDATE_K), strategy=strategy, package=package
        )
    if mode == "hybrid-graph":
        return _hybrid.graph_hybrid_retriever(
            chunks, k=max(k, _hybrid.CANDIDATE_K), strategy=strategy, package=package
        )
    return _hybrid.reranked_retriever(
        chunks,
        k=k,
        candidate_k=max(k, _hybrid.CANDIDATE_K),
        strategy=strategy,
        package=package,
        base="hybrid-graph" if mode == "hybrid-graph-rerank" else "hybrid",
    )


MANIFEST_PATH = Path(".vespa-manifest.json")  # git-ignored; written by index_package


def figure_chunks_for_package(package_dir: str | Path, strategy: str) -> list[Chunk]:
    """Build figure chunks for a package from its committed describe records
    (Day 12). No VLM here; each record is re-verified against the current PNG +
    DM XML inside `ingest.figure_chunks` (red-team P1). Missing records ⇒ none."""
    from learnarken.loader import load_package
    from learnarken.multimodal import ingest

    package_dir = Path(package_dir)
    records = ingest.load_records(package_dir)
    if not records:
        return []
    package = load_package(package_dir)
    chunks: list[Chunk] = []
    for dm in package.data_modules:
        chunks.extend(ingest.figure_chunks(dm, records, strategy, package_dir))
    return chunks


def corpus_chunks(
    package_dir: str | Path, strategy: str = "structure", skip_bad: bool = False
) -> list[Chunk]:
    """The one true corpus builder: text chunks (`chunk_package`) PLUS Day 12
    figure chunks. Every retrieval/verification path — index, search, query,
    ablation, corpus-identity verification — MUST build the local corpus through
    this, or figure chunks fed to the engine look 'foreign' and the query fails
    closed (red-team P1: index-vs-query corpus mismatch)."""
    return chunk_package(
        package_dir, strategy=strategy, skip_bad=skip_bad
    ) + figure_chunks_for_package(package_dir, strategy)


def index_package(
    package_dirs: list[str | Path], strategy: str = "structure", skip_bad: bool = False
) -> int:
    """Chunk, embed with the default provider, and (up)feed Vespa. Idempotent.

    Writes a corpus manifest (red-team day4 #4, adjudicated ACCEPT): what was
    fed, from where, chunked how, embedded by what — so evaluation can verify
    it is comparing rows over exactly this corpus, not a stale or mixed index.
    """
    import json as _json

    from learnarken import vespa
    from learnarken.embedding.providers import (
        DEFAULT_PROVIDER,
        DIMENSIONS,
        REVISIONS,
        get_embeddings,
    )

    names = [Path(p).name for p in package_dirs]
    if len(set(names)) != len(names):
        raise ValueError(
            f"package directory basenames collide: {sorted(names)} — the basename is "
            "the engine-side scope identity, so same-named packages cannot be indexed "
            "together (red-team day4 C1)"
        )
    raw: list[Chunk] = []
    owner: dict[str, str] = {}  # chunk_id → owning package name (red-team #5)

    def _own(c: Chunk, name: str) -> None:
        if owner.get(c.chunk_id, name) != name:
            raise ValueError(
                f"chunk {c.chunk_id} appears in both {owner[c.chunk_id]!r} and "
                f"{name!r} — cannot assign a package scope; index them separately"
            )
        owner[c.chunk_id] = name
        raw.append(c)

    for pkg in package_dirs:
        name = Path(pkg).name
        # corpus_chunks = text + Day 12 figure chunks, the same builder the query
        # and verification paths use, so index and query never disagree (P1).
        for c in corpus_chunks(pkg, strategy=strategy, skip_bad=skip_bad):
            _own(c, name)
    chunks = _dedupe_chunks(raw)
    if not vespa.is_up():
        vespa.deploy()
    vectors = get_embeddings().embed_documents([c.text for c in chunks])
    fed = vespa.feed(chunks, vectors, [owner[c.chunk_id] for c in chunks])
    # Graph sync (Day 5 decision 6, spec Q1): the dependency graph is part of
    # the index, fed from the same chunks — Neo4j down fails the index run
    # (fail closed) rather than leaving vector and graph views divergent.
    from learnarken import graph

    graph_stats = graph.sync(chunks, owner)
    MANIFEST_PATH.write_text(
        _json.dumps(
            {
                "packages": sorted(str(p) for p in package_dirs),
                "strategy": strategy,
                "provider": DEFAULT_PROVIDER,
                "revision": REVISIONS[DEFAULT_PROVIDER],
                "dimension": DIMENSIONS[DEFAULT_PROVIDER],
                "chunk_ids": sorted(c.chunk_id for c in chunks),
                # Day 11 (spec T7): graph and index provably come from the same
                # ingest — the synced node/edge counts are part of the manifest.
                "graph": graph_stats,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return fed


def verify_corpus(chunks: list[Chunk], strategy: str) -> None:
    """Fail closed unless the engine's contents match this exact corpus.

    Three checks (red-team day4 #4): the manifest exists and matches the
    requested corpus (provider/strategy/chunk ids), AND the engine's actual
    document-id set — fetched via the visit API, not counted — equals the
    local chunk-id set.
    """
    import json as _json

    from learnarken import vespa
    from learnarken.embedding.providers import DEFAULT_PROVIDER, REVISIONS

    local_ids = {c.chunk_id for c in chunks}
    if not MANIFEST_PATH.is_file():
        raise ValueError(
            "no corpus manifest found — run `learnarken index` first "
            "(fail closed: cannot prove what the engine holds)"
        )
    manifest = _json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    problems = []
    if manifest.get("strategy") != strategy:
        problems.append(f"manifest strategy {manifest.get('strategy')!r} != requested {strategy!r}")
    if manifest.get("provider") != DEFAULT_PROVIDER:
        problems.append(
            f"manifest provider {manifest.get('provider')!r} != current default "
            f"{DEFAULT_PROVIDER!r} (vectors in the engine are from another model)"
        )
    if manifest.get("revision") != REVISIONS[DEFAULT_PROVIDER]:
        problems.append(
            f"manifest model revision {manifest.get('revision')!r} != pinned "
            f"{REVISIONS[DEFAULT_PROVIDER]!r} (INV-5: vectors are from another snapshot)"
        )
    if set(manifest.get("chunk_ids", ())) != local_ids:
        problems.append("manifest chunk ids differ from the local corpus")
    engine_ids = vespa.list_doc_ids()
    if engine_ids != local_ids:
        extra, missing = engine_ids - local_ids, local_ids - engine_ids
        problems.append(f"engine holds {len(extra)} unknown / misses {len(missing)} expected docs")
    if problems:
        raise ValueError(
            "corpus verification failed — re-run `learnarken index` with the same "
            "packages/strategy (fail closed): " + "; ".join(problems)
        )


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
            raw.extend(corpus_chunks(pkg, strategy=strategy, skip_bad=skip_bad))
        chunks = _dedupe_chunks(raw)
        index = BM25Index(chunks)
        results[strategy] = evaluate_strategy(chunks, index.search, golden, resolved, ks=ks)
    return {
        "golden": str(golden_path),
        "n_queries": len(golden),
        "packages": [str(p) for p in package_dirs],
        "results": results,
    }


def run_ablation(
    package_dirs: list[str | Path],
    golden_path: str | Path,
    modes: tuple[str, ...] = MODES,
    ks: tuple[int, ...] = (5, 10),
    strategy: str = "structure",
    categories: dict[str, str] | None = None,
) -> dict:
    """The Day 4a ablation: same chunks, same golden set, one row per mode.

    Requires `index_package` to have fed Vespa with the same packages+strategy
    (manifest + engine-set verified — refuses to compare rows over mismatched
    corpora). Each mode runs every query exactly once; overall metrics, the
    per-category breakdown and p50 latency all derive from that single cached
    pass (red-team day4 #13 — no repeated model/reranker work). Deterministic:
    retrieval only, no sampling (seed irrelevant, recorded by the CLI for
    INV-5 form).
    """
    golden = load_golden(golden_path)
    # The single-pass cache is keyed by query text; duplicate texts would
    # collapse two golden rows into one audit identity (red-team day4 C6).
    texts = [q.query for q in golden]
    if len(set(texts)) != len(texts):
        duplicates = sorted({t for t in texts if texts.count(t) > 1})
        raise ValueError(f"duplicate golden query texts: {duplicates[:3]} (fail closed)")
    anchors = {a for q in golden for a in q.relevant}
    resolved = resolve_anchors(package_dirs, anchors)
    missing = unresolved_anchors(anchors, resolved)
    if missing:
        raise ValueError(f"{len(missing)} golden anchor(s) do not resolve: {sorted(missing)[:4]}")

    raw: list[Chunk] = []
    for pkg in package_dirs:
        raw.extend(corpus_chunks(pkg, strategy=strategy))
    chunks = _dedupe_chunks(raw)

    needs_vespa = any(m != "bm25" for m in modes)
    if needs_vespa:
        # Manifest + engine-set verification (red-team day4 #4, adjudicated
        # ACCEPT 2026-07-16) — replaces the count-only check.
        verify_corpus(chunks, strategy)
    if any(m in GRAPH_MODES for m in modes):
        # The graph route degrades to nothing when Neo4j is down (search-path
        # semantics); under ablation that would silently score hybrid+graph as
        # plain hybrid — refuse up front instead (fail closed, INV-5 honest rows).
        import json as _json

        from learnarken import graph

        if not graph.is_up():
            raise ValueError(
                "Neo4j is unreachable but a graph mode was requested — the graph "
                "route would silently degrade to plain hybrid, producing a "
                "dishonest ablation row (fail closed); start the neo4j container"
            )
        # The manifest's `graph` block is what `learnarken index` synced;
        # comparing it against the graph's live counts catches a stale graph
        # from a previous, different ingest (red-team day11 #1) — defense in
        # depth alongside sync() now being corpus-authoritative.
        manifest_graph = _json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("graph")
        if manifest_graph is not None and manifest_graph != graph.stats():
            raise ValueError(
                f"graph state {graph.stats()} does not match the manifest's recorded "
                f"sync {manifest_graph} — the graph is stale relative to the last "
                "`learnarken index` run (fail closed); re-run `learnarken index`"
            )

    results: dict[str, dict] = {}
    latencies: dict[str, float] = {}
    per_category: dict[str, dict[str, float]] = {}
    per_category_n: dict[str, int] = {}
    # evaluate_strategy probes rankings to max(ks, 10); the single real pass
    # per query must cache at least that depth (red-team day4 #13).
    top = max(ks + (10,))
    for mode in modes:
        if mode == "bm25":
            index = BM25Index(chunks)
            search = index.search
        else:
            # No package filter here: the ablation spans all indexed packages,
            # and verify_corpus already proved the engine holds exactly them.
            retriever = _mode_retriever(mode, chunks, k=top, strategy=strategy)

            def search(query: str, k: int, _r=retriever):
                docs = _r.invoke(query)[:k]
                return [
                    ScoredChunk(rank=i + 1, score=0.0, chunk=from_document(d))
                    for i, d in enumerate(docs)
                ]

        # One real search per query; every metric below derives from this cache.
        ranked_cache: dict[str, list[ScoredChunk]] = {}
        timings: list[float] = []
        for q in golden:
            t0 = time.perf_counter()
            ranked_cache[q.query] = search(q.query, k=top)
            timings.append(time.perf_counter() - t0)
        latencies[mode] = round(sorted(timings)[len(timings) // 2] * 1000, 1)  # p50 ms

        def cached_search(query: str, k: int, _cache=ranked_cache):
            return _cache[query][:k]

        results[mode] = evaluate_strategy(chunks, cached_search, golden, resolved, ks=ks)
        if categories:
            by_cat: dict[str, float] = {}
            for cat in sorted(set(categories.values())):
                subset = [q for q in golden if categories.get(q.query_id) == cat]
                metrics = evaluate_strategy(chunks, cached_search, subset, resolved, ks=ks)
                by_cat[cat] = metrics[f"recall@{min(ks)}"]
                # answerable n per category (red-team day4 #15) — mode-independent
                per_category_n[cat] = metrics["n_evaluated"]
            per_category[mode] = by_cat

    from learnarken.embedding.providers import pinned_revisions
    from learnarken.retrieval.hybrid import RERANKER_MODEL, RERANKER_REVISION

    return {
        "golden": str(golden_path),
        "n_queries": len(golden),
        "strategy": strategy,
        "packages": [str(p) for p in package_dirs],
        # INV-5 (red-team day4 #10): the exact model snapshots behind these rows.
        "model_revisions": {**pinned_revisions(), RERANKER_MODEL: RERANKER_REVISION},
        "results": results,
        "p50_ms": latencies,
        "per_category_recall": per_category,
        "per_category_n": per_category_n,
    }
