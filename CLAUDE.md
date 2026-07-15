# LearnArken — Operating Rules for the AI Implementer

This file governs AI coding assistants working in this repository. The
superior authority is [docs/constitution.md](docs/constitution.md)
(INV-1 – INV-8); on conflict, the constitution wins.

## Role Boundaries (most important)

- **Precondition for implementing**: the day's `docs/specs/dayN.md` exists with
  a human-written **decision layer** (goal, acceptance criteria, out-of-scope,
  key decisions). If it is missing or ambiguous — **ask questions; do not
  ghostwrite decisions; do not guess**.
- **Layered spec authorship (INV-6)**: AI may draft the spec's **elaboration
  layer** (interface details, formats) — always under an explicit `AI-drafted`
  label, effective only after human review. AI never writes the decision layer.
- **AI never touches**: `docs/journal/` and the adjudication half of
  `docs/reviews/`. AI may draft the red-team half of `docs/reviews/` (produced
  by a non-implementing model) and may distill working discussions into
  `docs/discussions/` (labeled, human-reviewed).
- **Red team is read-only**: when acting as red team, output findings only;
  never change code.
- **Same-day discussion memo (mandatory)**: every working discussion that
  produces decisions MUST be distilled into `docs/discussions/dayN.md` the
  same day, in the same session, immediately after the decisions are made —
  not deferred to day-end. It is part of the day's deliverable checklist
  (spec + discussions + red-team half + implementation + tests). AI-distilled,
  labeled, pending human review. (Rule added 2026-07-14 after two late
  filings.)

## Implementation Discipline

- Implement strictly within the day's SPEC scope; what the SPEC doesn't say,
  don't do (including "drive-by improvements").
- Small commits, conventional commits; AI-generated commits carry a
  `Co-Authored-By` trailer — honest provenance.
- One feature branch per day → one PR → squash merge; the PR description links
  the SPEC and states how to verify.
- Distribution-related code must pass the INV-2 check: sharding behind an
  abstraction, no shared-memory shortcuts, idempotent writes.
- QA/generation paths must fail closed (INV-4): insufficient evidence ⇒ refuse.

## Technical Baseline

- Python 3.12, ruff + pytest + pre-commit, type annotations (Pydantic models).
- Tests ship in the same PR as the implementation; benchmark numbers use fixed
  random seeds (INV-5).
- Sample data is synthetic XML only (INV-1). When real structure is needed as
  reference, consult the local `samples/s1000d/` files (non-committed files are
  reference-only; never copy their content).

## Directory Conventions

```text
docs/specs/dayN.md      Daily SPEC (decision layer human-written; elaboration may be AI-drafted, labeled)
docs/discussions/dayN.md Distilled design discussions (AI-distilled, human-reviewed)
docs/reviews/dayN.md    Red-team findings (AI) + adjudication (human-written)
docs/journal/dayN.md    Learning journal (human-written)
docs/adr/               Architecture decision records
samples/package-a       Legal synthetic sample package
samples/package-b       Synthetic package with known violations (list: constitution §4)
```
