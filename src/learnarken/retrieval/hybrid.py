"""Hybrid retrieval and reranking on LangChain primitives (Day 4a, D13).

Pipeline (tutorial 04 §6, spec decisions 4-5):

    BM25Retriever ─┐
                   ├─ EnsembleRetriever (reciprocal rank fusion, k=60) ─┐
    VespaDense ────┘                                                    │
                       ContextualCompressionRetriever ◄────────────────┘
                       └─ CrossEncoderReranker (bge-reranker-v2-m3, local)

- Fusion is RRF over ranks (`EnsembleRetriever`'s weighted RRF with equal
  weights) — never a weighted sum of raw scores; BM25 is unbounded and cosine
  is [-1,1], the scales are incommensurable (tutorial 04 §4).
- Fusion identity is `id_key="chunk_id"`: the BM25 side indexes text
  *augmented with attribute identifiers* while the dense side stores clean
  text, so page_content equality (the default identity) would never merge the
  two views of the same chunk.
- Rerank depth: each arm fetches `candidate_k` (> final k) so the reranker has
  real work; rerank must move nDCG/MRR, not Recall (spec, ablation self-check).
- Reranker runs in Python per Q3 (portability) — not as an ONNX model inside
  the engine.
"""

from __future__ import annotations

import threading

from langchain_classic.retrievers import ContextualCompressionRetriever, EnsembleRetriever
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker

from learnarken.chunking.base import Chunk
from learnarken.retrieval.bm25 import BM25Index
from learnarken.retrieval.dense import VespaDenseRetriever

RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
# Pinned snapshot (red-team day4 #10, INV-5) — recorded in eval artifacts.
RERANKER_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
RRF_K = 60  # EnsembleRetriever's `c`; the 2009 paper's constant — not a knob
CANDIDATE_K = 20  # per-arm fetch depth feeding fusion/rerank


def bm25_retriever(chunks: list[Chunk], k: int = CANDIDATE_K):
    index = BM25Index(chunks)
    if index.retriever is None:
        raise ValueError("cannot build a BM25 retriever over an empty chunk list")
    index.retriever.k = k
    return index.retriever


def hybrid_retriever(
    chunks: list[Chunk],
    k: int = CANDIDATE_K,
    strategy: str = "structure",
    package: str | None = None,
    clearance: str | None = None,
) -> EnsembleRetriever:
    """BM25 + Vespa dense, fused by reciprocal rank (equal weights = plain RRF).

    `chunks` is already clearance-filtered by the caller, which constrains the
    BM25 arm; `clearance` additionally constrains the dense arm engine-side, so
    neither route can surface an inadmissible chunk (red-team F-01).
    """
    return EnsembleRetriever(
        retrievers=[
            bm25_retriever(chunks, k=k),
            VespaDenseRetriever(k=k, strategy=strategy, package=package, clearance=clearance),
        ],
        weights=[0.5, 0.5],
        c=RRF_K,
        id_key="chunk_id",
    )


def graph_hybrid_retriever(
    chunks: list[Chunk],
    k: int = CANDIDATE_K,
    strategy: str = "structure",
    package: str | None = None,
    clearance: str | None = None,
) -> EnsembleRetriever:
    """BM25 + dense + graph expansion, plain three-way RRF (Day 11, spec §3).

    Equal weights — adding the third route is the single variable under
    ablation; no re-tuning of the existing pair (spec out-of-scope). The same
    chunk arriving from several routes needs no bespoke dedup: RRF fuses by
    `chunk_id` identity and sums the routes' contributions, which is the
    standard treatment (scan "unknown-unknown" #3). `EnsembleRetriever`
    de-duplicates by keeping the *first* document object seen for a given key
    (in `retrievers` order) — the fused score is unaffected by list order
    (it sums contributions by key regardless), but which object's *metadata*
    survives is not. Graph is listed **first** so its `graph_hop`/
    `graph_direction` provenance wins over a same-chunk BM25/dense copy that
    carries none — otherwise the answer trace would undercount the graph
    route's real contribution (red-team day11 #6).
    """
    from learnarken.retrieval.graph_expand import graph_expansion_retriever

    return EnsembleRetriever(
        retrievers=[
            graph_expansion_retriever(chunks, k=k),
            bm25_retriever(chunks, k=k),
            VespaDenseRetriever(k=k, strategy=strategy, package=package, clearance=clearance),
        ],
        weights=[1 / 3, 1 / 3, 1 / 3],
        c=RRF_K,
        id_key="chunk_id",
    )


_RERANKER_CACHE: dict[str, CrossEncoderReranker] = {}


# Single-flight, for the same reason as the embedding cache: an unlocked dict
# lets the warm thread and a concurrent query both build the cross-encoder
# (round-2 red team). What is cached is the *model* — the expensive part.
_RERANKER_LOCK = threading.Lock()


def _cross_encoder():
    """The shared, lazily loaded cross-encoder model."""
    with _RERANKER_LOCK:
        if "model" not in _RERANKER_CACHE:
            from langchain_community.cross_encoders import HuggingFaceCrossEncoder

            from learnarken.embedding.providers import resolve_device

            _RERANKER_CACHE["model"] = HuggingFaceCrossEncoder(
                model_name=RERANKER_MODEL,
                # Resolved, not hardcoded to "mps" — see providers.resolve_device
                # (deploy red team R-02): the hardcode made this Mac-only.
                model_kwargs={"device": resolve_device(), "revision": RERANKER_REVISION},
            )
    return _RERANKER_CACHE["model"]


def _reranker(top_n: int) -> CrossEncoderReranker:
    """A per-call wrapper around the shared model.

    The wrapper used to be cached and its `top_n` reassigned on every call —
    shared mutable state on a path two visitors can enter at once, so one
    query could rerank to the other's depth. The wrapper is cheap; the model
    is what must be shared (found while load-testing two concurrent visitors,
    2026-07-29).
    """
    return CrossEncoderReranker(model=_cross_encoder(), top_n=top_n)


def warm_reranker() -> None:
    """Load the cross-encoder ahead of the first request (deploy red team
    R-14). Scores one throwaway pair so the weights are actually resident, not
    merely constructed."""
    _reranker(1).model.score([("warm", "warm")])


def rerank_scored(query: str, documents: list, k: int = 10) -> list[tuple[object, float]]:
    """Cross-encoder scores for (query, doc) pairs, best first.

    The answer layer (Day 5) needs the raw scores — the refusal-threshold
    gate reads the top-1 score — which `CrossEncoderReranker` discards, so
    this scores through the same cached model directly.
    """
    if not documents:
        return []
    model = _reranker(top_n=k).model
    scores = model.score([(query, d.page_content) for d in documents])
    ranked = sorted(zip(documents, scores, strict=True), key=lambda pair: -pair[1])
    return [(d, float(s)) for d, s in ranked[:k]]


def reranked_retriever(
    chunks: list[Chunk],
    k: int = 10,
    candidate_k: int = CANDIDATE_K,
    strategy: str = "structure",
    package: str | None = None,
    base: str = "hybrid",
    clearance: str | None = None,
) -> ContextualCompressionRetriever:
    """The full pipeline: RRF candidates (`base` fusion) → cross-encoder rerank → top k.

    The reranker only ever sees admitted candidates: authorisation is applied
    when the candidate pool is built, not to the reranked output.
    """
    fuse = graph_hybrid_retriever if base == "hybrid-graph" else hybrid_retriever
    return ContextualCompressionRetriever(
        base_retriever=fuse(
            chunks, k=candidate_k, strategy=strategy, package=package, clearance=clearance
        ),
        base_compressor=_reranker(top_n=k),
    )
