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
