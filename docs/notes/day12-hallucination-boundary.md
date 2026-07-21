# Open topic — where is the hallucination boundary, and how to tier it?

> Raised by Yi Xin (2026-07-20), recorded for development. AI-distilled from the
> discussion; **not a decided design** — a topic to develop, likely a later day.

## The observation (recorded verbatim from the session)

The Day 12 free-text grounding gate
([engine._ungrounded_figure_tokens](../../src/learnarken/answer/engine.py)) is
**fail-safe but occasionally over-refuses**: a figure-only-cited answer is
refused if it uses any content word outside the cited chunk + the question, so a
legitimately-phrased answer with extra vocabulary can be refused. This matches
the project priority "宁可过度拒答，不放过幻觉" (prefer over-refusal to letting a
hallucination through), and it is characterised honestly in
[eval/results/day12-multimodal.json](../../eval/results/day12-multimodal.json) —
**not** dressed up as "zero false-refusals".

## Yi Xin's framing: the boundary is not binary — tier it by consequence

The current gate treats every ungrounded token identically (block). But **not all
fabrications carry the same risk**:

- **Low-stakes / tolerable-ish** — e.g. getting a **colour** wrong. A cosmetic
  descriptive attribute; a wrong answer is misleading but not directly dangerous.
- **Safety-critical / never acceptable** — e.g. getting a **torque** value,
  **part number**, **dimension**, **pressure/temperature**, or **step sequence**
  wrong. A fabricated value here can cause real harm on a maintenance floor.

So the right design is probably a **configuration table** mapping attribute
categories → policy, e.g.:

| category (examples) | on ungrounded assertion |
| --- | --- |
| safety-critical: torque, part number, dimension, pressure, temperature, sequence | **hard refuse** (never let through) |
| descriptive: colour, finish, generic shape | softer: allow-with-flag, or lower-priority refuse, or a "not stated in the figure" hedge |
| scaffolding / structural words | ignore (as today) |

This would **narrow the over-refusal** (stop blocking benign descriptive
phrasing) while keeping the **hard block on dangerous values** — a better
precision/safety balance than today's blunt gate.

## Why this is non-trivial (what to work through when developed)

- **Category detection is itself a classification problem** — mapping an answer's
  tokens to "torque-like" vs "colour-like" is easy for patterned values
  (numbers+units, part-number regex) but fuzzy for free-text nouns. A curated
  vocabulary/regex table per category is the deterministic start; an LLM/NER
  classifier is the fuzzy extension (with its own hallucination risk — keep the
  safety-critical tier deterministic).
- **Config provenance (INV-5)** — the table becomes a checked-in artifact; which
  category is "safety-critical" is a **human** decision (like a BREX rule), not
  AI-invented. It should live beside the constitution/validation rules.
- **Interaction with the answer contract** — a "descriptive, allow-with-flag"
  outcome is a THIRD outcome beyond the current answer/refuse binary (Day 5 Q2).
  Introducing it touches the two-outcome invariant — needs a decision-layer call.
- **Evaluation** — the golden set would need conflict/fabrication traps per
  category to measure the tiered policy honestly (k/n per category).

## Status

Roadmap / future-day topic. Today's blunt gate stays (it is safe); this note is
the pointer for when the tiered boundary is designed. See also the honest
over-refusal characterisation in the eval results and
[docs/reviews/day12.md](../reviews/day12.md) R2-P1a.
