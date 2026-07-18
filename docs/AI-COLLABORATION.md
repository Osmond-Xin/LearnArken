# AI-COLLABORATION — how this repository is built

> **What this is.** This repo is built AI-first, on purpose. The implementation
> is largely AI-written; the **judgment** — what to build, whether a red-team
> finding is real, whether a number reproduces — is human-owned and left as an
> auditable trail. This document is the map to that trail, and the definition of
> the terms it uses.
>
> **Provenance.** AI-generated (Day 9, 2026-07-18), pending human review. The
> authority for every rule referenced here is [CLAUDE.md](../CLAUDE.md) and
> [docs/constitution.md](constitution.md) (INV-1 – INV-8); on conflict the
> constitution wins.

## The daily cycle (seven steps)

Each day is one node, one branch, one PR, one tag. The fixed steps:

1. **Learn** — 研→读→扫: a deep-research report ([docs/gemini-deepresearch/](gemini-deepresearch/)),
   the day's tutorial, and an AI-written unknowns scan ([docs/research/](research/)).
2. **Spec (human)** — the **decision layer** (goal, acceptance, out-of-scope, key
   decisions) is human-written ([docs/specs/](specs/)); AI may draft only the
   elaboration layer, labelled `AI-drafted`.
3. **Implement (AI)** — strictly within spec scope, small conventional commits.
4. **Red-team review (independent model)** — a **different** model from the
   implementer reads the diff read-only and reports graded findings
   ([docs/reviews/](reviews/) Part 1).
5. **Adjudicate (human)** — the human accepts/rejects each finding with rationale
   ([docs/reviews/](reviews/) Part 2) and **re-runs every number** a red team reports.
6. **Verify** — acceptance criteria checked; tests + lint green.
7. **Journal (human)** — what the AI got wrong, how it was caught, which AI
   proposal was overruled ([docs/journal/](journal/)).

## Worked examples (read these, don't take my word)

- **A spec decision layer**: [docs/specs/day8.md](specs/day8.md) — the "Key
  Decisions" block is transcribed human ruling; interfaces are AI-drafted and
  labelled. Note the `【待 Yi Xin 定】` markers where AI explicitly refused to decide.
- **A red-team record + adjudication**: [docs/reviews/day8.md](reviews/day8.md) —
  Part 1 is the independent model's findings (`DO_NOT_MERGE`, 13 items); Part 2 is
  the human's finding-by-finding adjudication. The implementer never self-reviews.
- **A distilled design discussion**: [docs/discussions/day9.md](discussions/day9.md)
  — question → options → decision → rationale, AI-distilled and labelled.

## What must be human (the unforgeable output)

These are never AI-ghostwritten (INV-6):

- **SPEC decision layer** — goal, acceptance criteria, out-of-scope, key decisions.
- **Adjudication** — accept/reject of each red-team finding, with rationale.
- **Learning journal** — the honest post-mortem.
- **Number re-run** — every benchmark a red team cites is re-run by the human
  before merge.

Why these and not the code: an implementer who does not understand the system
**cannot** tell a true red-team finding from a false one, cannot cut a spec's
scope defensibly, and cannot reproduce a number on demand. The adjudication trail
is therefore a **proof of understanding** that AI-generated code volume is not.
This is the skill the workflow demonstrates: turning a vague goal into an
AI-executable spec, orchestrating adversaries for quality, and holding final
judgment.

## `CLAUDE.md` is this repo's `agents.md`

The industry `agents.md` convention is an "agent behaviour constitution" —
code-style, test commands, environment rules a coding agent must follow.
[CLAUDE.md](../CLAUDE.md) + [docs/constitution.md](constitution.md) already play
that role here (role boundaries, the automatic red-team gate, the daily cycle,
INV-1 – INV-8). We name that role rather than add a duplicate `AGENTS.md` file.
The three audiences stay distinct: **[README](../README.md)** for humans,
**[llms.txt](../llms.txt)** as a static map for external retrieval agents, and
**CLAUDE.md** as the behaviour constitution for agents working *inside* the repo.

## Supply-chain transparency

Every commit carrying substantive AI-written code uses a `Co-Authored-By`
trailer — honest provenance, checkable with `git log --grep='Co-Authored-By'`.
Hiding AI involvement is both dishonest and fragile against provenance tooling;
radical transparency is the position here.

## Adversarial validation — term card

The red-team workflow above is **adversarial validation**. The term carries two
distinct meanings; this project uses the second and states so explicitly (the
job-search materials use the same governed-AI sense — see private dossier).

- **Traditional ML sense — distribution-shift detection.** An offline diagnostic:
  mix the train and test sets, label them by origin, train a classifier; if it can
  tell them apart, the two distributions differ and generalisation is at risk. A
  *data-science* technique run before training.
- **Governed-AI sense (2025–2026) — cognitive/executive separation.** A defence
  *architecture*. Assuming the reasoning agent may be compromised (e.g. by prompt
  injection), an independent, stateless validation layer that shares no trust with
  the agent sits between "thinking" and "acting", screening every consequential
  action with **graduated determinism** (static rules → non-LLM classifier →
  human-in-the-loop). The model may propose; the runtime holds the authorization
  boundary.

**The two differ in stage, threat model, and implementation** — one is a
pre-training data check, the other a runtime safety architecture. Do not conflate
them.

### How this project practises the governed-AI sense (three layers)

1. **Critic attacks the answer** (Day 5) — grounded-QA fail-closed gates: an
   answer either cites verifiable evidence or explicitly refuses (INV-4). See
   [docs/specs/day5.md](specs/day5.md).
2. **Attack the evaluation** (Day 8) — two heterogeneous judges (never the
   generator's model family), intersection verdicts, and Cohen's κ calibration
   against human labels; the evaluator itself is evaluated. See
   [docs/EVIDENCE.md](EVIDENCE.md) (adversarial-evaluation rows).
3. **Red-team attacks the code** (every day) — the cross-host
   `coding-adversarial-review` runs on each day's diff before merge, routed to a
   model that is *not* the implementer. See [docs/reviews/](reviews/).

The convergence rule is adversarial, not neutral: a review stops only when no new
high-severity finding is produced — an attacker with a stopping condition, not a
scorer.
