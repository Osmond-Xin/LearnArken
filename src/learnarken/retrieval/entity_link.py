"""Deterministic query-side entity linking (Day 11, spec §1).

Regex + corpus-derived lexicons only — no LLM anywhere on this path (spec Key
Decision 1). Linking is fail-closed (INV-4): a candidate that does not match a
known corpus entity yields nothing, never a fuzzy guess. Everything here is a
pure function of (query, lexicon), so the graph route stays reproducible
(INV-5).

Three entity kinds, per the spec:
  dmc   a full (`DMC-LA100-A-29-10-00-00A-520A-A`) or bare
        (`29-10-00-00A-520A-A`) data-module code, validated against the
        indexed corpus; a bare code links to every corpus DMC it suffixes.
  part  a part number, matched *by lexicon membership* — the lexicon is built
        from IPD chunk text (where `structure.py` folds `@partNumberValue`
        in), so free text cannot false-positive into a part entity.
  task  a task/system phrase from DM titles (`techName — infoName` segments),
        ≥2 tokens so a generic single word ("description") never links;
        longest match wins over its own substrings.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from learnarken.chunking.base import Chunk

# Full DMC as it appears in `Chunk.dmc` (uppercase, DMC- head).
_FULL_DMC = re.compile(r"\bDMC(?:-[A-Z0-9]+)+\b")
# Bare S1000D code without the DMC-<modelIdent>-<sdc> head: 29-10-00-00A-520A-A
_BARE_DMC = re.compile(r"\b\d{2}-\d{2}-\d{2}-\d{2}[A-Z]-\d{3}[A-Z]-[A-Z]\b")
# Part-number *shape* used only to harvest lexicon candidates from IPD text:
# a short alpha prefix then ≥2 hyphenated groups (e.g. LA-29-4711-9). Query
# linking never trusts this shape alone — membership in the lexicon decides.
_PART_SHAPE = re.compile(r"\b[A-Z]{1,4}(?:-[A-Z0-9]+){2,}\b")
# Generic hyphenated-token scan for query-side lexicon lookup.
_HYPHEN_TOKEN = re.compile(r"\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b")

_MIN_TASK_TOKENS = 2


class LinkedEntity(BaseModel):
    surface: str
    kind: str  # "dmc" | "part" | "task"
    dmcs: tuple[str, ...]  # target DM nodes, sorted


class EntityLexicon(BaseModel):
    """Corpus-derived vocabulary, built at index/retriever-construction time
    from the same chunks the engines hold — no separate build entry, so lexicon
    and index cannot drift (spec T7)."""

    dmcs: tuple[str, ...] = ()
    parts: dict[str, tuple[str, ...]] = {}  # PART-NO → owning DMCs
    tasks: dict[str, tuple[str, ...]] = {}  # normalized phrase → DMCs


def _normalize(text: str) -> str:
    """Lowercase, punctuation→space, collapsed whitespace — phrase-match form."""
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z]+", " ", text.casefold())).strip()


_LEXICON_CACHE: dict[tuple[str, ...], EntityLexicon] = {}
_LEXICON_CACHE_MAXSIZE = 8  # a handful of distinct corpora is all one process sees


def build_lexicon(chunks: list[Chunk]) -> EntityLexicon:
    """Cached by the sorted chunk-id set (red-team day11 #10): a chunk_id is a
    content hash of (dmc, source_path, strategy, file_digest) — same id set
    means same corpus content, so the cache cannot serve a stale lexicon. This
    avoids rebuilding the lexicon on every retriever construction *and* again
    for the answer trace within the same query."""
    key = tuple(sorted(c.chunk_id for c in chunks))
    cached = _LEXICON_CACHE.get(key)
    if cached is not None:
        return cached
    if len(_LEXICON_CACHE) >= _LEXICON_CACHE_MAXSIZE:
        _LEXICON_CACHE.pop(next(iter(_LEXICON_CACHE)))  # evict oldest, unbounded-growth guard
    lexicon = _build_lexicon(chunks)
    _LEXICON_CACHE[key] = lexicon
    return lexicon


def _build_lexicon(chunks: list[Chunk]) -> EntityLexicon:
    dmcs: set[str] = set()
    parts: dict[str, set[str]] = {}
    tasks: dict[str, set[str]] = {}
    for chunk in chunks:
        dmcs.add(chunk.dmc)
        if chunk.chunk_type == "ipd":
            for token in _PART_SHAPE.findall(chunk.text):
                if any(ch.isdigit() for ch in token) and not token.startswith("DMC-"):
                    parts.setdefault(token, set()).add(chunk.dmc)
        for segment in chunk.dm_title.split("—"):
            phrase = _normalize(segment)
            if len(phrase.split()) >= _MIN_TASK_TOKENS:
                tasks.setdefault(phrase, set()).add(chunk.dmc)
    return EntityLexicon(
        dmcs=tuple(sorted(dmcs)),
        parts={p: tuple(sorted(d)) for p, d in sorted(parts.items())},
        tasks={t: tuple(sorted(d)) for t, d in sorted(tasks.items())},
    )


def link_entities(query: str, lexicon: EntityLexicon) -> list[LinkedEntity]:
    """All corpus entities the query names, deterministically ordered."""
    entities: list[LinkedEntity] = []
    upper = query.upper()

    consumed: list[tuple[int, int]] = []  # spans claimed by DMC matches
    for match in _FULL_DMC.finditer(upper):
        if match.group() in lexicon.dmcs:  # fail closed: unknown code links nothing
            entities.append(LinkedEntity(surface=match.group(), kind="dmc", dmcs=(match.group(),)))
            consumed.append(match.span())
    for match in _BARE_DMC.finditer(upper):
        if any(s <= match.start() and match.end() <= e for s, e in consumed):
            continue  # already part of a full-DMC match
        targets = tuple(d for d in lexicon.dmcs if d.endswith("-" + match.group()))
        if targets:
            entities.append(LinkedEntity(surface=match.group(), kind="dmc", dmcs=targets))
            consumed.append(match.span())

    for match in _HYPHEN_TOKEN.finditer(upper):
        if any(s <= match.start() and match.end() <= e for s, e in consumed):
            continue
        if match.group() in lexicon.parts:
            entities.append(
                LinkedEntity(surface=match.group(), kind="part", dmcs=lexicon.parts[match.group()])
            )

    normalized = _normalize(query)
    claimed: list[tuple[int, int]] = []
    for phrase in sorted(lexicon.tasks, key=lambda p: (-len(p), p)):  # longest first
        for match in re.finditer(rf"\b{re.escape(phrase)}\b", normalized):
            if any(s <= match.start() and match.end() <= e for s, e in claimed):
                continue  # substring of an already-matched longer phrase
            entities.append(LinkedEntity(surface=phrase, kind="task", dmcs=lexicon.tasks[phrase]))
            claimed.append(match.span())
            break  # one link per phrase is enough — seeds are a set anyway

    order = {"dmc": 0, "part": 1, "task": 2}
    return sorted(entities, key=lambda e: (order[e.kind], e.surface))
