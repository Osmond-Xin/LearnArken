"""Embedding provider entry point (Day 4a, docs/specs/day4.md).

MiniMax is the default provider for the dense path (decision 1) — an existing
subscription makes it the cheap option. It serves dense embeddings only; SPLADE,
ColBERT and rerankers come from elsewhere if they ever arrive (Day 4b).
"""

from __future__ import annotations

from learnarken.embedding.minimax import (
    DIMENSION,
    EmbeddingError,
    MiniMaxEmbedder,
    embed,
)

__all__ = ["DIMENSION", "EmbeddingError", "MiniMaxEmbedder", "embed"]
