"""Embedding providers behind LangChain's `Embeddings` interface (Day 4a).

LangChain is the project's default stack (Yi Xin, 2026-07-16; discussions/
day4.md D12/D13). Every provider is exposed as a
`langchain_core.embeddings.Embeddings`, so retrievers, the semantic chunker,
and the bake-off all consume one interface.

DEFAULT_PROVIDER was decided by measurement, not preference — the Day 4a dense
bake-off (docs/notes/day4-dense-bakeoff.md): **Qwen3-Embedding-8B** R@5 0.985 /
R@10 1.0 / MRR 0.870 over the golden set, vs BGE-M3 0.910/0.970/0.833 and
MiniMax embo-01 0.500/0.679/0.359. The Day 4 adjudication (docs/reviews/
day4.md Part 2) then **removed MiniMax from the architecture entirely** —
its measured length bias inverted relevance rankings
(docs/notes/day4-embedding-length-bias.md); the retired client is preserved
at commit `b414fa4` so the historical bake-off row stays reproducible.

BGE-M3 stays registered: its sparse + ColBERT representations are the Day 4b
gate's candidate supplies, and it is the bake-off contrast row.

`embed_documents` vs `embed_query` carries each model's asymmetric encoding:
Qwen3 applies its "query" prompt on the query side (verified live: same text,
doc-vs-query cosine 0.857); BGE-M3 is symmetric.
"""

from __future__ import annotations

from functools import cache, lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # heavy import (torch); deferred to first use
    from langchain_core.embeddings import Embeddings
    from langchain_huggingface import HuggingFaceEmbeddings

# Vespa schema tensor dimension per provider (model cards; schema follows the
# default). All providers are configured to emit L2-normalized vectors, which
# is what makes `prenormalized-angular` correct in the schema.
DIMENSIONS = {"bge-m3": 1024, "qwen3-8b": 4096}

DEFAULT_PROVIDER = "qwen3-8b"

# HF snapshots pinned by commit SHA (red-team day4 #10, INV-5): an upstream
# weight update must not silently move published numbers. These are the local
# snapshots the Day 4 benchmarks ran on; they are recorded in the corpus
# manifest and every eval artifact.
REVISIONS = {
    "bge-m3": "5617a9f61b028005a4858fdac845db406aefb181",
    "qwen3-8b": "1d8ad4ca9b3dd8059ad90a75d4983776a23d44af",
}

_LOCAL_CONFIG: dict[str, dict] = {
    "bge-m3": {
        "model_name": "BAAI/bge-m3",
        "model_kwargs": {"device": "mps", "revision": REVISIONS["bge-m3"]},
        "encode_kwargs": {"normalize_embeddings": True},
    },
    "qwen3-8b": {
        "model_name": "Qwen/Qwen3-Embedding-8B",
        # fp16: 8B in fp32 would be ~30 GB; fp16 halves it and MPS prefers it.
        "model_kwargs": {
            "device": "mps",
            "revision": REVISIONS["qwen3-8b"],
            "model_kwargs": {"torch_dtype": "float16"},
        },
        "encode_kwargs": {"normalize_embeddings": True},
        # Qwen3's asymmetric side: documents plain, queries via its "query" prompt.
        "query_encode_kwargs": {"normalize_embeddings": True, "prompt_name": "query"},
    },
}


def pinned_revisions() -> dict[str, str]:
    """HF model name → pinned commit SHA, for recording in eval artifacts."""
    return {_LOCAL_CONFIG[p]["model_name"]: sha for p, sha in REVISIONS.items()}


def _local(name: str) -> HuggingFaceEmbeddings:
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(**_LOCAL_CONFIG[name])


@cache
def get_embeddings(provider: str | None = None) -> Embeddings:
    """One Embeddings instance per provider (cached — local models are heavy)."""
    name = provider or DEFAULT_PROVIDER
    if name in _LOCAL_CONFIG:
        return _local(name)
    raise ValueError(f"unknown embedding provider {name!r}; choose from {sorted(DIMENSIONS)}")


@lru_cache(maxsize=4096)
def _cached_query_vector(provider: str, text: str) -> tuple[float, ...]:
    return tuple(get_embeddings(provider).embed_query(text))


def embed_query_cached(text: str, provider: str | None = None) -> list[float]:
    """Query vector with memoization — sound because embeddings are
    deterministic per (model, text); repeated queries (eval passes, CLI
    retries) skip the model entirely."""
    return list(_cached_query_vector(provider or DEFAULT_PROVIDER, text))
