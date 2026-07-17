"""Day 5 answer-quality mini-eval (execution-plan: citation coverage +
groundedness, 20 samples for human review).

Runs `answer_question` live on a fixed-seed sample of golden queries
(answerable + no-answer traps), and writes an artifact with, per query: the
question, the answer or refusal, the cited chunk ids, and whether the
citations intersect the human-annotated relevant set. Summary metrics:

- **citation coverage** — of answered answerable queries, the fraction whose
  citations intersect the golden relevant set;
- **refusal accuracy** — traps refused / traps sampled;
- **false refusals** — answerable queries that got the placeholder.

Groundedness (does the answer text actually follow from the cited chunks?)
is the human half: Yi Xin reviews the 20 rows in the artifact (the trace ids
link each row to its full five-span trace).

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

    summary = {
        "n_sampled": len(sample),
        "answerable_sampled": len(sample) - min(n_traps, len(traps)),
        "traps_sampled": min(n_traps, len(traps)),
        "citation_coverage": round(covered / answered, 4) if answered else None,
        "false_refusals": false_refusals,
        "refusal_accuracy_on_traps": round(traps_refused / min(n_traps, len(traps)), 4),
        "human_review": "pending (Yi Xin, 20-sample groundedness check)",
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
