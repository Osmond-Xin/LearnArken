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

## Progress (Day 1–13)

| Day | Node | Tag | Status |
| --- | --- | --- | --- |
| 1 | Skeleton, sample packages, project constitution | `v0.1.0` | ✅ 2026-07-13 |
| 2 | Canonical model & validators | `v0.2.0` | ✅ 2026-07-14 |
| 3 | BM25 baseline & retrieval evaluation | `v0.3.0` | ✅ 2026-07-16 |
| 4 | Hybrid retrieval & ablation table ⚑ heavy red team | `v0.4.0` | ✅ 2026-07-16 |
| 5 | RAG with citations ⚑ heavy red team | `v0.5.0` | ✅ 2026-07-17 |
| 6 | API & local demo | `v0.6.0` | ✅ 2026-07-17 |
| 7 | Validation-repair agent | `v0.7.0` | ✅ 2026-07-17 |
| 8 | Adversarial evaluation: attacking my own RAG ⚑ heavy red team | `v0.8.0` | ✅ 2026-07-18 |
| 9 | Evidence chain & machine readability | `v0.9.0` | ✅ 2026-07-18 |
| 10 | On-demand real-stack deployment & wrap-up | `v1.0.0` | ✅ 2026-07-18 |
| 11 | Graph-augmented retrieval (KG-RAG slice) | `v1.1.0` | ✅ 2026-07-19 |
| 12 | Multimodal ingest & QA (describe-then-index + G15 second-look) ⚑ heavy red team | `v1.2.0` | ✅ 2026-07-20 |
| 13 | Performance & inference-strategy experiments (mp / profile→numba / ToT / asyncio) ⚑ heavy red team | `v1.3.0` | ✅ 2026-07-21 |

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
| dense (Vespa + Qwen3-8B) | **0.99** | **1.00** | **0.87** | **0.90** | 0.00 | 56 ms |
| hybrid (RRF) | 0.93 | **1.00** | 0.85 | 0.88 | 0.00 | 6 ms |
| hybrid + rerank | **0.99** | 0.99 | 0.85 | 0.88 | 0.00 | 123 ms |

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

### Grounded QA — Day 5 (cited answers or refusal, nothing in between)

`learnarken query "<question>"` answers over the manifest-verified corpus
with **MiniMax-M3**, or refuses with a fixed placeholder — strict two-outcome
(INV-4). Every claim is traceable: citations carry **chunk ID + DMC + XPath**,
backfilled from chunk metadata by the system (the LLM only ever emits chunk
ids — citation-drift defense). Three fail-closed gates, each logged in a
five-span answer trace (`eval/traces/<trace_id>.json`):

1. **threshold** — reranker top-1 below the measured zero-false-refusal
   threshold (`eval/results/day5-refusal-threshold.json`; the distributions
   overlap at this scale, so this gate is a cost guard, not the main defense);
2. **LLM** — structured output `is_answerable: false`;
3. **citation validation** — each citation must name a retrieved chunk AND
   carry a verbatim `supporting_quote` that is a span of that chunk; a valid
   pointer with an unfindable quote refuses (a valid citation is not
   groundedness — red-team day5 #1). Semantic entailment beyond this
   substring floor is Day 8's adversarial-eval work.

Retrieval combines the Vespa vector store with the **Neo4j dependency graph**
(synced idempotently at `learnarken index`; DM→DM dmRefs and DM→ICN edges are
injected as structured context — tutorial 06 §9 interface ③).

Reproduce: `learnarken index samples/package-a samples/package-c` then
`learnarken query "How do I remove the hydraulic pump?"` (needs the local
services + `MINIMAX_*` in the repo-root `.env`, see
[docs/local-services.md](docs/local-services.md)); quality sample:
`uv run python tools/answer_sample_eval.py` →
`eval/results/day5-answer-sample.json` (20 fixed-seed golden queries;
metrics over the full sampled sets — answerable_success, false_refusal_rate,
trap_refusal_rate — coverage ≠ correctness; human groundedness review of the
answered rows pending).

### Adversarial evaluation — Day 8 (attack the RAG, judge groundedness, fix defects)

`learnarken eval adversarial` runs a **32-case adversarial set**
(`eval/golden/day8-adversarial.jsonl`; rewrite-invariance / perturbation /
no-answer / cross-doc) through the answer engine, then scores each answered row
for **groundedness with two heterogeneous judges — Codex (GPT-family) and agy
(Gemini 3.1 Pro via Antigravity), never MiniMax** (the generator — same-family
judging self-preferences its own hallucinations). The headline uses the
**intersection** (both judges must pass); judge verdicts are frozen to
`eval/results/day8-judge-*.json` for reproducibility.

Defects exposed here are **generation-layer**. Root-cause analysis
**exonerated retrieval** — the one candidate retrieval miss (a dropped cross-DM
fact) was MiniMax non-determinism, not recall (its trace shows both facts
retrieved). The fix is a prompt guardrail (entity/value alignment +
no-derivation). Because MiniMax is non-deterministic at temperature 0, behavior
is measured as a **mean over N=3 repeated runs**, frozen to
`eval/results/day8-behavior-{before,after}.json`.

Honest reading (INV-7): the **overall** behavior pass rate is essentially flat
within the N=3 noise (0.94 → 0.93) — at this scale it is dominated by MiniMax
non-determinism, not by the fix. What the guardrail **demonstrably** does is kill
the one *reproducible* defect and lift judge-scored groundedness:

| Metric | Before | After |
| --- | --- | --- |
| **Cross-doc aggregation defect** (X-01: sums 25 Nm + 18 Nm → "43 Nm") | **affirmed 3/3** | **eliminated 0/3** |
| Intersection groundedness — 2 judges (single-run snapshot) | 0.53 | **0.63** |
| Per-judge groundedness (Codex / agy) | 0.60 / 0.60 | **0.63 / 0.69** |
| Overall behavior pass rate (N=3 mean) | 0.94 | 0.93 *(flat — noise-dominated)* |

Decision-6 re-validation (same attacks re-run through the judges after the fix,
never self-declared): X-01 flips affirm→refuse; P-03 flips hallucinated→grounded
on both judges. One honest wrinkle — a *correct* answer (P-09: "25 Nm, not 25
ft-lb") is still judged hallucinated by both, which is exactly why the judge is
calibrated against human labels with **Cohen's Kappa** (soft gate 0.60), not
trusted blind. On the human anchor (n=30: Day 5 answered rows + Day 8
adversarial, human-labeled blind, INV-6) both judges pass: **Codex κ = 0.74,
agy κ = 0.67** — "substantial" agreement (Landis-Koch), enough to back the
groundedness numbers but deliberately short of blind trust. The κ step
(`tools/adversarial_eval.py --kappa-only`) is deterministic over the frozen
judge labels + `eval/golden/day8-human-labels.json`. Full evidence chain:
[docs/notes/day8-defects.md](docs/notes/day8-defects.md).

Reproduce: `learnarken eval adversarial --seed 42` (live judges); behavior
distribution: `uv run python tools/adversarial_eval.py --repeat 3 --label after`
(needs the local services, `MINIMAX_*` in `.env`, and the `codex` + `agy` CLIs;
exact values drift run-to-run — the frozen artifact is the record).

### Multimodal ingest & QA — Day 12 (describe-then-index + G15 fail-closed)

Synthetic ICN figures (self-drawn SVG → PNG, INV-1) are described **offline** by
a VLM into a schema-constrained structure, **mechanically diffed** against the
DM-declared hotspot set, and **SHA-256-bound** to the image (re-verified at index
time — a swapped image or edited label mints a new chunk id and fails corpus
verification). Verified figures join the **same** retrieval corpus as text and
are cited as `[ICN-…, Hotspot NN]`. Query-time **second-look** re-reads the image
with a **multi-sample consensus** (a single read of the unstable VLM channel is
not trusted). Fail-closed throughout (**G15**): a question asking for a visual
detail the figure cannot support — or an answer that would assert content
ungrounded in the cited figure (a fabricated colour, material, or part/torque
value) — is **refused at citation confirmation, never fabricated**. The
hallucination-boundary is deliberately fail-safe (occasional over-refusal); a
tiered severity policy is a [Roadmap topic](docs/notes/day12-hallucination-boundary.md).
Honest scope (INV-7): measured on synthetic wireframes; description-quality
numbers do not extrapolate to real scans. Three-class eval + regression:
[eval/results/day12-multimodal.json](eval/results/day12-multimodal.json),
[docs/notes/day12-figure-noise.md](docs/notes/day12-figure-noise.md).

### Performance & inference-strategy experiments — Day 13 (judgment over keywords)

A deliberate "**verifiable engineering judgment, not flashy optimization**" day —
each experiment is allowed to honestly conclude *no benefit* and still count as a
**passing** result:

- **multiprocessing** validation sharding at **per-DM-file** granularity, behind an
  abstraction and **byte-equivalent to the single-process baseline** (INV-2,
  asserted). Result: **no speedup at toy scale** — pool spawn + pickle overhead
  dominate work this cheap ([day13-mp-scaling.json](eval/results/day13-mp-scaling.json)).
  The concrete Amdahl serial fraction (L3 cross-file resolution) is named, not hidden.
- **profile → numba**: py-spy/cProfile first ([day13-hotspots.json](eval/results/day13-hotspots.json));
  the CPU is spent in lxml / Pydantic / C-extensions, so the honest verdict is
  **"no numba target justified"** — a passing result, and **no numba dependency is
  added** ([docs/notes/day13-numba-decision.md](docs/notes/day13-numba-decision.md)).
- **Tree-of-Thoughts repair** (best-of-N): 3 heterogeneous role candidates
  (conservative / schema-focused / reference-focused) selected by the **deterministic
  sandbox validator — never LLM self-judgment** (INV-4), with a reward-hacking
  deletion veto. Repeat-tested because the generator is non-deterministic (2 of 8
  findings flipped across runs): **baseline 3/8 = ToT 3/8 majority-solved, at ~2.8×
  the completion tokens** — the honest *"when is search **not** worth it"* result
  ([day13-tot.json](eval/results/day13-tot.json)).
- **asyncio** orchestration for the **I/O-bound** fan-out only, strictly separated
  from multiprocessing (no `async def` around a CPU hotspot): Semaphore-bounded,
  per-task timeout, non fail-fast — **~3× wall-clock overlap** on the waiting-type
  work ([day13-async.json](eval/results/day13-async.json)).
- **Rust / Python free-threading**: gate & narrative only — no crate, no code, no
  build change; the evidence door does not open on this corpus
  ([ADR-0003](docs/adr/0003-day13-rust-gate.md)).

Reproduce: `uv run python tools/day13_mp_bench.py`,
`tools/day13_profile.py`, `tools/day13_tot_eval.py`, `tools/day13_async_bench.py`.
The cross-host red team returned DO_NOT_MERGE with 12 findings — all fixed with
regression tests ([docs/reviews/day13.md](docs/reviews/day13.md)).

### Graph-augmented retrieval — Day 11 (entity linking → REFS expansion → third RRF route)

A **deterministic** query-side entity linker (regex + corpus-derived lexicons
for DMC / part-number / task entities — no LLM, fail-closed on unknown
entities) seeds a 1-2-hop traversal of the Neo4j `REFS` citation graph (both
directions, cycle-safe, hub-capped); the expanded neighborhood's chunks join
BM25 and dense as a **third RRF route** (`hybrid-graph` /
`hybrid-graph-rerank`). New and old golden sets are reported separately: the
old set's ceiling was already 1.00, so it guards regression; the new
multi-hop set (questions human-authored under an anti-circularity protocol —
see [eval/golden/README.md](eval/golden/README.md)) is where gains could show.

<!-- BEGIN gen:day11-ablation -->
**Old golden set (day4, regression guard — dense R@10 was already 1.00)** — answerable n=67, no-answer traps n=15:

| Mode | Recall@5 | Recall@10 | MRR | nDCG@10 | Zero-hit rate | p50 |
| --- | --- | --- | --- | --- | --- | --- |
| bm25 (in-process) | 0.83 | 0.88 | 0.74 | 0.77 | **0.40** | <1 ms |
| dense (Vespa + Qwen3-8B) | **0.99** | **1.00** | **0.87** | **0.90** | 0.00 | 55 ms |
| hybrid (RRF) | 0.93 | **1.00** | 0.85 | 0.88 | 0.00 | 5 ms |
| hybrid + rerank | **0.99** | 0.99 | 0.85 | 0.88 | 0.00 | 124 ms |
| hybrid + graph (3-way RRF) | 0.93 | **1.00** | 0.84 | 0.88 | 0.00 | 6 ms |
| hybrid + graph + rerank | **0.99** | 0.99 | 0.85 | 0.88 | 0.00 | 133 ms |

**New multi-hop set (day11, human-authored, answers span 2-3 DMs)** — answerable n=7, no-answer traps n=3:

| Mode | Recall@5 | Recall@10 | MRR | nDCG@10 | Zero-hit rate | p50 |
| --- | --- | --- | --- | --- | --- | --- |
| bm25 (in-process) | 0.58 | 0.65 | 0.73 | 0.58 | **0.00** | <1 ms |
| dense (Vespa + Qwen3-8B) | **0.82** | **0.95** | 0.74 | 0.74 | 0.00 | 66 ms |
| hybrid (RRF) | 0.65 | 0.83 | 0.81 | 0.72 | 0.00 | 6 ms |
| hybrid + rerank | 0.73 | 0.81 | 0.71 | 0.69 | 0.00 | 175 ms |
| hybrid + graph (3-way RRF) | 0.64 | 0.83 | **0.89** | **0.75** | 0.00 | 15 ms |
| hybrid + graph + rerank | 0.73 | 0.81 | 0.71 | 0.69 | 0.00 | 208 ms |

T3 refusal-regression gate (deterministic threshold gate over 18 no-answer traps): hybrid 0.06 vs hybrid+graph 0.06 — **pass** (not lower).

Model snapshots pinned (INV-5): `BAAI/bge-m3 @ 5617a9f61`, `BAAI/bge-reranker-v2-m3 @ 953dc6f6f`, `Qwen/Qwen3-Embedding-8B @ 1d8ad4ca9`.
<!-- END gen:day11-ablation -->

Honest readings (details:
[docs/notes/day11-neighbor-noise.md](docs/notes/day11-neighbor-noise.md)):

- **Post-rerank, the graph route changes nothing at this scale** — the
  `hybrid+graph+rerank` row is bit-identical to `hybrid+rerank`: with 43
  chunks and 20 candidates per arm, the pool already covers nearly the whole
  corpus, so the route's rescue mechanism (pulling chunks the other arms
  missed entirely) has nothing to rescue. Its measured value here is the
  **pre-rerank ranking signal on multi-hop queries** (MRR 0.81→0.89, nDCG
  0.72→0.75) plus citation-path explainability (traces carry linked entities
  and per-candidate hop/direction).
- **Neighbor noise, measured**: on the old set the graph route dilutes
  pre-rerank MRR/nDCG slightly (0.850→0.842 / 0.883→0.879) and costs ~13 ms
  p50 on entity-dense queries; recall never regresses.
- **The deterministic threshold gate held, per-query (T3)**: over all 18
  no-answer traps, every trap `hybrid` correctly refuses is still refused
  under `hybrid-graph` — no trap flipped from refuse to answer (checked
  per-query, not just as an aggregate rate, since offsetting flips could
  otherwise hide a regression)
  ([eval/results/day11-refusal-gate.json](eval/results/day11-refusal-gate.json)).
  This measures only the **first** of the answer layer's three fail-closed
  gates (Day 5: threshold → citation → LLM contract); it shows structure-
  pulled "high-quality noise" did not clear the reranker threshold on its
  own, not that the full answer pipeline is regression-free under load —
  that would need an end-to-end no-answer run, not yet done for graph modes.
- One multi-hop question (MH-04, a genuine cross-ATA comparison) has **no
  reference chain between its answer DMs** — kept and flagged
  (`graph_connected: false`) rather than dropped: real questions do not
  promise to follow the graph.

Reproduce: `learnarken index samples/package-a samples/package-c`, then
`learnarken eval ablation --golden eval/golden/day4.jsonl --json` and
`--golden eval/golden/day11-multihop.jsonl --json` (combined into
[eval/results/day11-ablation.json](eval/results/day11-ablation.json)),
`uv run python tools/day11_refusal_gate.py`, and
`uv run python tools/gen_benchmark_tables.py`.

## Live Demo (On-Demand)

The full stack (Vespa + Neo4j + local embedding/rerank models + MiniMax) is too
heavy for any free tier, so instead of a permanently-degraded copy the demo runs
the **real stack, on demand**:

- A recruiter opens a per-recipient token link → a static status page that
  doubles as a guided walkthrough (architecture + key points) and a live state
  monitor (**closed → starting → running → auto-closing**).
- Clicking *start* boots a stopped GCP VM running the exact `make demo` topology
  — the same code and same benchmarks, **no substituted backend, no INV-5
  caveat**. The page shows real per-stage self-check progress, then a countdown.
- **Cost fences (fail-closed, layered):** 30-minute business-idle auto-shutdown
  and a 3-hour hard cap, both enforced in-VM from the kernel clock; an in-process
  LLM call quota + concurrency cap (MiniMax spend is not GCP billing, so this is
  the real spend fence); a shared access key on every spending route; uploads and
  full prompt/answer traces disabled in public mode; a `$20` budget alert.

This is deliberately **one-visitor-at-a-time and cost-aware**, not a
high-availability service — the trigger itself is the interest signal. Mechanism,
security envelope and the exact `gcloud` commands are in
[deploy/runbook.md](deploy/runbook.md); the cross-host red-team review of the
deploy slice is [docs/reviews/day10.md](docs/reviews/day10.md).

## Roadmap (Honest Layering)

- **Implemented**: `inspect` CLI (package summary, JSON output, hardened XML
  parsing); synthetic sample packages a/b/c with enumerated violation manifest
  (VIO-1..8); canonical Pydantic model with structured applicability;
  four-layer validator (well-formedness → project mini-XSD → BREX rules →
  cross-file reference graph) via `validate`; per-DMC query via `dm`;
  identifier-preserving BM25 baseline + human-annotated golden-set evaluation
  (`search`, `eval retrieval`); Vespa-backed dense retrieval (Qwen3-8B,
  revision-pinned), hybrid RRF + cross-encoder rerank, package-scoped search,
  four-mode ablation with generated benchmark tables (`index`, `eval ablation`);
  grounded question answering with mandatory citations or explicit refusal —
  three fail-closed gates (rerank threshold, LLM answerability, verbatim-quote
  citation verification) — via `query` (Day 5); a local demo (FastAPI backend +
  Streamlit dumb client, SSE streaming with a retraction protocol, transactional
  upload) via `make demo` (Day 6); an LLM-driven ReAct **repair agent** that
  diagnoses L0–L3 validation findings and proposes minimal structured patches,
  trusted only when the deterministic validator re-runs clean, with a default
  dry-run and an approve-then-write `--apply` (per-patch human gate, never
  silent — constitution §1.3) via `repair` (Day 7); an adversarial evaluation
  harness — 32-case golden set, two heterogeneous judges (Codex + agy) with
  Cohen's κ calibration against human labels and deterministic behavioral
  scoring — via `eval adversarial` (Day 8); a Neo4j dependency-graph impact
  query (reverse `dmRef` traversal, cycle-safe, depth-bounded) via
  `graph impact`, and a machine-readable evidence chain (`llms.txt`,
  [docs/EVIDENCE.md](docs/EVIDENCE.md), [docs/AI-COLLABORATION.md](docs/AI-COLLABORATION.md))
  (Day 9); an **on-demand real-stack deployment** — a token-gated Cloud Function
  boots a stopped GCP VM running the full `make demo` topology behind a
  static status/guide page, with layered fail-closed cost fences (in-VM idle +
  hard-cap shutdown, in-process LLM spend quota, shared-key gate, public-mode
  upload/trace kill switches) — see [deploy/](deploy/runbook.md) (Day 10);
  **graph-augmented retrieval** — deterministic entity linking (regex +
  corpus lexicons, no LLM) + 1-2-hop `REFS` expansion fused as a third RRF
  route (`hybrid-graph` modes), with a human-authored multi-hop golden set
  and an honestly-flat post-rerank ablation (Day 11)
- **Toy-scale**: synthetic sample-package size; single-machine simulation of
  distributed behavior; the repair agent's sandbox is an application-layer fence
  (import/argv allow-list + temp-dir jail + resource limits), not OS-level
  isolation; the local demo is single-user and loopback-bound with no auth, and
  the on-demand public deployment is single-visitor with a shared-key gate and
  plain-HTTP transport (TLS/per-recipient session auth are deferred, see
  [docs/reviews/day10.md](docs/reviews/day10.md))
- **Considered and declined on evidence**: SPLADE and ColBERT — the Day 4b
  gates stayed shut on the reviewed ablation (the paraphrase gap SPLADE
  would treat is closed by dense at 1.00; identifier queries are not losing),
  so neither was built; decision + revisit trigger in
  [docs/adr/0001-day4b-gate-stays-shut.md](docs/adr/0001-day4b-gate-stays-shut.md).
  Likewise **numba, self-written Rust/PyO3, and Python free-threading** (Day 13):
  the profiler shows no pure-numeric or Python-side CPU bottleneck on this corpus,
  so numba records "no target justified" and the Rust/free-threading doors stay
  gate/narrative only — [ADR-0003](docs/adr/0003-day13-rust-gate.md)
- **Considered and preferred as an informed consumer**: the stack already *consumes*
  Rust through `pydantic-core` (canonical-model validation/serialization) and the
  HuggingFace `tokenizers` backend (embedding/rerank tokenization, via
  sentence-transformers) — getting Rust performance by selection rather than by
  writing an extension (Day 13). (BM25 here is pure-Python `rank-bm25`; Tantivy was
  the rejected search-engine candidate, not a Rust dependency of this project.)
- **Planned**: full RDF/SPARQL knowledge graph (the minimal dependency-graph
  query slice landed in Day 9 —
  [docs/adr/0002-minimal-graph-query-slice.md](docs/adr/0002-minimal-graph-query-slice.md);
  the full graph, version/issue-semantics modelling, and multi-hop SPARQL stay
  planned); local vLLM serving, Rust extensions, GNN, formal verification — see
  [docs/project-design.md](docs/project-design.md)
- **Planned — deferred from Day 8 red team**: number/unit-aware answer matching
  (the substring matcher treats `125 Nm` as satisfying `25 Nm`); a judge-call
  circuit breaker (a hard cap on judge failures, not just a per-call timeout);
  index content-hash / epoch and plaintext-trace payload hardening — see
  [docs/reviews/day8.md](docs/reviews/day8.md)
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
| [docs/architecture/](docs/architecture/README.md) | Architecture snapshot & change baseline (file inventory, data flow, config, tech selection, API/demo) |
| [docs/research/](docs/research/README.md) · [docs/gemini-deepresearch/](docs/gemini-deepresearch/) | Daily deep-research reports + unknowns scans (研→读→扫 learning loop) |
| [docs/adr/](docs/adr/) | Architecture decision records (Day 4b gate, minimal graph-query slice) |
| [docs/redteam.md](docs/redteam.md) · [docs/local-services.md](docs/local-services.md) | Red-team recipes; local Vespa/Neo4j/MiniMax service handbook |
| [docs/tutorials/00-overview.md](docs/tutorials/00-overview.md) | Zero-background tutorial series (Chinese) |
| [samples/](samples/README.md) | S1000D sample notes and license audit |
| [deploy/](deploy/runbook.md) | On-demand GCP deploy: VM stack, idle watchdog, token trigger function, status page, runbook |
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

`inspect` and `validate` run offline. The retrieval, QA and repair paths
(`index`, `query`, `repair`, `make demo`) need the local services up
(Vespa + Neo4j) and a repo-root `.env` (`MINIMAX_*`, `NEO4J_*`) — see
[docs/local-services.md](docs/local-services.md). In particular `repair`
drives an LLM ReAct loop per finding; `repair --apply` writes a fix only after
a per-patch human approval (constitution §1.3).

Validation results are only claimed for locked installs (`uv.lock`); CI runs
`uv sync --locked` so parser behavior cannot drift with dependency versions.
