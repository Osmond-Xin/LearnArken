"""Structure-aware chunking: cut on the document's own boundaries (Day 3).

S1000D-like content carries its cut lines — procedural steps, safety
warnings/cautions, description sections. Boundaries:

- each procedural step → one chunk; a warning/caution *inline* to that step is
  folded into it and sets the hazard flag (紧急场合);
- each reqSafety *preliminary* warning/caution → its own standalone chunk
  (retrievable on its own), NOT merged into the steps it guards;
- preliminary conditions / support equipment → "precondition" chunks, and
  close requirements → a "closeout" chunk (so procedural context is not
  silently dropped);
- description sections → one chunk per levelledPara.

Every chunk keeps the XPath anchor the golden set annotates against. Because a
step and its *preliminary* safety warning are separate chunks, answer-time
safety-context expansion (always pulling the DM's warning chunk) is a Day 5
RAG concern, not done here.
"""

from __future__ import annotations

from lxml import etree

from learnarken.chunking.base import Chunk, inherited_fields, make_chunk_id
from learnarken.loader import _dm_code, _text
from learnarken.models import DataModule

STRATEGY = "structure"


def _dm_refs(elem: etree._Element) -> list[str]:
    out = {
        _dm_code(code).as_str()
        for ref in elem.iter("dmRef")
        if (code := ref.find("dmRefIdent/dmCode")) is not None
    }
    return sorted(out)


def _icn_refs(elem: etree._Element) -> list[str]:
    return [g.get("infoEntityIdent") for g in elem.iter("graphic") if g.get("infoEntityIdent")]


def _make(
    elem: etree._Element,
    tree: etree._ElementTree,
    dm: DataModule,
    chunk_type: str,
    digest: str,
) -> Chunk:
    path = tree.getpath(elem)
    return Chunk(
        chunk_id=make_chunk_id(dm.dmc, path, STRATEGY, digest),
        strategy=STRATEGY,
        chunk_type=chunk_type,
        source_path=path,
        text=_text(elem),
        has_warning=elem.tag == "warning" or elem.find(".//warning") is not None,
        has_caution=elem.tag == "caution" or elem.find(".//caution") is not None,
        outbound_dm_refs=_dm_refs(elem),
        icn_refs=_icn_refs(elem),
        **inherited_fields(dm),
    )


def chunk_dm(path, tree: etree._ElementTree, dm: DataModule, digest: str = "") -> list[Chunk]:
    root = tree.getroot()
    content = root.find("content")
    if content is None:
        return []
    chunks: list[Chunk] = []

    procedure = content.find("procedure")
    if procedure is not None:
        for cond in procedure.iterfind("preliminaryRqmts/reqCondGroup"):
            chunks.append(_make(cond, tree, dm, "precondition", digest))
        for equip in procedure.iterfind("preliminaryRqmts/reqSupportEquips"):
            chunks.append(_make(equip, tree, dm, "precondition", digest))
        for safety in procedure.iterfind("preliminaryRqmts/reqSafety/safetyRqmts/warning"):
            chunks.append(_make(safety, tree, dm, "warning", digest))
        for safety in procedure.iterfind("preliminaryRqmts/reqSafety/safetyRqmts/caution"):
            chunks.append(_make(safety, tree, dm, "caution", digest))
        for step in procedure.iterfind("mainProcedure//proceduralStep"):
            chunks.append(_make(step, tree, dm, "step", digest))
        for close in procedure.iterfind("closeRqmts/reqCondGroup"):
            chunks.append(_make(close, tree, dm, "closeout", digest))

    for desc in content.iterfind(".//faultIsolation/faultDescription"):
        chunks.append(_make(desc, tree, dm, "fault", digest))
    for step in content.iterfind(".//isolationStep"):
        chunks.append(_make(step, tree, dm, "fault", digest))

    description = content.find("description")
    if description is not None:
        paras = description.findall("levelledPara") or [description]
        for para in paras:
            chunks.append(_make(para, tree, dm, "description", digest))

    ipd = content.find("illustratedPartsCatalog")
    if ipd is not None:
        chunk = _make(ipd, tree, dm, "ipd", digest)
        # Part numbers live in @partNumberValue (attributes, not element text),
        # so fold them into the searchable text — an IPD chunk without its part
        # numbers is useless for parts lookups.
        parts = [p.get("partNumberValue") for p in ipd.iter("partRef") if p.get("partNumberValue")]
        if parts:
            chunk = chunk.model_copy(update={"text": f"{chunk.text} {' '.join(parts)}"})
        chunks.append(chunk)

    if not chunks:  # unknown content type: one chunk for the whole DM (never drop content)
        chunks.append(_make(content, tree, dm, "dm", digest))
    return chunks
