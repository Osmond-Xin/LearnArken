# Day 4a dense bake-off — MiniMax embo-01 / BGE-M3 / Qwen3-Embedding-8B

> **AI-generated** (Claude, implementer), 2026-07-16, per Yi Xin's
> direction: three dense rows, the winner becomes the default provider.
> Harness: exact cosine in Python over structure chunks of package-a+c
> (43 chunks); scored by the Day 3 evaluation code against
> eval/golden/day4.jsonl (82 queries, of which 32 are
> human-reviewed Day 3 annotations; the rest are AI-drafted candidates
> pending review — both views reported). Reproduce:
> `uv run python tools/dense_bakeoff.py`

## Overall

| Provider | R@5 | R@10 | MRR | nDCG@10 | R@5 (human-32) | MRR (human-32) | embed docs (s) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| minimax | 0.5 | 0.6791 | 0.3587 | 0.4298 | 0.463 | 0.4051 | 3.9 |
| bge-m3 | 0.9104 | 0.9701 | 0.8325 | 0.8664 | 0.9259 | 0.8417 | 0.7 |
| qwen3-8b | 0.9851 | 1.0 | 0.8703 | 0.9027 | 0.963 | 0.8386 | 1.6 |

## Per category (Recall@5, all queries)

| Provider | applicability | cross_reference | descriptive | fault_isolation | identifier | identifier_perturbation | no_answer | paraphrase | procedural | warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| minimax | 1.0 | 0.2 | 0.8571 | 0.75 | 0.7143 | 1.0 | 0.0 | 0.1667 | 0.375 | 0.2222 |
| bge-m3 | 1.0 | 0.8 | 1.0 | 1.0 | 0.7143 | 1.0 | 0.0 | 0.8333 | 0.9167 | 1.0 |
| qwen3-8b | 1.0 | 1.0 | 1.0 | 1.0 | 0.8571 | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 |

Notes: dense retrieval always returns k hits, so `zero_hit_rate` is 0
for every provider by construction — refusal is Day 5's job, and the
no_answer / identifier_perturbation categories are scored on that
basis (they read 0 here; the BM25 row is where refusal-by-absence
shows). Latency is embed time on this machine (M5 Max), not a serving
claim (INV-7).
