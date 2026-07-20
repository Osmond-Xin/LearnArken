"""The grounded-answer engine (Day 5): strict two-outcome, defense in depth.

Per the Q2 ruling there are exactly two outputs: a cited answer or the
refusal placeholder. Three fail-closed gates, in order (each cheaper than
the next, each logged in the trace):

1. **threshold** — the reranker top-1 score is below the *measured* refusal
   threshold (artifact `eval/results/day5-refusal-threshold.json`, INV-5):
   short-circuit; the LLM is never called.
2. **llm / llm-contract** — the model says `is_answerable: false`, or its
   output violates the JSON contract.
3. **citation-validation** — each citation must name a retrieved chunk AND
   carry a `supporting_quote` that is a verbatim (whitespace/case-tolerant)
   span of that chunk. A valid id with an unfindable quote refuses: a
   well-formed answer with unverifiable provenance is worthless here (INV-4,
   red-team day5 #1 — a valid pointer is not groundedness).

DMC/XPath are backfilled from chunk metadata by this module — the LLM only
ever emits chunk ids + quotes (citation-drift defense, DR report 陷阱一).
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from pathlib import Path

from learnarken import graph
from learnarken.answer.models import AnswerResult, Citation
from learnarken.answer.prompt import build_system, build_user, make_delimiter
from learnarken.answer.stream import AnswerFieldExtractor
from learnarken.answer.trace import new_trace_id, write_trace
from learnarken.chunking import chunk_package
from learnarken.chunking.base import Chunk
from learnarken.chunking.documents import from_document, to_document
from learnarken.config import REPO_ROOT
from learnarken.llm import LLMContractError, chat_json, chat_json_stream
from learnarken.retrieval import GRAPH_MODES, MODES, _dedupe_chunks, verify_corpus
from learnarken.retrieval.bm25 import BM25Index

PLACEHOLDER = "I don't know — no answer was found in the indexed corpus."
DEFAULT_PACKAGES = ("samples/package-a", "samples/package-c")
# Resolve from the repo root, not cwd — a poisoned artifact in the working
# directory must not be able to disable the gate (red-team day5 #6).
THRESHOLD_ARTIFACT = REPO_ROOT / "eval/results/day5-refusal-threshold.json"
CANDIDATE_K = 20  # pre-rerank candidate depth, matching the retrieval layer
ANSWER_K = 5  # evidence chunks handed to the LLM (curated evidence, not stuffing)
# A supporting quote must be substantial: an empty/one-word span trivially
# substring-matches any chunk and proves nothing (red-team day5 #1 convergence).
MIN_QUOTE_CHARS = 12


def load_threshold(path: Path = THRESHOLD_ARTIFACT) -> float:
    """The refusal threshold is measured (INV-5) and validated on load.

    A non-finite or out-of-range value would silently disable gate 1
    (`score < NaN` is always false) — reject it rather than trust the file
    (red-team day5 #6). The reranker emits sigmoid scores in [0, 1].
    """
    if not path.is_file():
        raise ValueError(
            f"no refusal-threshold artifact at {path} — run "
            "`uv run python tools/measure_refusal_threshold.py` first (fail closed)"
        )
    artifact = json.loads(path.read_text(encoding="utf-8"))
    threshold = float(artifact["threshold"])
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError(
            f"refusal threshold {threshold!r} is not a finite [0,1] value (fail closed)"
        )
    return threshold


def _normalize(text: str) -> str:
    """Whitespace-collapsed, case-folded — the substring test tolerates
    reflowed spacing/newlines but not invented content (red-team day5 #1)."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def _candidates(question: str, chunks: list[Chunk], mode: str) -> list:
    """Mode-selected candidate documents (package=None: corpus is verified)."""
    from learnarken.retrieval import _mode_retriever

    if mode == "bm25":
        hits = BM25Index(chunks).search(question, k=CANDIDATE_K)
        return [to_document(h.chunk) for h in hits]
    # The engine reranks itself (rerank_scored), so a *-rerank mode retrieves
    # through its fusion base rather than double-reranking.
    base = {"hybrid-rerank": "hybrid", "hybrid-graph-rerank": "hybrid-graph"}.get(mode, mode)
    retriever = _mode_retriever(base, chunks, k=CANDIDATE_K, strategy="structure")
    return retriever.invoke(question)


def answer_question(
    question: str,
    package_dirs: list[str] | None = None,
    k: int = ANSWER_K,
    mode: str = "hybrid-rerank",
    on_event: Callable[[str, dict], None] | None = None,
) -> AnswerResult:
    """Answer over the verified indexed corpus, or refuse. Never in between.

    `on_event` (Day 6 SSE path) receives progress beats as they happen:
    `("status", {"stage"})`, `("token", {"text"})` for incremental answer
    text (pre-verification — SPEC day6 decision 3), and `("retract",
    {"gate", "message"})` when a post-generation gate voids what was
    streamed. The threshold gate never retracts: nothing was generated.
    The return value is unchanged either way.
    """
    from learnarken.retrieval.hybrid import rerank_scored

    emit = on_event or (lambda kind, data: None)
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {MODES}")
    packages = [str(p) for p in (package_dirs or DEFAULT_PACKAGES)]
    threshold = load_threshold()

    trace_id = new_trace_id()
    spans: dict = {"question": question, "packages": packages, "mode": mode}

    emit("status", {"stage": "retrieval"})
    raw: list[Chunk] = []
    for package in packages:
        raw.extend(chunk_package(package, strategy="structure"))
    chunks = _dedupe_chunks(raw)
    if mode != "bm25":
        verify_corpus(chunks, "structure")  # fail closed on stale/mixed index

    t0 = time.perf_counter()
    candidates = _candidates(question, chunks, mode)
    emit("status", {"stage": "rerank"})
    ranked = rerank_scored(question, candidates, k=k)
    spans["retrieval"] = {
        "candidate_k": CANDIDATE_K,
        "candidates": [d.metadata.get("chunk_id") for d in candidates],
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    if mode in GRAPH_MODES:
        # Day 11 explainability: which entities linked and which candidates the
        # graph route contributed, with hop/direction provenance (spec §3).
        from learnarken.retrieval.entity_link import build_lexicon, link_entities

        spans["graph"] = {
            "entities": [e.model_dump() for e in link_entities(question, build_lexicon(chunks))],
            "candidates": [
                {
                    "chunk_id": d.metadata.get("chunk_id"),
                    "hop": d.metadata["graph_hop"],
                    "direction": d.metadata["graph_direction"],
                }
                for d in candidates
                if "graph_hop" in d.metadata
            ],
        }
    spans["rerank"] = {
        "threshold": threshold,
        "ranked": [(d.metadata.get("chunk_id"), s) for d, s in ranked],
    }

    def refuse(gate: str, extra: dict | None = None) -> AnswerResult:
        if gate != "threshold":
            # Generation happened (or was attempted) and a fail-closed gate
            # voided it: anything already streamed must be withdrawn client-side.
            emit(
                "retract",
                {
                    "gate": gate,
                    "message": f"generated content failed the {gate} gate and has been retracted",
                },
            )
        spans["outcome"] = {"refused": True, "gate": gate, **(extra or {})}
        write_trace(trace_id, spans)
        return AnswerResult(
            question=question,
            answer_text=PLACEHOLDER,
            refused=True,
            refusal_gate=gate,
            trace_id=trace_id,
        )

    if not ranked or ranked[0][1] < threshold:
        top1 = ranked[0][1] if ranked else None
        return refuse("threshold", {"top1_score": top1})

    evidence = [from_document(d) for d, _ in ranked]
    evidence_ids = {c.chunk_id for c in evidence}
    by_id = {c.chunk_id: c for c in evidence}

    facts = graph.facts([c.dmc for c in evidence])  # GraphError propagates: fail closed
    # Merge into the Day 11 span (entities/candidates set above) rather than
    # overwrite it — both provenance views must survive to an answered trace
    # (red-team day11 #5: the graph explainability was being lost on every
    # non-refused answer).
    spans.setdefault("graph", {})["facts"] = [f.model_dump() for f in facts]

    delimiter = make_delimiter()
    emit("status", {"stage": "generating"})
    try:
        if on_event is None:
            result = chat_json(
                build_system(delimiter), build_user(question, evidence, facts, delimiter)
            )
        else:
            # Streaming path: forward only the answer-field text, extracted
            # incrementally from the raw delta stream. Usage is null in
            # stream mode (probe 2026-07-17), so the trace's llm span may
            # carry an empty usage dict here.
            extractor = AnswerFieldExtractor()

            def _on_delta(text: str) -> None:
                piece = extractor.feed(text)
                if piece:
                    emit("token", {"text": piece})

            result = chat_json_stream(
                build_system(delimiter),
                build_user(question, evidence, facts, delimiter),
                on_delta=_on_delta,
            )
    except LLMContractError as exc:
        # The service answered but broke the JSON contract — a refusal, not a
        # transport error (red-team day5 #3): traced, exit 3, not exit 1.
        spans["llm"] = {"contract_error": str(exc)}
        return refuse("llm-contract", {"error": str(exc)})
    spans["llm"] = {
        "request_payload": result.request_payload,
        "model": result.model,
        "usage": result.usage,
    }
    spans["generation"] = {"raw_content": result.raw_content, "parsed": result.parsed}

    parsed = result.parsed
    citations_raw = parsed.get("citations")
    if not (
        isinstance(parsed.get("is_answerable"), bool)
        and isinstance(parsed.get("answer"), str)
        and isinstance(citations_raw, list)
        and all(
            isinstance(c, dict)
            and isinstance(c.get("chunk_id"), str)
            and isinstance(c.get("supporting_quote"), str)
            for c in citations_raw
        )
    ):
        return refuse("llm-contract", {"keys": sorted(parsed)})
    if not parsed["is_answerable"]:
        return refuse("llm")

    # Validate EVERY citation (not just the first per chunk — red-team day5 #1
    # convergence): the id must be in the retrieved set, and the quote must be
    # a substantial verbatim span of that chunk. Empty/short quotes trivially
    # substring-match and are rejected before the containment test. A quote
    # present in EVERY retrieved chunk is boilerplate that discriminates
    # nothing — also rejected (day5 #1 convergence pass 2). These are all
    # *necessary* conditions; semantic entailment is Day 8.
    normalized_evidence = {cid: _normalize(c.text) for cid, c in by_id.items()}
    bad: list[str] = []
    for c in citations_raw:
        cid, quote = c["chunk_id"], c["supporting_quote"]
        normalized = _normalize(quote)
        boilerplate = len(by_id) > 1 and all(
            normalized in text for text in normalized_evidence.values()
        )
        if (
            cid not in evidence_ids
            or len(normalized) < MIN_QUOTE_CHARS
            or normalized not in normalized_evidence[cid]
            or boilerplate
        ):
            bad.append(cid)
    if bad or not citations_raw or not parsed["answer"].strip():
        return refuse("citation-validation", {"invalid_or_ungrounded": bad})

    # All quotes validated; de-dup by chunk id (keep the first) for display.
    seen: dict[str, str] = {}
    for c in citations_raw:
        seen.setdefault(c["chunk_id"], c["supporting_quote"])
    citations = [
        Citation(
            chunk_id=cid,
            dmc=by_id[cid].dmc,
            source_path=by_id[cid].source_path,
            supporting_quote=quote,
        )
        for cid, quote in seen.items()
    ]
    spans["outcome"] = {
        "refused": False,
        "citations": [c.model_dump() for c in citations],
    }
    write_trace(trace_id, spans)
    return AnswerResult(
        question=question,
        answer_text=parsed["answer"].strip(),
        refused=False,
        citations=citations,
        graph_facts=facts,
        trace_id=trace_id,
        model=result.model,
        usage=result.usage,
    )
