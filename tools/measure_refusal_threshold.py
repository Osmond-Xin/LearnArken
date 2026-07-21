"""Measure the Day 5 refusal threshold from golden-set score distributions.

The threshold is the answer layer's first fail-closed gate (spec: "measured,
recorded as an artifact — not hand-picked", INV-5). For every golden query,
run the same candidate retrieval the engine uses, rerank with the pinned
cross-encoder, and record the **top-1 score**. Answerable queries should
score high, no-answer traps low; the artifact records both distributions and
the chosen threshold with the rule that picked it.

Rule — **zero-false-refusal**: threshold = min(answerable top-1); the gate
refuses only scores strictly below it. Rationale: a gate-1 error is
unrecoverable (it short-circuits an answerable question into a refusal
before the LLM ever sees it), while a trap that slips through is still
caught by the LLM and citation-validation gates behind it. The measured
distributions overlap on this corpus (identifier-perturbation traps score
near-duplicate-high), so ANY separating threshold would falsely refuse some
answerable paraphrase queries — the artifact records both distributions and
how many traps gate 1 still catches. Caveats recorded in the artifact:
scores are sigmoid outputs of the pinned reranker (revision-specific), and
the rule is tuned on the measurement set itself — Day 8's adversarial eval
measures generalization.

    uv run python tools/measure_refusal_threshold.py
"""

from __future__ import annotations

import json
from pathlib import Path

from learnarken.answer.engine import CANDIDATE_K, DEFAULT_PACKAGES
from learnarken.retrieval import _dedupe_chunks, _mode_retriever, corpus_chunks, verify_corpus
from learnarken.retrieval.evaluate import load_golden
from learnarken.retrieval.hybrid import RERANKER_MODEL, RERANKER_REVISION, rerank_scored

GOLDEN = "eval/golden/day4.jsonl"
ARTIFACT = Path("eval/results/day5-refusal-threshold.json")


def choose_threshold(answerable: list[float], no_answer: list[float]) -> tuple[float, str]:
    # Unrounded (red-team day5 #5): rounding min-up would falsely refuse the
    # very query that set the threshold. The artifact stores the exact value;
    # a display-rounded copy is written alongside it.
    threshold = min(answerable)
    caught = sum(1 for s in no_answer if s < threshold)
    return (
        threshold,
        f"zero-false-refusal: min answerable top-1 (refuse strictly below); "
        f"gate 1 catches {caught}/{len(no_answer)} traps, the rest fall through "
        f"to the LLM and citation gates",
    )


def main() -> int:
    golden = load_golden(GOLDEN)
    chunks = _dedupe_chunks(
        [c for pkg in DEFAULT_PACKAGES for c in corpus_chunks(pkg, "structure")]
    )
    verify_corpus(chunks, "structure")
    retriever = _mode_retriever("hybrid", chunks, k=CANDIDATE_K, strategy="structure")

    answerable: dict[str, float] = {}
    no_answer: dict[str, float] = {}
    for q in golden:
        ranked = rerank_scored(q.query, retriever.invoke(q.query), k=1)
        top1 = ranked[0][1] if ranked else float("-inf")
        (answerable if q.relevant else no_answer)[q.query_id] = top1  # unrounded (#5)

    threshold, rule = choose_threshold(list(answerable.values()), list(no_answer.values()))
    artifact = {
        "golden": GOLDEN,
        "packages": list(DEFAULT_PACKAGES),
        "reranker": {RERANKER_MODEL: RERANKER_REVISION},
        "threshold": threshold,  # exact value the gate compares against
        "threshold_display": round(threshold, 4),  # human-facing only
        "rule": rule,
        "answerable_top1": {k: round(v, 6) for k, v in sorted(answerable.items())},
        "no_answer_top1": {k: round(v, 6) for k, v in sorted(no_answer.items())},
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=1), encoding="utf-8")
    print(
        f"answerable n={len(answerable)} min={min(answerable.values())}  "
        f"no-answer n={len(no_answer)} max={max(no_answer.values())}\n"
        f"threshold={threshold} ({rule})\nartifact -> {ARTIFACT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
