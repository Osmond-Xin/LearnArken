# LearnArken

**A standards-aware technical-publication intelligence platform for aviation
(S1000D), built AI-first: human-written specs, AI implementation, adversarial
red-team review, human adjudication.**

*[中文版 / Chinese version](README.zh-CN.md)*

LearnArken is a portfolio project with a deliberate second purpose: to
demonstrate how an engineer in 2026 ships software by **writing specs and
exercising judgment while AI writes the implementation** — with the entire
process auditable by a third party (including a recruiter's AI agent) along
a verifiable evidence chain.

## The Business Scenario This Project Simulates

An aviation MRO (maintenance, repair & overhaul) company equips its engineers
for on-site work: an engineer stands beside an aircraft, laptop open, looking
for the correct maintenance procedure right now. **Latency and recall
therefore outrank everything else** — every benchmark in this project reports
both. The source material is the company's training manuals, delivered as
S1000D-style data packages, in which superseded document versions accumulate
and must be filtered out.

The planned system (built incrementally over the 10 days below — see the
Progress table for what exists today) will provide:

1. **Fail-closed ingestion gate** — every document is validated against S1000D
   structure and basic BREX (Schematron) rules before entering the knowledge
   base. Outdated, non-compliant, or out-of-domain documents (e.g. a
   ship-maintenance module mixed into the aircraft library) are rejected with
   a report of the deviation — never auto-corrected; a human decides;
2. **Cited question answering** — "What preparation is required before replacing
   this part?" Every answer carries source citations; when evidence is
   insufficient the system refuses to answer (fabrication is not acceptable in
   a maintenance domain);
3. **Assisted repair** — for known violations, generate fix suggestions for
   human approval, then automatically re-validate.

**Honesty statement**: the sample data is synthetic S1000D-like XML (with
deliberately injected, enumerated violations); the scale is educational;
distributed behavior is simulated with single-machine multiprocessing, but all
interfaces are designed as if for a real distributed system. All simulation
boundaries and project invariants live in
[docs/constitution.md](docs/constitution.md).

## The AI-First Workflow (This Project's Second Artifact)

One node per day, seven fixed steps: **learn → spec (human-written) →
implement (AI) → red-team review (independent read-only model) →
adjudicate (human, finding by finding) → verify (acceptance criteria) →
ship (tag)**.

Three understanding gates that cannot be faked, all committed to this repo:

| Gate | Evidence | Why it can't be faked |
| --- | --- | --- |
| Spec **decision layer** is human-written (goal, acceptance criteria, scope cuts, key decisions) | [docs/specs/](docs/specs/) | Decomposition and judgment are exposed directly in the writing; AI-drafted elaboration sections are explicitly labeled |
| Adjudications are human-written | [docs/reviews/](docs/reviews/) | You cannot judge red-team findings without understanding the implementation |
| Journals are human-written | [docs/journal/](docs/journal/) | Three fixed questions: what did I learn / where was the AI wrong / what AI proposal did I reject and why |

In addition, the design discussions behind each day's decisions are distilled
into [docs/discussions/](docs/discussions/) — question → options → decision →
rationale — showing how AI proposals were steered, adopted, or rejected in
real working sessions.

Red-team discipline: the reviewing model must differ from the implementing
model, reviews are read-only, and every number a red team reports is re-run by
me before merge. See [docs/redteam.md](docs/redteam.md) and
[docs/execution-plan.md](docs/execution-plan.md).

## Progress (Day 1–10)

| Day | Node | Tag | Status |
| --- | --- | --- | --- |
| 1 | Skeleton, sample packages, project constitution | `v0.1.0` | ✅ 2026-07-13 |
| 2 | Canonical model & validators | `v0.2.0` | ✅ 2026-07-14 |
| 3 | BM25 baseline & retrieval evaluation | `v0.3.0` | ⬜ |
| 4 | Hybrid retrieval & ablation table ⚑ heavy red team | `v0.4.0` | ⬜ |
| 5 | RAG with citations ⚑ heavy red team | `v0.5.0` | ⬜ |
| 6 | API & local demo | `v0.6.0` | ⬜ |
| 7 | Validation-repair agent | `v0.7.0` | ⬜ |
| 8 | Adversarial evaluation: attacking my own RAG ⚑ heavy red team | `v0.8.0` | ⬜ |
| 9 | Evidence chain & machine readability | `v0.9.0` | ⬜ |
| 10 | Deployment & wrap-up | `v1.0.0` | ⬜ |

Benchmark tables, ablations, and adversarial-evaluation results will appear
below this section as the corresponding nodes complete. Every number comes
with a reproduction command — numbers that cannot be reproduced do not enter
this README (invariant INV-5).

### Retrieval benchmark — Day 3 (BM25 × chunking strategy)

Scored against the **human-annotated** golden set
(`eval/golden/day3.jsonl`, 32 queries: 27 answerable + 5 no-answer traps;
relevance judged by Yi Xin — the retrieval-eval red line). Metric priority:
Recall@k leads for RAG (tutorial 02 §4).

| Strategy | Recall@5 | Recall@10 | MRR | nDCG@10 |
| --- | --- | --- | --- | --- |
| structure-aware | 0.93 | 0.93 | 0.84 | 0.86 |
| recursive (control) | 0.85 | 0.89 | 0.79 | 0.82 |

Structure-aware chunking leads on every metric — the empirical form of
tutorial 02's top optimization lever (chunking ≫ k1/b, which is left at
library defaults). Reproduce (fixed seed, versioned golden set):

```bash
learnarken eval retrieval --package samples/package-a --package samples/package-c \
  --golden eval/golden/day3.jsonl
```

## Roadmap (Honest Layering)

- **Implemented**: `inspect` CLI (package summary, JSON output, hardened XML
  parsing); synthetic sample packages a/b/c with enumerated violation manifest
  (VIO-1..8); canonical Pydantic model with structured applicability;
  four-layer validator (well-formedness → project mini-XSD → BREX rules →
  cross-file reference graph) via `validate`; per-DMC query via `dm`
- **Toy-scale**: synthetic sample-package size; single-machine simulation of
  distributed behavior
- **Planned**: SPLADE, ColBERT, RDF/SPARQL knowledge graph, local vLLM serving,
  Rust extensions, GNN, formal verification — see
  [docs/project-design.md](docs/project-design.md)
- **Planned — direct S1000D → graph-database mapping**: real S1000D already
  defines structure and relationships, and industry approaches map the XML
  straight into a graph database (ontology / property-graph), skipping text
  chunking for the relational layer. This project uses traditional RAG
  chunking instead, because of scope and data-access limits (no real S1000D
  content, INV-1); revisited at the Day 4 checkpoint (docs/discussions/day3.md
  D5)

## Repository Guide

| Entry | Contents |
| --- | --- |
| [docs/constitution.md](docs/constitution.md) | Business scenario + 8 project invariants (highest authority) |
| [docs/execution-plan.md](docs/execution-plan.md) | 10-day execution plan with daily acceptance criteria |
| [docs/project-design.md](docs/project-design.md) | Full design, JD coverage matrix, milestones |
| [docs/specs/](docs/specs/) · [docs/reviews/](docs/reviews/) · [docs/journal/](docs/journal/) | Daily evidence chain: specs / red team + adjudication / journals |
| [docs/discussions/](docs/discussions/) | Distilled design discussions: question → options → decision → rationale |
| [docs/redteam.md](docs/redteam.md) | Red-team recipes (light cross-review + heavy adversarial loop) |
| [docs/tutorials/00-overview.md](docs/tutorials/00-overview.md) | Zero-background tutorial series (Chinese) |
| [samples/](samples/README.md) | S1000D sample notes and license audit |
| [CLAUDE.md](CLAUDE.md) | Operating rules and role boundaries for the AI implementer |

Some learning materials (tutorials, journals) are written in Chinese; all
outward-facing artifacts — this README, the constitution, evidence maps, and
benchmark reports — are in English.

## Quickstart

```bash
uv sync --locked                               # Python 3.12 + deps (needs uv)
make test                                      # ruff + pytest
uv run learnarken inspect samples/package-a    # summarize a sample package
uv run learnarken validate samples/package-b   # four-layer validation findings
```

Validation results are only claimed for locked installs (`uv.lock`); CI runs
`uv sync --locked` so parser behavior cannot drift with dependency versions.
