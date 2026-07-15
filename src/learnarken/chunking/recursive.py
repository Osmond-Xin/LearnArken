"""Recursive character chunking: the fixed-window control strategy (Day 3).

Deliberately structure-blind — it splits the flattened DM text into
overlapping character windows. Its job is to be the baseline the
structure-aware strategy is measured against in the eval table (tutorial 02
§6: prove what structure-awareness is worth). No new dependencies.
"""

from __future__ import annotations

from lxml import etree

from learnarken.chunking.base import Chunk, inherited_fields, make_chunk_id
from learnarken.chunking.structure import _dm_refs, _icn_refs
from learnarken.loader import _text
from learnarken.models import DataModule

STRATEGY = "recursive"
WINDOW = 800
OVERLAP = 100


def _windows(text: str, window: int = WINDOW, overlap: int = OVERLAP) -> list[str]:
    if len(text) <= window:
        return [text] if text else []
    step = window - overlap
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + window, len(text))
        # Break at the last whitespace before the hard boundary to avoid mid-word cuts.
        if end < len(text):
            space = text.rfind(" ", start + step, end)
            if space != -1:
                end = space
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
    return [w for w in out if w]


def chunk_dm(path, tree: etree._ElementTree, dm: DataModule) -> list[Chunk]:
    content = tree.getroot().find("content")
    if content is None:
        return []
    text = _text(content)
    # Whole-DM metadata: the control strategy cannot localize refs/hazards to a
    # window, so every window inherits the DM's aggregate flags and graph hooks.
    base = dict(
        strategy=STRATEGY,
        chunk_type="recursive",
        has_warning=dm.warnings > 0,
        has_caution=dm.cautions > 0,
        outbound_dm_refs=_dm_refs(content),
        icn_refs=_icn_refs(content),
        **inherited_fields(dm),
    )
    chunks: list[Chunk] = []
    for i, window in enumerate(_windows(text)):
        source_path = f"/dmodule[{dm.dmc}]#win{i}"
        chunks.append(
            Chunk(
                chunk_id=make_chunk_id(dm.dmc, source_path, STRATEGY),
                source_path=source_path,
                text=window,
                **base,
            )
        )
    return chunks
