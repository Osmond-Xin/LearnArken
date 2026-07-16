# Day 4a dense bake-off — BGE-M3 / Qwen3-Embedding-8B (MiniMax row: historical)

> **AI-generated** (Claude, implementer), 2026-07-16, per Yi Xin's
> direction: three dense rows, the winner becomes the default provider.
> Harness: exact cosine in Python over structure chunks of package-a+c
> (43 chunks); scored by the Day 3 evaluation code against
> eval/golden/day4.jsonl (82 queries, of which 82 are
> human-reviewed Day 3 annotations; the rest are AI-drafted candidates
> pending review — both views reported). Reproduce:
> `uv run python tools/dense_bakeoff.py`

## Overall

| Provider | R@5 | R@10 | MRR | nDCG@10 | R@5 (human-32) | MRR (human-32) | embed docs (s) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bge-m3 | 0.9179 | 0.9701 | 0.8375 | 0.8678 | 0.9179 | 0.8375 | 0.2 |
| qwen3-8b | 0.9851 | 1.0 | 0.8703 | 0.9003 | 0.9851 | 0.8703 | 1.0 |

## Per category (Recall@5, all queries)

| Provider | applicability | cross_reference | descriptive | fault_isolation | identifier | identifier_perturbation | no_answer | paraphrase | procedural | warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bge-m3 | 1.0 | 0.8 | 1.0 | 1.0 | 0.7143 | 1.0 | 0.0 | 0.875 | 0.9167 | 1.0 |
| qwen3-8b | 1.0 | 1.0 | 1.0 | 1.0 | 0.8571 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 |

Notes: dense retrieval always returns k hits, so `zero_hit_rate` is 0
for every provider by construction — refusal is Day 5's job, and the
no_answer / identifier_perturbation categories are scored on that
basis (they read 0 here; the BM25 row is where refusal-by-absence
shows). Latency is embed time on this machine (M5 Max), not a serving
claim (INV-7).
