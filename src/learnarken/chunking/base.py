"""Chunk model and metadata helpers (Day 3, docs/specs/day3.md).

A Chunk is the retrieval unit. It inherits identity and filter metadata from
the Day 2 DataModule (DMC, applicability, hazard flags, graph hooks) so that
retrieval can filter on applicability (排除场合) and surface hazard-carrying
content (紧急场合) without re-parsing the source.
"""

from __future__ import annotations

import hashlib
from datetime import date

from pydantic import BaseModel

from learnarken.models import Applicability, DataModule


class Chunk(BaseModel):
    chunk_id: str
    strategy: str  # "structure" | "recursive"
    dmc: str
    dm_title: str
    issue_info: str
    chunk_type: str  # step | warning | caution | description | fault | ipd | dm
    source_path: str  # absolute XPath (structure) or DM root + ordinal (recursive)
    text: str
    applicability: Applicability | None = None
    security_classification: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    has_warning: bool = False
    has_caution: bool = False
    outbound_dm_refs: list[str] = []
    icn_refs: list[str] = []


def inherited_fields(dm: DataModule) -> dict:
    """Metadata every chunk inherits from its data module (Day 2 model → chunk)."""
    return {
        "dmc": dm.dmc,
        "dm_title": dm.title,
        "issue_info": dm.issue_info.as_str() if dm.issue_info else "",
        "applicability": dm.applicability,
        "security_classification": dm.security_classification,
        "effective_date": dm.extension.effective_date if dm.extension else None,
        "expiry_date": dm.extension.expiry_date if dm.extension else None,
    }


def make_chunk_id(dmc: str, source_path: str, strategy: str) -> str:
    """Deterministic chunk id: stable across runs for the same anchor + strategy."""
    key = f"{dmc}|{source_path}|{strategy}".encode()
    return hashlib.sha1(key, usedforsecurity=False).hexdigest()[:12]


def _values_match(query_value: str, assertion_values: str) -> bool:
    """Does `query_value` satisfy a comma list of exact values / `min~max` ranges?"""
    for token in assertion_values.split(","):
        token = token.strip()
        if "~" in token:
            low, high = (p.strip() for p in token.split("~", 1))
            try:
                if int(low) <= int(query_value) <= int(high):
                    return True
            except ValueError:
                if low <= query_value <= high:  # lexical range fallback
                    return True
        elif token == query_value:
            return True
    return False


def applies_to(chunk: Chunk, context: dict[str, str]) -> bool:
    """排除场合 filter: keep the chunk unless an assertion excludes this context.

    For each (property, value) in `context`: a chunk carrying assertion(s) on
    that property is kept only if `value` matches one of them; a chunk with no
    assertion on that property is kept (absence of exclusion = applicable).
    """
    if chunk.applicability is None:
        return True
    for prop, value in context.items():
        constraints = [a for a in chunk.applicability.assertions if a.property_ident == prop]
        if constraints and not any(_values_match(value, a.values) for a in constraints):
            return False
    return True
