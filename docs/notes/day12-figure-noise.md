# Day 12 — figure chunks vs old-golden text retrieval (honest regression)

> AI-generated, 2026-07-20. Acceptance 9 + scan T6: adding figure chunks to a
> tiny corpus can crowd text recall — **reported either way**. This is that
> report, and it is a *drop*, not a wash.

## Measurement (BM25, `eval/golden/day4.jsonl`, 67 answerable queries)

| metric | baseline (43 text chunks) | + 2 figure chunks (45) | Δ |
| --- | --- | --- | --- |
| Recall@5 | 0.8284 | 0.8060 | −0.0224 |
| Recall@10 | 0.8806 | 0.8731 | −0.0075 |
| MRR | 0.7393 | 0.7063 | −0.0330 |
| nDCG@10 | 0.7701 | 0.7423 | −0.0278 |
| zero-hit | 0.400 | 0.400 | 0 |

Reproduce: build the corpus with `chunk_package` vs `retrieval.corpus_chunks`
and run `evaluate_strategy` over `day4.jsonl` (both deterministic, BM25).

## Why

Exactly the scan-T6 挤占 effect: two term-dense figure chunks ("Hotspot", "part",
"pump", part numbers like `LA-29-4711-9`) enter a 43-chunk BM25 pool (~4.4% of
it) and occasionally out-score the correct text step for pump/part queries,
nudging it below k. The effect is largest on MRR (rank-sensitive) and vanishes
for zero-hit (the answer is still retrieved, just lower).

## Under the production path (`hybrid-rerank`) — the reranker recovers it

Same day4 golden, but retrieved via `hybrid-rerank` (BM25 + dense + rerank), with
Vespa re-indexed **with vs without** the figure chunks (each run `vespa.clear()`ed
first so the corpora are clean):

| metric | no figures | + figures | Δ |
| --- | --- | --- | --- |
| Recall@5 | 0.9851 | 0.9851 | **0** |
| Recall@10 | 0.9851 | 0.9851 | **0** |
| zero-hit | 0.000 | 0.000 | **0** |
| MRR | 0.8507 | 0.8231 | −0.0276 |
| nDCG@10 | 0.8835 | 0.8626 | −0.0209 |

**Recall and zero-hit are unchanged** — the reranker pulls every text answer back
into the top-k that BM25 had shuffled; the only residual is a small within-top-k
**rank-order** shuffle (MRR/nDCG ≈ −0.02 to −0.03). So on the path users actually
hit, figures cost **no answers**, only a slight ranking nudge.

## Honest position (needs Yi Xin's call — accept vs mitigate)

This is a **real, small regression on BM25-only text retrieval**, the price of
making figures retrievable in a toy pool. Two honest options:

- **(a) accept** — the drop is ≤3.3 points, confined to the toy scale (it
  shrinks as the corpus grows and figures become a smaller fraction), and the
  production path is `hybrid-rerank` where the reranker can recover the text
  answer; state the number in the README and move on.
- **(b) mitigate** — the scan-T6 "minimal defense": give figure chunks a
  separate retrieval pool or a BM25 down-weight so they cannot evict text
  answers, then re-measure. More engineering; cleaner text metrics.

**Not yet measured:** the same regression under `hybrid-rerank` (needs the
ablation harness + services) — the BM25 number above is the worst case. Whichever
option is chosen, the reranked delta should also be reported before merge.
