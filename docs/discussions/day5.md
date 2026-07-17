# Day 5 — Design Discussions (distilled)

> AI-distilled from working sessions (Claude, implementer), human-reviewed.
> Same-day rule: every decision-producing discussion lands here in-session.

## D1. Day 5 opening rulings: query CLI, MiniMax-M3, mandatory citations, graph sync

- **Context**: Day 4 closed (v0.4.0, 2026-07-16); Yi Xin opened Day 5 in the
  same session with the decision layer, transcribed into docs/specs/day5.md.
- **Decisions** (transcribed):
  1. New `learnarken query "<question>"` CLI.
  2. Answer LLM = **MiniMax-M3** — supersedes the execution plan's "Claude
     API" line for Day 5. Config = the four `MINIMAX_*` vars (values on
     hand). Note the boundary: Day 4's adjudication removed MiniMax as an
     *embedding* provider; generation was not covered by that ruling.
  3. Every answer traceable: chunk ID + DMC + XPath, mandatory.
  4. Unanswerable ⇒ fixed refusal placeholder ("I don't know" 类), INV-4.
  5. Tests: golden questions with citation verification, AND no-answer
     questions asserted to hit the placeholder.
  6. **Graph sync + combined query**: indexing syncs Neo4j; `query`
     combines vector and graph — pulls the minimal graph slice forward
     from Day 9 (ADR-0002 to be amended per the Q1 ruling).
  7. Post-implementation review is the standing automatic gate (Day 5 is a
     ⚑ heavy node).
- **Process note**: 研 was already in the archive (all ten DR reports
  generated 2026-07-15); 扫 is docs/research/day5-unknowns.md; spec open
  questions Q1–Q4 put to Yi Xin before implementation, per role boundaries.
