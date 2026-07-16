"""Embedding entry point (Day 4a, docs/specs/day4.md).

Provider = **Qwen3-Embedding-8B, local**, decided by the three-way bake-off
(docs/notes/day4-dense-bakeoff.md) and made the sole architecture provider by
the Day 4 adjudication (docs/reviews/day4.md Part 2): the MiniMax client was
removed after its measured length bias (docs/notes/day4-embedding-length-bias.md);
the historical client and its probe live at commit `b414fa4` for reproduction.

Everything consumes the LangChain `Embeddings` interface from
`learnarken.embedding.providers` — swapping providers is a registry entry,
never a call-site change.
"""

from learnarken.embedding.providers import (
    DEFAULT_PROVIDER,
    DIMENSIONS,
    embed_query_cached,
    get_embeddings,
)

# Provider-aware dimension of the default provider (red-team day4 #11: the old
# constant silently pinned the retired provider's 1536).
DIMENSION = DIMENSIONS[DEFAULT_PROVIDER]

__all__ = [
    "DEFAULT_PROVIDER",
    "DIMENSION",
    "DIMENSIONS",
    "embed_query_cached",
    "get_embeddings",
]
