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
- **Red-team gate is automatic (mandatory)**: as soon as the day's
  implementation is green (tests + lint pass) and **before** proposing a
  commit or merge, the implementer MUST launch the cross-host
  `coding-adversarial-review` on the day's diff and write the findings to
  `docs/reviews/dayN.md` Part 1 — **without being asked**. The review is
  routed to the non-implementing model (Codex when the host is Claude Code);
  the implementer never self-reviews. Adjudication (Part 2: accept/reject +
  rationale, and re-running any red-team number) is the human's, never
  drafted by AI. This is step 4 of the daily cycle and does not wait for a
  prompt. (Rule added 2026-07-14 after the Day 3 review had to be started
  manually.)
- **Same-day discussion memo (mandatory)**: every working discussion that
  produces decisions MUST be distilled into `docs/discussions/dayN.md` the
  same day, in the same session, immediately after the decisions are made —
  not deferred to day-end. It is part of the day's deliverable checklist
  (spec + discussions + red-team half + implementation + tests). AI-distilled,
  labeled, pending human review. (Rule added 2026-07-14 after two late
  filings.)
- **Daily deep-research learning step (mandatory, from Day 4 / 2026-07-15)**:
  step 1 of the daily cycle is 研→读→扫 (research → read → scan):
  (a) **研** — a Chinese deep-research report on the day's domain, archived
  under `docs/gemini-deepresearch/` (all ten days were generated 2026-07-15;
  reviewed in `docs/gemini-deepresearch/REVIEW.md`). Primary channel: the
  human pastes the day's prepared prompt (library:
  `docs/tutorials/deep-research-prompts.md`) into the Gemini app's official
  Deep Research, downloads the report, and archives it with a source line. Automated alternative: the Interactions API
  (`tools/deep_research.py`; needs a paid-tier `GEMINI_API_KEY`). Fallback:
  `agy` (Antigravity CLI) + Gemini 3.1 Pro single-pass web research —
  fallback output MUST be labeled "simulated, not official Deep Research".
  The defunct `gemini` CLI is not a channel (personal free tier
  discontinued). If the day's report is missing, ask the human to run it (or
  offer the fallback) — do not silently skip 研.
  (b) **读** — the human reads report + the day's tutorial.
  (c) **扫** — the implementer writes an unknowns scan (blind-spot pass per
  Anthropic's "Finding Your Unknowns" quadrants) plus a deep explanation of
  must-master points, at `docs/research/dayN-unknowns.md`, cross-referencing
  report and tutorial. AI-generated, labeled. This step never substitutes for
  the human-written journal or the spec decision layer. (Rule added
  2026-07-15 at Yi Xin's direction; see docs/discussions/day4.md.)

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
docs/research/dayN-*.md Daily deep-research report + unknowns scan (AI-generated, labeled)
docs/adr/               Architecture decision records
samples/package-a       Legal synthetic sample package
samples/package-b       Synthetic package with known violations (list: constitution §4)
```
