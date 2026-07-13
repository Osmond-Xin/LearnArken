# Day N Red-Team Review & Adjudication

## Part 1: Red-Team Findings (non-implementing model, read-only review)

- Review target: <branch / diff range>
- Reviewing model: <Codex / Gemini / MiniMax — must differ from the implementer>
- Inputs: diff + the day's SPEC + constitution

| # | Grade | Finding | Location | Suggestion |
| --- | --- | --- | --- | --- |
| 1 | P0/P1/P2 | <description; cite INV ID if an invariant is violated> | file:line | <suggestion> |

**Red-team verdict**: SHIP / REVIEW_NEEDED / DO_NOT_MERGE

---

## Part 2: My Adjudication (human-written, non-delegable — INV-6)

| # | Ruling | Rationale (one sentence) |
| --- | --- | --- |
| 1 | accept / reject | <why> |

**Number re-run record** (every number the red team reported, re-run by me):

- <command> → <my re-run result> → matches red-team report / mismatch (explain)

**Final decision**: merge / rework (scope: …)
