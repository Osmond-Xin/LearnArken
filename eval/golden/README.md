# Golden set for retrieval evaluation (Day 3)

This directory holds the versioned relevance judgments that
`learnarken eval retrieval` scores against. Two files, two authorship rules.

## `day3.candidates.jsonl` — AI-drafted candidates (NOT authoritative)

24 candidate queries drafted by the AI implementer across the categories the
spec requires: procedural how-tos, identifier / part-number lookups,
warning/hazard, fault isolation, descriptive, applicability-conditional,
cross-reference, identifier perturbation, and no-answer traps. Every line
carries `"ai_suggested": true` and a proposed `relevant` anchor.

**These anchors are suggestions, not judgments.** They are a scaffold to speed
up annotation — the AI drafted the questions and guessed the answers; a human
must verify or correct each one.

## `day3.jsonl` — the human-annotated golden set (authoritative)

**Produced by Yi Xin, not the AI** (this is the retrieval-evaluation red line:
the judgment of what is relevant is where the interview value and the
evaluation's credibility live). Workflow:

1. Review each candidate in `day3.candidates.jsonl`; keep, fix the anchor, or
   drop it.
2. Add your own queries until there are ≥ 30, keeping the category mix.
3. Save the curated set as `day3.jsonl` (drop the `ai_suggested` / `category`
   helper fields, or keep them — the loader ignores unknown keys).

Until `day3.jsonl` exists, run against the candidates explicitly:

```bash
learnarken eval retrieval --package samples/package-a --package samples/package-c \
  --golden eval/golden/day3.candidates.jsonl
```

The README benchmark table and the `v0.3.0` release-notes numbers must be
generated from `day3.jsonl` (the human set), not from the candidates.

## Line format

```json
{"query_id": "Q001", "query": "How do I discharge the accumulator safely?",
 "relevant": [{"dmc": "DMC-LA100-…", "source_path": "…/mainProcedure/proceduralStep[2]"}]}
```

Relevance is annotated at the `(dmc, source_path)` **anchor** level, where
`source_path` is the XPath of a structure element (get it from
`learnarken chunk <pkg> --json`). One annotation serves both chunking
strategies: a chunk counts relevant when it shares the DMC and its text
contains — or is contained by — the anchor element's text. A no-answer query
has `"relevant": []`.

## `day8-adversarial.jsonl` — adversarial evaluation set (Day 8)

32 adversarial queries over the LA100 corpus, spanning the four attack classes
(DR §3): **rewrite-invariance** (colloquial / cross-language / de-punctuated
restatements → must still answer), **perturbation** (part-number / torque /
measurement / DMC fuzzing → must refuse or correct, never affirm the false
value), **no-answer** (absent systems, false premises, world-knowledge bait →
must refuse), and **cross-doc** (aggregation traps, code ambiguity, attribute
grafting → must disambiguate, not conflate).

**Authorship (SPEC day8 Decision 1):** these are **AI-drafted, pending Yi Xin's
review** — every row carries `"ai_drafted": true`. Unlike the retrieval golden,
Day 8's decision layer delegates the adversarial *design* to the AI (Yi Xin
reviews); the **groundedness anchor labels** used for Cohen's Kappa calibration
remain human-owned. **Anti-leak (Decision 9):** this file must never be pasted
into the answer-generation prompt / few-shot — a test asserts the isolation.

Row schema: `id`, `category`, `question`, `expected_behavior`
(`answer|refuse|clarify`), `attack_note`, and `anchor`
(`must_cite_dmc` / `must_state` for answerable; `must_not_state` for
perturbation/trap rows).
