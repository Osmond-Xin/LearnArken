"""The grounded-answer engine (Day 5): strict two-outcome, defense in depth.

Per the Q2 ruling there are exactly two outputs: a cited answer or the
refusal placeholder. Three fail-closed gates, in order (each cheaper than
the next, each logged in the trace):

1. **threshold** — the reranker top-1 score is below the *measured* refusal
   threshold (artifact `eval/results/day5-refusal-threshold.json`, INV-5):
   short-circuit; the LLM is never called.
2. **llm / llm-contract** — the model says `is_answerable: false`, or its
   output violates the JSON contract.
3. **citation-validation** — any cited id outside the retrieved set (or an
   empty citation list on a claimed answer) refuses: a well-formed answer
   with unverifiable provenance is worthless in this domain (INV-4).

DMC/XPath are backfilled from chunk metadata by this module — the LLM only
ever emits chunk ids (citation-drift defense, DR report 陷阱一).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from learnarken import graph
from learnarken.answer.models import AnswerResult, Citation
from learnarken.answer.prompt import build_system, build_user, make_delimiter
from learnarken.answer.trace import new_trace_id, write_trace
from learnarken.chunking import chunk_package
from learnarken.chunking.base import Chunk
from learnarken.chunking.documents import from_document, to_document
from learnarken.llm import chat_json
from learnarken.retrieval import MODES, _dedupe_chunks, verify_corpus
from learnarken.retrieval.bm25 import BM25Index

PLACEHOLDER = "I don't know — no answer was found in the indexed corpus."
DEFAULT_PACKAGES = ("samples/package-a", "samples/package-c")
THRESHOLD_ARTIFACT = Path("eval/results/day5-refusal-threshold.json")
CANDIDATE_K = 20  # pre-rerank candidate depth, matching the retrieval layer
ANSWER_K = 5  # evidence chunks handed to the LLM (curated evidence, not stuffing)


def load_threshold(path: Path = THRESHOLD_ARTIFACT) -> float:
    """The refusal threshold is measured, never hand-picked (INV-5)."""
    if not path.is_file():
        raise ValueError(
            f"no refusal-threshold artifact at {path} — run "
            "`uv run python tools/measure_refusal_threshold.py` first (fail closed)"
        )
    artifact = json.loads(path.read_text(encoding="utf-8"))
    return float(artifact["threshold"])


def _candidates(question: str, chunks: list[Chunk], mode: str) -> list:
    """Mode-selected candidate documents (package=None: corpus is verified)."""
    from learnarken.retrieval import _mode_retriever

    if mode == "bm25":
        hits = BM25Index(chunks).search(question, k=CANDIDATE_K)
        return [to_document(h.chunk) for h in hits]
    base = "hybrid" if mode == "hybrid-rerank" else mode
    retriever = _mode_retriever(base, chunks, k=CANDIDATE_K, strategy="structure")
    return retriever.invoke(question)


def answer_question(
    question: str,
    package_dirs: list[str] | None = None,
    k: int = ANSWER_K,
    mode: str = "hybrid-rerank",
) -> AnswerResult:
    """Answer over the verified indexed corpus, or refuse. Never in between."""
    from learnarken.retrieval.hybrid import rerank_scored

    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {MODES}")
    packages = [str(p) for p in (package_dirs or DEFAULT_PACKAGES)]
    threshold = load_threshold()

    trace_id = new_trace_id()
    spans: dict = {"question": question, "packages": packages, "mode": mode}

    raw: list[Chunk] = []
    for package in packages:
        raw.extend(chunk_package(package, strategy="structure"))
    chunks = _dedupe_chunks(raw)
    if mode != "bm25":
        verify_corpus(chunks, "structure")  # fail closed on stale/mixed index

    t0 = time.perf_counter()
    candidates = _candidates(question, chunks, mode)
    ranked = rerank_scored(question, candidates, k=k)
    spans["retrieval"] = {
        "candidate_k": CANDIDATE_K,
        "candidates": [d.metadata.get("chunk_id") for d in candidates],
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    spans["rerank"] = {
        "threshold": threshold,
        "ranked": [(d.metadata.get("chunk_id"), s) for d, s in ranked],
    }

    def refuse(gate: str, extra: dict | None = None) -> AnswerResult:
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
    spans["graph"] = {"facts": [f.model_dump() for f in facts]}

    delimiter = make_delimiter()
    result = chat_json(build_system(delimiter), build_user(question, evidence, facts, delimiter))
    spans["llm"] = {
        "request_payload": result.request_payload,
        "model": result.model,
        "usage": result.usage,
    }
    spans["generation"] = {"raw_content": result.raw_content, "parsed": result.parsed}

    parsed = result.parsed
    if not (
        isinstance(parsed.get("is_answerable"), bool)
        and isinstance(parsed.get("answer"), str)
        and isinstance(parsed.get("citations"), list)
        and all(isinstance(c, str) for c in parsed["citations"])
    ):
        return refuse("llm-contract", {"keys": sorted(parsed)})
    if not parsed["is_answerable"]:
        return refuse("llm")
    cited = list(dict.fromkeys(parsed["citations"]))
    invalid = [c for c in cited if c not in evidence_ids]
    if invalid or not cited or not parsed["answer"].strip():
        return refuse("citation-validation", {"invalid_citations": invalid})

    citations = [
        Citation(chunk_id=c, dmc=by_id[c].dmc, source_path=by_id[c].source_path) for c in cited
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
