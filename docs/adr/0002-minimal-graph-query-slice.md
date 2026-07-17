# ADR-0002: Minimal RDF/SPARQL dependency-graph query pulled into scope (Day 9)

- Status: accepted — **amended 2026-07-16 (same day, Day 5 opening ruling)**:
  the *first half* of the slice moves forward to **Day 5** — index-time graph
  sync into Neo4j (DM nodes, dmRef/ICN edges) + tutorial 06 §9 interface ③
  (graph facts injected as structured context in `query`). The *dependency
  query class* ("which procedures are affected if DM X is superseded?",
  interface ①-style) **stays at Day 9** as originally decided. See
  docs/specs/day5.md Q1 and docs/discussions/day5.md D2.
- Date: 2026-07-16
- Deciders: Yi Xin (decision), Claude implementer (drafting — **AI-drafted
  record of a human ruling**; see docs/discussions/day4.md D18)
- Related: execution-plan.md Day 4 复评点 (🔁), tutorials/06 §9

## Context

The execution plan set a review point at Day 4 closeout: re-evaluate whether
a **minimal RDF/SPARQL dependency-graph query** should move from *Planned*
(out of slice) into scope, attached around Day 9. Knowledge-Graph RAG
appears in the *title* of a target role (private dossier) — the only
title-level keyword gap in the current slice. The groundwork already exists:
the Neo4j container runs (empty), every chunk carries graph hooks
(`outbound_dm_refs`, `icn_refs`), and tutorial 06 §9 defines three
graph × RAG combination interfaces.

## Decision

**Pull the minimal slice in, attached to Day 9** (evidence-chain day). Scope
is deliberately small: load the dmRef/ICN dependency graph from the chunk
hooks, answer one class of dependency query (e.g. "which procedures are
affected if DM X is superseded?"), and wire it as *one* of tutorial 06 §9's
combination interfaces next to the existing retrieval — not a full
knowledge-graph platform (RDF/SPARQL 全量图谱 stays out of slice).

Rationale (Yi Xin): closes the only title-level JD keyword gap at marginal
cost, because the decision cost lands today (this ADR) and the
implementation cost lands inside Day 9, whose evidence-chain theme the graph
query naturally serves.

## Consequences

- execution-plan.md Day 9 gains the minimal graph-query slice as a listed
  deliverable; the Day 4 复评点 is resolved and marked done.
- The Day 9 spec decision layer (human-written, that day) still owns the
  concrete scope cut; this ADR fixes only *that it is in scope*.
- Risk watch: INV-8 — if Day 9 overruns, the graph slice is the first item
  cut back to a documented design sketch, per the slippage rules.
