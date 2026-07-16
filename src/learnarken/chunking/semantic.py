"""Semantic chunking: cut where the meaning shifts (Day 4a, spec Q5).

The third strategy promised on Day 3 (discussions/day3.md D1), deliverable once
embeddings exist. Like `recursive` it is structure-blind — it never looks at the
XML tree — but unlike `recursive` it chooses boundaries from the content itself:
embed each sentence, measure the distance between neighbours, and cut where that
distance spikes.

Breakpoint rule: distances are compared against a **percentile of the DM's own
distances** rather than a fixed cosine threshold, because absolute similarity
scales vary by model and by text; a percentile adapts to the document.

Cost note: this is the only chunker that makes network calls (one embedding
request per DM). Tests that exercise it for real are `integration`-marked.
"""

from __future__ import annotations

import logging
import re

from lxml import etree

from learnarken.chunking.base import Chunk, inherited_fields, make_chunk_id
from learnarken.chunking.structure import _dm_refs, _icn_refs
from learnarken.loader import _text
from learnarken.models import DataModule

logger = logging.getLogger("learnarken")

STRATEGY = "semantic"

# Cut where a neighbour distance sits above this percentile of the DM's own
# distances. 95 is the common default; it yields few, confident cuts.
PERCENTILE = 95.0
# Below this many sentences a percentile is meaningless — emit one chunk.
MIN_SENTENCES = 4

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _embed(sentences: list[str], _mode: str = "db") -> list[list[float]]:
    """Sentence vectors via the default LangChain Embeddings provider (D13).

    Kept as a module-level indirection so tests monkeypatch this instead of
    the network. Boundary detection uses document-side encoding.
    """
    from learnarken.embedding.providers import get_embeddings

    return get_embeddings().embed_documents(sentences)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def _cosine(a: list[float], b: list[float]) -> float:
    # Providers are configured to emit L2-normalized vectors, so the dot
    # product is the cosine. Normalizing again here would be wasted work.
    return sum(x * y for x, y in zip(a, b, strict=True))


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile. Avoids a numpy dependency for one number."""
    if not values:
        raise ValueError("percentile of an empty list")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (pct / 100.0) * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def split_semantically(sentences: list[str], percentile: float = PERCENTILE) -> list[list[str]]:
    """Group sentences into semantically coherent runs."""
    if len(sentences) < MIN_SENTENCES:
        return [sentences] if sentences else []

    vectors = _embed(sentences, "db")
    # Distance, not similarity: high value = neighbours drifted apart = cut here.
    distances = [1.0 - _cosine(vectors[i], vectors[i + 1]) for i in range(len(vectors) - 1)]
    threshold = _percentile(distances, percentile)

    groups: list[list[str]] = []
    current = [sentences[0]]
    for i, distance in enumerate(distances):
        if distance >= threshold:
            groups.append(current)
            current = []
        current.append(sentences[i + 1])
    groups.append(current)
    return [g for g in groups if g]


def chunk_dm(path, tree: etree._ElementTree, dm: DataModule, digest: str = "") -> list[Chunk]:
    content = tree.getroot().find("content")
    if content is None:
        return []
    sentences = _sentences(_text(content))
    if not sentences:
        return []

    # Whole-DM metadata, same as the recursive control: a structure-blind
    # strategy cannot localize refs or hazards to a chunk.
    base = dict(
        strategy=STRATEGY,
        chunk_type="semantic",
        has_warning=dm.warnings > 0,
        has_caution=dm.cautions > 0,
        outbound_dm_refs=_dm_refs(content),
        icn_refs=_icn_refs(content),
        **inherited_fields(dm),
    )

    chunks: list[Chunk] = []
    for i, group in enumerate(split_semantically(sentences)):
        source_path = f"/dmodule[{dm.dmc}]#sem{i}"
        chunks.append(
            Chunk(
                chunk_id=make_chunk_id(dm.dmc, source_path, STRATEGY, digest),
                source_path=source_path,
                text=" ".join(group),
                **base,
            )
        )
    return chunks
