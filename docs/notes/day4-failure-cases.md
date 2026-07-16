# Day 4a failure-case analysis (execution-plan requirement)

> **AI-generated** (Claude, implementer), 2026-07-16. The plan asked for "at
> least one identifier/part-number query where dense loses to BM25". We found
> that case — but not where the plan expected it, and the honest story is
> better than the predicted one. Reproduce: `learnarken search` / the probe
> scripts below.

## 1. The predicted failure did NOT materialize at toy scale

Prediction (execution plan, tutorials 03/04): dense embeddings shred
identifiers into subword fragments, so identifier lookups lose to BM25.

Measured (ablation per-category, identifier lookups, Recall@5): dense
(Qwen3-8B) **0.857** vs BM25 **0.714** — dense did *not* lose. On a 43-chunk
corpus an 8B model attends to identifier tokens well enough to resolve exact
lookups. The textbook failure mode is real but scale- and model-dependent;
claiming it from this corpus would have been the "honest-looking but wrong"
conclusion the heavy red team exists to catch.

## 2. Where dense really loses: it cannot refuse (the perturbation trap)

Query: **`LA-29-4711-5`** — a part number one digit away from two real parts
(`LA-29-4711-1` pump, `LA-29-4711-9` gasket). **This part does not exist.**

| Path | Behavior |
| --- | --- |
| BM25 (identifier-preserving tokenizer) | tokenizes the query as one whole token, finds no posting, returns **zero hits — a correct refusal** |
| dense (Qwen3-8B, our best model) | returns the IPD chunk and pump-procedure chunks at high confidence — a fake part number *looks like* a part number in embedding space |

Across all 15 no-answer/perturbation queries: BM25 zero-hit rate **0.4**,
dense **0.0** — dense *never* returns an empty result by construction. In an
aviation-maintenance context, confidently returning parts data for a
nonexistent part number is the dangerous failure, and no embedding upgrade
fixes it: refusal must come from the lexical arm (this is what keeps BM25 in
the hybrid architecture even while dense wins every ranking metric) and from
the Day 5 fail-closed answer layer.

## 3. The MiniMax case (separate note, measured 2026-07-16)

The broadest "dense loses" instance of the day was provider-specific:
embo-01's length bias inverted relevance rankings *on ordinary procedural
queries* (correct chunk ranked 31/35). Root-caused and documented in
[day4-embedding-length-bias.md](day4-embedding-length-bias.md); resolved by
the bake-off (provider replaced, MiniMax kept as the ablation contrast row).

## 4. Ablation readings that need their footnotes (for the README + red team)

- **hybrid (0.910 R@5) scores BELOW pure dense (0.985)**: when one arm is much
  stronger, RRF lets the weaker arm's noise displace top dense hits. Fusion
  is not free insurance — at this corpus/model pairing its value is the
  refusal behavior and identifier hard-matching it retains, not the ranking
  lift. Reported as measured; not hidden.
- **rerank Recall@5 (0.985, post-fix) > hybrid Recall@5 (0.910)** does *not*
  violate the pre-committed self-check ("rerank cannot raise Recall"): the
  rule holds at the candidate-pool depth (20), where rerank creates no new
  candidates. Within-pool reordering can legitimately lift a relevant doc
  from fused rank 7 into the top-5. At pool depth, hybrid R@10 = rerank
  R@10 = 0.970 — the invariant holds.
- **Numbers above are post-fix**: the first ablation run scored the reranker
  against identifier-augmented text (self-review finding; BM25's scoring
  corpus had leaked into the returned documents). Fixing document hygiene
  changed ONLY the rerank row (R@5 0.970 → 0.985, MRR 0.861 → 0.851) —
  bm25/dense/hybrid are rank-based and were unaffected. Honest drift, both
  runs preserved in the eval JSON.
- **BM25 p50 = 0.0 ms** is sub-millisecond in-process scoring over 43 chunks
  rounding down; dense/hybrid p50 (~55 ms) is dominated by Qwen3-8B query
  encoding on MPS; rerank p50 (~214 ms) adds the cross-encoder pass over 20
  candidates. Toy-scale numbers, not serving claims (INV-7).

## 5. Post-adjudication update (2026-07-16, second re-run)

The numbers in §4 predate two events: Yi Xin's completion of the golden-set
review (anchors edited — bm25 R@5 moved 0.821 → 0.828) and the red-team #6
fusion-guard fix. Current authoritative numbers live in
`eval/results/day4-ablation.json` and the README tables generated from it.
Notable post-fix changes: hybrid R@10 reached 1.00 (the guard stopped the
lexical arm voting for garbage), hybrid-rerank reached R@5 0.99, and the
identifier category under rerank reached 1.00. The zero-hit conclusion is
unchanged — and sharpened: no dense-bearing mode can refuse by construction;
only pure BM25 refuses today.
