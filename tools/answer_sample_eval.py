"""Day 5 answer-quality mini-eval (execution-plan: citation coverage +
groundedness, 20 samples for human review).

Runs `answer_question` live on a fixed-seed sample of golden queries
(answerable + no-answer traps). Metrics are defined over the FULL sampled
sets, not the answered subset (red-team day5 #4 — no denominator that hides
false refusals):

- **answerable_success** — answered AND citations intersect the golden
  relevant set, over ALL sampled answerable queries (false refusals count
  against it);
- **false_refusal_rate** — sampled answerable queries that got the
  placeholder, over all sampled answerable;
- **trap_refusal_rate** — traps refused, over ALL sampled traps;
- **citation_coverage_when_answered** — the old covered/answered ratio, kept
  but explicitly labeled "among answered only" so it is not read as accuracy.

The `supporting_quote` substring check (engine gate 3) is the machine
groundedness floor; whether the answer *semantically* follows from the quotes
is still the human step — Yi Xin reviews the rows (trace ids link each to its
five-span trace). This artifact is evidence, not a merge gate by itself.

    uv run python tools/answer_sample_eval.py [--n 20] [--seed 42]
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from learnarken.answer import answer_question
from learnarken.answer.engine import DEFAULT_PACKAGES
from learnarken.chunking import chunk_package
from learnarken.retrieval import _dedupe_chunks
from learnarken.retrieval.evaluate import _anchor_chunk_sets, load_golden, resolve_anchors

GOLDEN = "eval/golden/day4.jsonl"
ARTIFACT = Path("eval/results/day5-answer-sample.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)  # sampling only — real seed use
    args = parser.parse_args()

    golden = load_golden(GOLDEN)
    chunks = _dedupe_chunks(
        [c for pkg in DEFAULT_PACKAGES for c in chunk_package(pkg, "structure")]
    )
    anchors = {a for q in golden for a in q.relevant}
    resolved = resolve_anchors(list(DEFAULT_PACKAGES), anchors)

    rng = random.Random(args.seed)
    answerable = [q for q in golden if q.relevant]
    traps = [q for q in golden if not q.relevant]
    n_traps = max(2, args.n // 5)
    sample = rng.sample(answerable, args.n - n_traps) + rng.sample(traps, min(n_traps, len(traps)))

    rows = []
    covered = answered = false_refusals = traps_refused = 0
    for q in sample:
        relevant_ids = (
            set().union(*_anchor_chunk_sets(q, chunks, resolved)) if q.relevant else set()
        )
        result = answer_question(q.query)
        cited = [c.chunk_id for c in result.citations]
        hit = bool(set(cited) & relevant_ids)
        if q.relevant:
            if result.refused:
                false_refusals += 1
            else:
                answered += 1
                covered += hit
        elif result.refused:
            traps_refused += 1
        rows.append(
            {
                "query_id": q.query_id,
                "question": q.query,
                "expected": "answer" if q.relevant else "refusal",
                "refused": result.refused,
                "refusal_gate": result.refusal_gate,
                "answer": result.answer_text,
                "citations": cited,
                "golden_relevant_chunk_ids": sorted(relevant_ids),
                "citations_hit_golden": hit if q.relevant and not result.refused else None,
                "trace_id": result.trace_id,
            }
        )
        status = "REFUSED" if result.refused else ("HIT" if hit else "MISS")
        print(f"  {q.query_id:<6} expected={'answer' if q.relevant else 'refusal':<8} {status}")

    n_answerable = len(sample) - min(n_traps, len(traps))
    n_trap = min(n_traps, len(traps))
    summary = {
        "n_sampled": len(sample),
        "answerable_sampled": n_answerable,
        "traps_sampled": n_trap,
        # End-to-end success over ALL answerable — false refusals count against it (#4).
        "answerable_success": round(covered / n_answerable, 4) if n_answerable else None,
        "false_refusal_rate": round(false_refusals / n_answerable, 4) if n_answerable else None,
        "trap_refusal_rate": round(traps_refused / n_trap, 4) if n_trap else None,
        # Kept for continuity but explicitly scoped so it isn't read as accuracy.
        "citation_coverage_when_answered": round(covered / answered, 4) if answered else None,
        "note": "coverage != correctness; supporting_quote substring is the machine "
        "groundedness floor; semantic groundedness review is a human step",
        "human_review": "pending (Yi Xin, groundedness of the answered rows)",
    }
    ARTIFACT.write_text(
        json.dumps(
            {"golden": GOLDEN, "seed": args.seed, "summary": summary, "rows": rows},
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nsummary: {summary}\nartifact -> {ARTIFACT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
