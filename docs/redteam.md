# Red-Team Review Recipes

> Reused from a workflow validated in another personal project. Iron rules
> (constitution INV-6): **red teams read but never write; every number a red
> team reports is re-run by me before merge.**

## Which Mode When

| Mode | Applies to | Cost |
| --- | --- | --- |
| Light cross-review | Default, every day | One round |
| Heavy adversarial loop | Day 4 / 5 / 8 (nodes with numeric conclusions) | Multiple rounds until convergence |

## Light: Cross-Review

1. After implementation is done and CI is green, take
   `git diff main...<feature-branch>`;
2. Hand it to a **non-implementing** model (Codex or Gemini; never Claude when
   Claude implemented). Input = diff + the day's SPEC + `docs/constitution.md`;
3. Require output: P0 (must fix) / P1 (should fix) / P2 (may fix) findings,
   citing INV IDs for invariant violations, ending with a verdict:
   SHIP / REVIEW_NEEDED / DO_NOT_MERGE;
4. Findings go into the first half of `docs/reviews/dayN.md`;
5. I adjudicate each finding (accept/reject + one-sentence rationale) in the
   second half.

Inside Claude Code, the `adversarial-review` skills trigger this directly
(coding-adversarial-review for code, adversarial-plan-review for designs).

## Heavy: Producer → Challenger → Reviser

Used to attack **the evaluation methodology itself** (leakage? seeds? sample
size? metric definitions?):

1. **Producer** (implementer) submits: implementation + eval script + numeric
   conclusions;
2. **Challenger** (non-implementing model) attacks: evaluation-design flaws,
   suspicious numbers, reproduction obstacles — graded findings;
3. **Reviser** (implementer) responds item by item: fix, or rebut with
   evidence;
4. Loop 2–3 until the Challenger produces no new P0/P1;
5. All rounds are recorded in `docs/reviews/dayN.md`; I adjudicate the final
   state and re-run every number.

## Red-Team Prompt Skeleton (light mode)

```text
You are a read-only red-team reviewer. You may not submit code; output findings only.
Review target: <diff>
Today's SPEC: <contents of docs/specs/dayN.md>
Project invariants: <contents of docs/constitution.md>
Requirements:
1. Grade findings P0/P1/P2. P0 = violates an invariant or produces a wrong conclusion;
2. Each finding: location (file:line) + a one-sentence fix suggestion;
3. If a finding involves an invariant, cite the INV ID;
4. End with a verdict: SHIP / REVIEW_NEEDED / DO_NOT_MERGE, with a one-sentence reason.
```
