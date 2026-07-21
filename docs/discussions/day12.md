# Day 12 design discussions — multimodal ingest & QA

> **AI-distilled** (Claude, 2026-07-20, pending human review). Distills the
> decisions made in the Day 12 working session. Scope decision came earlier
> ([day11-13-planning.md](day11-13-planning.md) Decision 2); this memo records
> what was decided *this* day. Authority is the SPEC decision layer
> ([docs/specs/day12.md](../specs/day12.md)) and the review
> ([docs/reviews/day12.md](../reviews/day12.md)); this is a labelled summary.

## Decisions

1. **VLM provider = reuse the existing MiniMax proxy (no new key).** A live probe
   settled the day's biggest unknown: the proxy's `/v1/models` lists no VL model,
   **but** it accepts the OpenAI multimodal `image_url` format and genuinely reads
   pixels (rendered `AR7429` read back byte-exact 2/3 runs). The channel is
   **unstable at temperature 0** (featureless images / intermittent calls return
   empty) → every VLM call is fail-closed with two stop conditions: bounded retry
   on flaky misses, terminal on subscription `429`. (Yi Xin: "首先看 MiniMax 是否
   有我们需要的服务"; resolves scan T4.)

2. **Second-look = multi-sample consensus, NOT a single call.** Yi Xin **corrected**
   the scan's "single call / defer to Roadmap" recommendation: a single read of an
   unreliable channel is not trusted. Query-time second-look issues multiple
   independent VLM calls, accepts a reading only on consensus + deterministic
   anchor corroboration, and refuses (G15) on divergence / non-convergence / 429.
   Inference-time self-consistency — the Day 8 repeat-test discipline moved from
   evaluation into reading.

3. **Visual fail-closed gate named G15 (not "Gate 4").** The interview 拦截塔
   catalog already uses G4 (ingest L0–L3 validation) through G14 (demo_guard);
   the new answer-layer visual-refusal gate takes the next free number **G15**
   (`figure-out-of-description`), to avoid collision. (Yi Xin: "改成新的".)

4. **Image-text conflict: mechanical yes, semantic no; Class B = deliberate
   synthetic conflict (option a).** Hotspot-set diff at ingest is mechanical and
   deterministic; semantic conflict is NOT auto-detected at toy scale (Decision
   3b). To test the boundary honestly, a deliberate synthetic conflict was
   authored (battery DM prose says housing part `LA-24-9002-3` while the figure's
   verified hotspot says `LA-24-5002-6`). **Emergent result:** grounded QA (every
   claim must cite) makes the system **present both cited sources** rather than
   assert one — a pass by "not force one side", not semantic detection.

5. **Indexed figure text is declared-grounded only (VLM free-text not indexed).**
   Red-team-driven tightening: the retrieval chunk uses the authoritative DM XML
   hotspot mapping; the VLM `summary`/`safety_warnings` stay in the audit record,
   never indexed as authoritative. Removes unverified VLM text from the corpus.
   (Confirmed by Yi Xin, review Part 2.)

6. **Old-golden regression: measure the production path first, then accept.**
   Yi Xin **corrected** deciding on the BM25 worst case (R@5 −0.022, MRR −0.033):
   measure the `hybrid-rerank` (production) delta first. Measured: **Recall and
   zero-hit unchanged** (the reranker recovers every text answer BM25 shuffled),
   only a small MRR/nDCG rank shuffle → accepted.

## Red-team (two rounds, all fixed)

- Round 1 (completed slice): 4 P1 + 4 P2 + 2 P3 — all fixed. Biggest: figure
  chunks were not in the query/verify corpus → a single shared `corpus_chunks`
  builder now serves index, query, verification, ablation.
- Round 2 (full diff, Codex **DO_NOT_MERGE**): 2 P1 + 5 P2 + 2 P3 — all fixed.
  R2-P1a (G15 bypass by a fabricated concrete value) → deterministic
  part-number/measurement guard; R2-P1b (chunk id didn't bind label/part text)
  → declared-mapping digest folded into the chunk id + re-verified.
- **Free-text fabrication — RULED, not deferred (Yi Xin 2026-07-20).** I first
  disclosed free-text visual fabrication (a fabricated colour) as a "Day-8
  boundary" to defer. Yi Xin **rejected** the defer: blocking free-text
  hallucination is a KEY purpose of the project and must be caught at citation
  confirmation. The grounding gate now covers **all** content tokens (not just
  part/measurement) — a figure-only-cited answer whose content isn't grounded in
  the cited quote or the question is refused. Lesson: a red-team finding is not
  mine to downgrade to "out of scope".

## Honesty notes (interview-usable)

- Second-look adds **no answerable content** at toy scale (the description is the
  complete verified declared set) — its value is the **fail-closed consensus
  guarantee**, like Day 11's honest null result. Answering from a re-read for
  genuinely lossy real figures is Roadmap.
- A1 (an answerable figure question) **occasionally over-refuses** (fail-safe):
  the G15 trigger can't tell an LLM `is_answerable=false` flake from a genuine
  out-of-description question, so it errs toward refusal, never fabrication.
  Reported honestly (eval characterization), not tuned away.
- Synthetic-data privilege (INV-7): description-quality / resolution numbers were
  measured on self-drawn wireframes and do **not** extrapolate to real scans.
