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

| Strategy | Recall@5 | Recall@10 | MRR | nDCG@10 | Zero-hit rate |
| --- | --- | --- | --- | --- | --- |
| structure-aware | 0.93 | 0.93 | 0.80 | 0.83 | 0.40 |
| recursive (control) | 0.85 | 0.89 | 0.79 | 0.80 | 0.40 |

Structure-aware chunking leads on every ranking metric — the empirical form of
tutorial 02's top optimization lever (chunking ≫ k1/b, which is left at
library defaults). The **zero-hit rate** (fraction of the 5 out-of-corpus trap
queries the retriever correctly returns nothing for) is only 0.40 for both:
lexical BM25 alone cannot refuse well, which is exactly what the fail-closed
answer logic (Day 5) and adversarial no-answer evaluation (Day 8) are for —
reported honestly rather than hidden. Reproduce (versioned golden set,
deterministic):

```bash
learnarken eval retrieval   # defaults to package-a + package-c, golden day3.jsonl
```

Day 4 adds the **semantic** strategy (embedding-based breakpoints, chunked by
the default provider): Recall@5 0.81 / MRR 0.74 / nDCG@10 0.75 on the same
golden set — structure-aware still wins, so the Day 4 retrieval ablation runs
on structure chunks (`learnarken eval retrieval --strategy semantic`).

### Embedding-provider bake-off — Day 4 (dense path)

Providers behind one LangChain `Embeddings` interface, exact-cosine ranked,
scored by the same harness on the Day 4 golden set (82 queries, **all
human-reviewed** by 2026-07-16; ranking metrics computed over the 67
answerable ones).

<!-- BEGIN gen:day4-bakeoff -->
| Provider | Recall@5 | Recall@10 | MRR | nDCG@10 |
| --- | --- | --- | --- | --- |
| MiniMax embo-01 (remote) † | 0.50 | 0.68 | 0.36 | 0.43 |
| BGE-M3 (local) | 0.92 | 0.97 | 0.84 | 0.87 |
| **Qwen3-Embedding-8B (local)** | **0.99** | **1.00** | **0.87** | **0.90** |
<!-- END gen:day4-bakeoff -->

**Qwen3-8B wins and is the sole dense provider** — the Day 4 adjudication
removed the MiniMax client from the architecture after its embeddings showed a
measured **length bias strong enough to invert relevance** (adding *relevant*
words to a chunk lowers its similarity; an irrelevant short chunk outscores
the correct long one) — root-caused against a wire-identical LangChain request
and a healthy local control, see
[docs/notes/day4-embedding-length-bias.md](docs/notes/day4-embedding-length-bias.md).

† historical row: measured 2026-07-16 pre-review on the then-current golden
set, reproducible at commit `b414fa4` (client removed since). BGE-M3/Qwen3
rows re-measured on the reviewed set. Reproduce:
`uv run python tools/dense_bakeoff.py`.

### Retrieval-mode ablation — Day 4 (BM25 × dense × hybrid × rerank)

Same golden set, structure chunks, exact `nearestNeighbor` (no ANN confound at
43 chunks), RRF fusion via LangChain `EnsembleRetriever` (k=60), rerank via
`bge-reranker-v2-m3` over 20 candidates. The corpus is manifest-verified
before every run (fed chunk-id set must equal the engine's actual contents).

<!-- tables generated by tools/gen_benchmark_tables.py from eval/results/*.json — do not hand-edit -->
<!-- BEGIN gen:day4-ablation -->
Ranking metrics over **answerable n=67**; zero-hit rate over the **15 no-answer traps** (red-team day4 #2 labeling).

| Mode | Recall@5 | Recall@10 | MRR | nDCG@10 | Zero-hit rate | p50 |
| --- | --- | --- | --- | --- | --- | --- |
| bm25 (in-process) | 0.83 | 0.88 | 0.74 | 0.77 | **0.40** | <1 ms |
| dense (Vespa + Qwen3-8B) | **0.99** | **1.00** | **0.87** | **0.90** | 0.00 | 55 ms |
| hybrid (RRF) | 0.93 | **1.00** | 0.85 | 0.88 | 0.00 | 7 ms |
| hybrid + rerank | **0.99** | 0.99 | 0.85 | 0.88 | 0.00 | 126 ms |

Per-category Recall@5 (answerable queries only; *italic* cells have n<3 and are indicative):

| Mode | applicability (n=6) | cross-reference (n=5) | descriptive (n=7) | fault-isolation (n=8) | identifier (n=7) | identifier-perturbation (n=1) | no-answer (n=0) | paraphrase (n=12) | procedural (n=12) | warning (n=9) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | 1.00 | 0.60 | 1.00 | 1.00 | 0.71 | *1.00* | *0.00* | 0.38 | 1.00 | 1.00 |
| dense | 1.00 | 1.00 | 1.00 | 1.00 | 0.86 | *1.00* | *0.00* | 1.00 | 1.00 | 1.00 |
| hybrid | 1.00 | 0.80 | 1.00 | 1.00 | 0.86 | *1.00* | *0.00* | 0.75 | 1.00 | 1.00 |
| hybrid-rerank | 1.00 | 0.80 | 1.00 | 1.00 | 1.00 | *1.00* | *0.00* | 1.00 | 1.00 | 1.00 |

Model snapshots pinned (INV-5): `BAAI/bge-m3 @ 5617a9f61`, `BAAI/bge-reranker-v2-m3 @ 953dc6f6f`, `Qwen/Qwen3-Embedding-8B @ 1d8ad4ca9`.
<!-- END gen:day4-ablation -->


Honest readings (details:
[docs/notes/day4-failure-cases.md](docs/notes/day4-failure-cases.md)):

- **Dense wins every ranking metric at this scale** — an 8B embedder over 43
  chunks even resolves identifier lookups, so the textbook "dense loses on
  identifiers" did not materialize here. Rerank matches dense on Recall@5 and
  is the only mode at 1.00 on identifier-category queries.
- **No dense-bearing mode can refuse**: dense always returns k hits, and
  fusion inherits that — the lexical arm's token-overlap guard keeps it from
  *voting for garbage* (it lifted hybrid's R@10 to 1.00) but cannot make the
  union empty. Refusal (zero-hit 0.40) exists only in pure BM25 today; real
  refusal is the Day 5 fail-closed answer layer's job, measured at Day 8.
- **p50 is cumulative-cache honest**: the dense row includes Qwen3-8B query
  encoding (~55 ms); hybrid reuses those cached query vectors, so its 4 ms is
  the marginal cost of BM25 + fusion; rerank adds the cross-encoder pass
  (~124 ms). Toy-scale numbers, not serving claims (INV-7).

Reproduce: `learnarken index samples/package-a samples/package-c` then
`learnarken eval ablation --json > eval/results/day4-ablation.json` and
`uv run python tools/gen_benchmark_tables.py` (tables are generated from the
artifact — hand-editing them is how red-team finding day4 #1 happened).

## Roadmap (Honest Layering)

- **Implemented**: `inspect` CLI (package summary, JSON output, hardened XML
  parsing); synthetic sample packages a/b/c with enumerated violation manifest
  (VIO-1..8); canonical Pydantic model with structured applicability;
  four-layer validator (well-formedness → project mini-XSD → BREX rules →
  cross-file reference graph) via `validate`; per-DMC query via `dm`;
  identifier-preserving BM25 baseline + human-annotated golden-set evaluation
  (`search`, `eval retrieval`); Vespa-backed dense retrieval (Qwen3-8B,
  revision-pinned), hybrid RRF + cross-encoder rerank, package-scoped search,
  four-mode ablation with generated benchmark tables (`index`, `eval ablation`)
- **Toy-scale**: synthetic sample-package size; single-machine simulation of
  distributed behavior
- **Considered and declined on evidence**: SPLADE and ColBERT — the Day 4b
  gates stayed shut on the reviewed ablation (the paraphrase gap SPLADE
  would treat is closed by dense at 1.00; identifier queries are not losing),
  so neither was built; decision + revisit trigger in
  [docs/adr/0001-day4b-gate-stays-shut.md](docs/adr/0001-day4b-gate-stays-shut.md)
- **Planned**: RDF/SPARQL knowledge graph (a minimal dependency-graph query
  slice is pulled into Day 9 —
  [docs/adr/0002-minimal-graph-query-slice.md](docs/adr/0002-minimal-graph-query-slice.md));
  local vLLM serving, Rust extensions, GNN, formal verification — see
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
