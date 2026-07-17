"""Answer-layer models (Day 5, docs/specs/day5.md decision 3).

`Citation` metadata (DMC, XPath) is backfilled by the system from chunk
metadata — the LLM only ever emits short chunk ids (citation-drift defense);
it never gets to *state* where a chunk came from.
"""

from __future__ import annotations

from pydantic import BaseModel

from learnarken.graph import GraphFacts


class Citation(BaseModel):
    chunk_id: str
    dmc: str
    source_path: str  # XPath (structure chunks) — the trace-back anchor


class AnswerResult(BaseModel):
    question: str
    answer_text: str
    refused: bool
    # Which fail-closed gate fired: "threshold" | "llm" | "llm-contract" |
    # "citation-validation"; None when answered.
    refusal_gate: str | None = None
    citations: list[Citation] = []
    graph_facts: list[GraphFacts] = []
    trace_id: str
    model: str | None = None
    usage: dict = {}
