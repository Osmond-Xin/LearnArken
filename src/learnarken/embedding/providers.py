"""Embedding providers behind LangChain's `Embeddings` interface (Day 4a).

LangChain is the project's default stack (Yi Xin, 2026-07-16 — adopted as a
learning goal and system default; discussions/day4.md D12/D13). This module is
where that shows for embeddings: every provider — remote MiniMax or local
HuggingFace — is exposed as a `langchain_core.embeddings.Embeddings`, so
retrievers, the semantic chunker, and the bake-off all consume one interface.

`embed_documents` vs `embed_query` carries the asymmetric-encoding split:
for MiniMax that is the measured `type=db` / `type=query` switch; for Qwen3 it
is the model's query prompt (`prompt_name="query"`); BGE-M3 is symmetric.

DEFAULT_PROVIDER is decided by measurement, not preference: the Day 4a dense
bake-off (MiniMax / BGE-M3 / Qwen3-8B on the golden set) picks the winner —
"用数字开门", the project's own methodology.
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from langchain_core.embeddings import Embeddings

from learnarken.embedding.minimax import MiniMaxEmbedder

if TYPE_CHECKING:  # heavy import (torch); deferred to first use
    from langchain_huggingface import HuggingFaceEmbeddings

# Vespa schema tensor dimension per provider (measured / model cards).
DIMENSIONS = {"minimax": 1536, "bge-m3": 1024, "qwen3-8b": 4096}

# Winner of the Day 4a dense bake-off (docs/notes/day4-dense-bakeoff.md,
# 2026-07-16): Qwen3-8B R@5 0.985 / R@10 1.0 / MRR 0.870 over the 82-query
# golden set, vs BGE-M3 0.910/0.970/0.833 and MiniMax 0.500/0.679/0.359 (the
# measured length bias, docs/notes/day4-embedding-length-bias.md). Losers stay
# available as ablation contrast rows.
DEFAULT_PROVIDER = "qwen3-8b"


class MiniMaxProxyEmbeddings(Embeddings):
    """LangChain adapter over the probe-verified MiniMax client.

    The stock LangChain `MiniMaxEmbeddings` cannot talk to our proxy (403 —
    no `X-Proxy-Token` support), so we wrap our own client instead; the wire
    shape is otherwise identical (verified: cosine 1.000000 on the same text).
    """

    def __init__(self, client: MiniMaxEmbedder | None = None) -> None:
        self._client = client or MiniMaxEmbedder()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed(list(texts), "db")

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed([text], "query")[0]


_LOCAL_CONFIG: dict[str, dict] = {
    "bge-m3": {
        "model_name": "BAAI/bge-m3",
        "model_kwargs": {"device": "mps"},
        "encode_kwargs": {"normalize_embeddings": True},
    },
    "qwen3-8b": {
        "model_name": "Qwen/Qwen3-Embedding-8B",
        # fp16: 8B in fp32 would be ~30 GB; fp16 halves it and MPS prefers it.
        "model_kwargs": {"device": "mps", "model_kwargs": {"torch_dtype": "float16"}},
        "encode_kwargs": {"normalize_embeddings": True},
        # Qwen3's asymmetric side: documents plain, queries via its "query" prompt.
        "query_encode_kwargs": {"normalize_embeddings": True, "prompt_name": "query"},
    },
}


def _local(name: str) -> HuggingFaceEmbeddings:
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(**_LOCAL_CONFIG[name])


@cache
def get_embeddings(provider: str | None = None) -> Embeddings:
    """One Embeddings instance per provider (cached — local models are heavy)."""
    name = provider or DEFAULT_PROVIDER
    if name == "minimax":
        return MiniMaxProxyEmbeddings()
    if name in _LOCAL_CONFIG:
        return _local(name)
    raise ValueError(f"unknown embedding provider {name!r}; choose from {sorted(DIMENSIONS)}")
