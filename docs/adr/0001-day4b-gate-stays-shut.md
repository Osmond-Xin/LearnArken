# ADR-0001: Day 4b (SPLADE / ColBERT) gate stays shut

- Status: accepted
- Date: 2026-07-16
- Deciders: Yi Xin (decision), Claude implementer (drafting — **AI-drafted
  record of a human ruling**; see docs/discussions/day4.md D18)
- Related: D5 (gate design), D7 (engine-coupling tension), D15 (gate
  reading), docs/specs/day4.md decision 8

## Context

D5 split Day 4 into 4a (four-mode ablation, shipped) and 4b (SPLADE +
ColBERT), gated on a *specific* gap in 4a's per-category table: synonym /
paraphrase queries still losing would open the SPLADE gate; identifier or
fine-grained queries still losing would open the ColBERT gate. The gate
reading had to wait for the human-reviewed golden set and the re-issued
tables (red-team day4 #1–#3).

## Decision

**Both gates stay shut; Day 4b is not built.** On the reviewed golden set
(answerable n=67, artifact `eval/results/day4-ablation.json`):

- **SPLADE gate**: the paraphrase gap is closed by the dense default —
  paraphrase Recall@5 went BM25 0.38 → dense **1.00**. SPLADE treats
  vocabulary mismatch; there is no vocabulary mismatch left to treat.
- **ColBERT gate**: identifier / fine-grained queries are not losing —
  dense 0.86 vs BM25 0.71 identifier Recall@5, and hybrid-rerank reaches
  1.00 there. The textbook "dense loses identifiers" failure inverted at
  this scale/model.

A learning-value override was considered and declined (Yi Xin, closeout
session): BGE-M3's three-representation route stays documented (D13, the
handoff §3) but unbuilt; INV-8's two-calendar-day cap on Day 4 is already
fully used, and the project's own methodology — "用数字开门", let the
ablation decide — would be inverted by shipping techniques the evidence
just rejected.

## Pre-ruled position if the gate ever opens

The D7 tension is resolved in advance: **MaxSim would run Python-side over
multi-vectors stored in Vespa**, keeping the Q3 ruling (the engine is a
dense store; ranking logic stays portable) — accepting that this forfeits
Vespa's ColBERT-native selling point, in which case the Day 3 D2
engine-selection rationale must be restated. Recorded so a future session
does not re-litigate it from scratch.

## Consequences

- README Roadmap: SPLADE/ColBERT are marked "considered and declined on
  evidence (Day 4b, this ADR)" rather than *Planned*.
- execution-plan.md carries the 4a/4b split with 4b closed by this ADR.
- Revisit trigger: a corpus/golden-set change that re-opens a per-category
  gap the current modes cannot close (e.g. paraphrase Recall@5 dropping
  materially below dense's current 1.00 at larger scale).
