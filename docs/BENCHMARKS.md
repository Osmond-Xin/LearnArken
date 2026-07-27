# BENCHMARKS — every number, its golden set, and how to re-run it

> **What this file is.** The full measurement record behind the headline numbers
> in the [README](../README.md). Each section states the golden set, the honest
> reading (including the results that came out flat or negative), and a
> copy-pasteable reproduction command.
>
> **The rule (INV-5).** A number that cannot be reproduced does not get
> published — here or anywhere else. Tables between `<!-- BEGIN gen:… -->`
> markers are **generated** from `eval/results/*.json` by
> `tools/gen_benchmark_tables.py`; hand-editing them fails the test suite
> (`tests/test_day4_closeout.py::test_benchmark_tables_match_artifacts`). That
> guard exists because a hand-edited row was once arithmetically wrong —
> red-team finding day4 #1.
>
> **`INV-n` references** are this project's eight numbered invariants — rules
> written before any code and ranking above any spec
> ([constitution.md](constitution.md); summary in the
> [README](../README.md#learnarken)). The ones cited here: INV-1 synthetic data
> only · INV-2 distributed-interface discipline · INV-4 fail-closed refusal ·
> INV-5 reproducibility · INV-6 human-owned evidence · INV-7 honest layering.
>
> **Claim → evidence index:** [EVIDENCE.md](EVIDENCE.md).
> Rows marked *(needs services)* require the local Vespa + Neo4j containers
> ([local-services.md](local-services.md)).

## Contents

| Section | Question it answers |
| --- | --- |
| [1. Chunking × BM25](#1-chunking--bm25--day-3) | Does structure-aware chunking beat a character window? |
| [2. Embedding bake-off](#2-embedding-bake-off--day-4) | Which embedder, and can I detect a bad one? |
| [3. Retrieval-mode ablation](#3-retrieval-mode-ablation--day-4) | Is hybrid + rerank worth its latency? |
| [4. Graph-augmented retrieval](#4-graph-augmented-retrieval--day-11) | Does a KG route add ranking signal? |
| [5. Grounded QA](#5-grounded-qa--day-5) | Do answers carry citations, and does refusal work? |
| [6. Adversarial evaluation](#6-adversarial-evaluation--day-8) | What breaks when I attack my own RAG? |
| [7. Multimodal ingest & QA](#7-multimodal-ingest--qa--day-12) | Can figures be indexed without inviting hallucination? |
| [8. Performance & inference strategy](#8-performance--inference-strategy--day-13) | Which optimizations are actually justified here? |

---

## 1. Chunking × BM25 — Day 3

Scored against the **human-annotated** golden set
(`eval/golden/day3.jsonl`, 32 queries: 27 answerable + 5 no-answer traps;
relevance judged by Yi Xin — the retrieval-eval red line). Metric priority:
Recall@k leads for RAG.

| Strategy | Recall@5 | Recall@10 | MRR | nDCG@10 | Zero-hit rate |
| --- | --- | --- | --- | --- | --- |
| structure-aware | 0.93 | 0.93 | 0.80 | 0.83 | 0.40 |
| recursive (control) | 0.85 | 0.89 | 0.79 | 0.80 | 0.40 |

Structure-aware chunking leads on every ranking metric — the empirical form of
the top optimization lever (chunking ≫ k1/b, which is left at library
defaults). The **zero-hit rate** (fraction of the 5 out-of-corpus trap queries
the retriever correctly returns nothing for) is only 0.40 for both: lexical
BM25 alone cannot refuse well, which is exactly what the fail-closed answer
logic (Day 5) and adversarial no-answer evaluation (Day 8) are for — reported
honestly rather than hidden.

Day 4 adds the **semantic** strategy (embedding-based breakpoints, chunked by
the default provider): Recall@5 0.81 / MRR 0.74 / nDCG@10 0.75 on the same
golden set — structure-aware still wins, so the Day 4 retrieval ablation runs
on structure chunks. (The semantic row itself is reproduced with
`learnarken eval retrieval --strategy semantic`; the ablation in §3 is a
different command and defaults to structure chunks.)

```bash
learnarken eval retrieval   # defaults to package-a + package-c, golden day3.jsonl
```

## 2. Embedding bake-off — Day 4

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

**Qwen3-8B wins and is the sole dense provider.** The Day 4 adjudication
removed the MiniMax client from the architecture after its embeddings showed a
measured **length bias strong enough to invert relevance** — adding *relevant*
words to a chunk lowered its similarity, and an irrelevant short chunk
outscored the correct long one. Root-caused against a wire-identical LangChain
request and a healthy local control:
[notes/day4-embedding-length-bias.md](notes/day4-embedding-length-bias.md).
This is the bake-off earning its keep: the failure was in a vendor's model, not
in my code, and only a controlled comparison surfaced it.

† historical row: measured 2026-07-16 pre-review on the then-current golden
set, reproducible at commit `b414fa4` (client removed since). BGE-M3/Qwen3
rows re-measured on the reviewed set.

```bash
uv run python tools/dense_bakeoff.py   # (needs services)
```

## 3. Retrieval-mode ablation — Day 4

Same golden set, structure chunks, exact `nearestNeighbor` (no ANN confound at
43 chunks), RRF fusion via LangChain `EnsembleRetriever` (k=60), rerank via
`bge-reranker-v2-m3` over 20 candidates. The corpus is manifest-verified
before every run (fed chunk-id set must equal the engine's actual contents).

> **Which corpus this table describes.** These numbers were measured on Day 4
> (2026-07-16), on the **43-chunk pre-Day-12 corpus**. Day 12 later added figure
> assets to `samples/package-a` and `samples/package-c` and edited one of
> package-c's data modules, taking the corpus to 45 chunks including 2 figure
> chunks. Re-running the command below today therefore produces **different
> numbers in 12 of 32 metric cells** — verified 2026-07-26, cause traced,
> `bm25` included (so it is not an engine effect).
>
> The table is **left exactly as measured**. A benchmark number is a statement
> about a specific corpus at a specific revision; when the source material
> changes, the earlier measurement is void rather than approximate. Carrying the
> scoped record — instead of quietly refreshing the table — is the ruling and the
> point: [ADR-0004](adr/0004-measurements-are-bound-to-their-corpus.md),
> [F-21](reviews/arken-alignment-2026-07-26.md).

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
[notes/day4-failure-cases.md](notes/day4-failure-cases.md)):

- **Dense wins every ranking metric at this scale** — an 8B embedder over 43
  chunks even resolves identifier lookups, so the textbook "dense loses on
  identifiers" did not materialize here. Rerank matches dense on Recall@5 and
  is the only mode at 1.00 on identifier-category queries.
- **No dense-bearing mode can refuse**: dense always returns k hits, and
  fusion inherits that — the lexical arm's token-overlap guard keeps it from
  *voting for garbage* (it lifted hybrid's R@10 to 1.00) but cannot make the
  union empty. Refusal (zero-hit 0.40) exists only in pure BM25 today; real
  refusal is the answer layer's job (§5), measured under attack in §6.
- **p50 is cumulative-cache honest**: the dense row includes Qwen3-8B query
  encoding (~55 ms); hybrid reuses those cached query vectors, so its 6 ms is
  the marginal cost of BM25 + fusion; rerank adds the cross-encoder pass
  (~124 ms). Toy-scale numbers, not serving claims (INV-7).

```bash
learnarken index samples/package-a samples/package-c
learnarken eval ablation --json > eval/results/day4-ablation.json
uv run python tools/gen_benchmark_tables.py
```

## 4. Graph-augmented retrieval — Day 11

A **deterministic** query-side entity linker (regex + corpus-derived lexicons
for DMC / part-number / task entities — no LLM, fail-closed on unknown
entities) seeds a 1–2-hop traversal of the Neo4j `REFS` citation graph (both
directions, cycle-safe, hub-capped); the expanded neighborhood's chunks join
BM25 and dense as a **third RRF route** (`hybrid-graph` /
`hybrid-graph-rerank`). New and old golden sets are reported separately: the
old set's ceiling was already 1.00, so it guards regression; the new
multi-hop set (questions human-authored under an anti-circularity protocol —
see [eval/golden/README.md](../eval/golden/README.md)) is where gains could show.

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
[notes/day11-neighbor-noise.md](notes/day11-neighbor-noise.md)):

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
  ([eval/results/day11-refusal-gate.json](../eval/results/day11-refusal-gate.json)).
  This measures only the **first** of the answer layer's fail-closed gates;
  it shows structure-pulled "high-quality noise" did not clear the reranker
  threshold on its own, not that the full answer pipeline is regression-free
  under load — that would need an end-to-end no-answer run, not yet done for
  graph modes.
- One multi-hop question (MH-04, a genuine cross-ATA comparison) has **no
  reference chain between its answer DMs** — kept and flagged
  (`graph_connected: false`) rather than dropped: real questions do not
  promise to follow the graph.

```bash
learnarken index samples/package-a samples/package-c
learnarken eval ablation --golden eval/golden/day4.jsonl --json
learnarken eval ablation --golden eval/golden/day11-multihop.jsonl --json
uv run python tools/day11_refusal_gate.py
uv run python tools/gen_benchmark_tables.py
```

## 5. Grounded QA — Day 5

`learnarken query "<question>"` answers over the manifest-verified corpus with
**MiniMax-M3**, or refuses with a fixed placeholder — strict two-outcome
(INV-4). Every claim is traceable: citations carry **chunk ID + DMC + XPath**,
backfilled from chunk metadata by the system (the LLM only ever emits chunk
ids — citation-drift defense). Each gate is logged in a five-span answer trace
(`eval/traces/<trace_id>.json`). Gate mechanics are in the
[README's gate table](../README.md#2-the-interception-chain).

The refusal threshold is **measured, not guessed**
(`eval/results/day5-refusal-threshold.json`): it is calibrated to the
zero-false-refusal point. At this corpus size the answerable/trap score
distributions overlap, so gate 1 is honestly a **cost guard**, not the main
defense — the load is carried by the LLM answerability contract and the
verbatim-quote citation check.

Fixed-seed answer sample (20 golden queries, `eval/results/day5-answer-sample.json`):

| Metric | Value |
| --- | --- |
| answerable_success | 0.875 (14/16) |
| false_refusal_rate | 0.125 |
| trap_refusal_rate | **1.00** (4/4) |
| citation_coverage_when_answered | 1.00 |

Honest reading: **coverage ≠ correctness.** `citation_coverage_when_answered`
says every answered row carried citations that survived the verbatim-quote
check; it does not say the answer is semantically entailed. That is what §6
attacks and what the human groundedness labels calibrate.

```bash
learnarken index samples/package-a samples/package-c
learnarken query "How do I remove the hydraulic pump?"       # (needs services)
uv run python tools/answer_sample_eval.py                     # (needs services)
uv run python tools/measure_refusal_threshold.py              # (needs services)
```

## 6. Adversarial evaluation — Day 8

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

<!-- BEGIN gen:day8-before-after -->
| Metric | Before | After |
| --- | --- | --- |
| **Cross-doc aggregation defect** (X-01: sums 25 Nm + 18 Nm → "43 Nm") | **affirmed 3/3** | **eliminated 0/3** |
| Intersection groundedness — 2 judges (single-run snapshot) | 0.53 | **0.69** |
| Per-judge groundedness (Codex / agy) | 0.60 / 0.60 | **0.69 / 0.75** |
| Overall behavior pass rate (N=3 mean) | 0.94 | 0.92 *(flat — noise-dominated)* |
<!-- END gen:day8-before-after -->

> **Correction, 2026-07-25** (red team `readme-refactor-2026-07-25` F-01). These
> four rows used to be hand-typed and had drifted from the artifacts: the "after"
> groundedness was published as `0.63 / 0.63 / 0.69` when
> `day8-adversarial-report.json` records `0.69 / 0.69 / 0.75`, and the N=3
> behaviour mean `0.9167` had been rounded up to `0.93`. Both errors are now
> corrected **from the frozen artifacts, with no re-run** — nothing was
> re-measured, the published text had simply stopped matching the record. The
> table is generated from `day8-adversarial-{before,report}.json` and
> `day8-behavior-{before,after}.json`, so `--check` now guards it like every
> other table here and this class of drift cannot recur silently.

Honest reading (INV-7): the **overall** behavior pass rate is essentially flat
within the N=3 noise (0.94 → 0.93) — at this scale it is dominated by MiniMax
non-determinism, not by the fix. What the guardrail **demonstrably** does is
kill the one *reproducible* defect and lift judge-scored groundedness.

Re-validation is measured, never self-declared: the same attacks re-run through
the judges after the fix show X-01 flipping affirm→refuse and P-03 flipping
hallucinated→grounded on both judges. One honest wrinkle — a *correct* answer
(P-09: "25 Nm, not 25 ft-lb") is still judged hallucinated by both, which is
exactly why the judge is calibrated against human labels with **Cohen's Kappa**
(soft gate 0.60), not trusted blind. On the human anchor (n=30: Day 5 answered
rows + Day 8 adversarial, human-labeled blind, INV-6) both judges pass:
**Codex κ = 0.74, agy κ = 0.67** — "substantial" agreement (Landis-Koch),
enough to back the groundedness numbers but deliberately short of blind trust.
Full evidence chain: [notes/day8-defects.md](notes/day8-defects.md).

```bash
learnarken eval adversarial --seed 42                                    # live judges (needs services)
uv run python tools/adversarial_eval.py --repeat 3 --label after         # behavior distribution
uv run python tools/adversarial_eval.py --kappa-only                     # deterministic, offline
```

The κ step is deterministic over the frozen judge labels +
`eval/golden/day8-human-labels.json`. Live-judge values drift run-to-run — the
frozen artifact is the record.

## 7. Multimodal ingest & QA — Day 12

Synthetic ICN figures (self-drawn SVG → PNG, INV-1) are described **offline** by
a VLM into a schema-constrained structure, **mechanically diffed** against the
DM-declared hotspot set, and **SHA-256-bound** to the image (re-verified at index
time — a swapped image or edited label mints a new chunk id and fails corpus
verification). Verified figures join the **same** retrieval corpus as text and
are cited as `[ICN-…, Hotspot NN]`. Query-time **second-look** re-reads the image
with a **multi-sample consensus** (a single read of the unstable VLM channel is
not trusted).

Fail-closed throughout (**G15**): a question asking for a visual detail the
figure cannot support — or an answer that would assert content ungrounded in
the cited figure (a fabricated colour, material, or part/torque value) — is
**refused at citation confirmation, never fabricated**. Honest scope: the
positive-grounding token check fires when **every** cited chunk is a figure; a
mixed text+figure answer is not re-checked token-by-token today
([answer/engine.py](../src/learnarken/answer/engine.py)). The
hallucination-boundary is deliberately fail-safe (occasional over-refusal); a
tiered severity policy is a Roadmap topic
([notes/day12-hallucination-boundary.md](notes/day12-hallucination-boundary.md)).

Honest scope (INV-7): measured on synthetic wireframes; description-quality
numbers do not extrapolate to real scans. Three-class eval + regression:
[eval/results/day12-multimodal.json](../eval/results/day12-multimodal.json),
[notes/day12-figure-noise.md](notes/day12-figure-noise.md).

```bash
uv run pytest tests/test_day12_multimodal.py -q
uv run python tools/gen_figures.py    # re-render → re-hash → diff the committed record
```

## 8. Performance & inference strategy — Day 13

A deliberate "**verifiable engineering judgment, not flashy optimization**" day —
each experiment is allowed to honestly conclude *no benefit* and still count as a
**passing** result:

- **multiprocessing** validation sharding at **per-DM-file** granularity, behind an
  abstraction and **byte-equivalent to the single-process baseline** (INV-2,
  asserted). Result: **no speedup at toy scale** — pool spawn + pickle overhead
  dominate work this cheap ([eval/results/day13-mp-scaling.json](../eval/results/day13-mp-scaling.json)).
  The concrete Amdahl serial fraction (L3 cross-file resolution) is named, not hidden.
- **profile → numba**: py-spy/cProfile first ([eval/results/day13-hotspots.json](../eval/results/day13-hotspots.json));
  the CPU is spent in lxml / Pydantic / C-extensions, so the honest verdict is
  **"no numba target justified"** — a passing result, and **no numba dependency is
  added** ([notes/day13-numba-decision.md](notes/day13-numba-decision.md)).
- **Tree-of-Thoughts repair** (best-of-N): 3 heterogeneous role candidates
  (conservative / schema-focused / reference-focused) selected by the **deterministic
  sandbox validator — never LLM self-judgment** (INV-4), with a reward-hacking
  deletion veto. Repeat-tested because the generator is non-deterministic (2 of 8
  findings flipped across runs): **baseline 3/8 = ToT 3/8 majority-solved, at ~2.8×
  the completion tokens** — the honest *"when is search **not** worth it"* result
  ([eval/results/day13-tot.json](../eval/results/day13-tot.json)).
- **asyncio** orchestration for the **I/O-bound** fan-out only, strictly separated
  from multiprocessing (no `async def` around a CPU hotspot): Semaphore-bounded,
  per-task timeout, non fail-fast — **~3× wall-clock overlap** on the waiting-type
  work ([eval/results/day13-async.json](../eval/results/day13-async.json)).
- **Rust / Python free-threading**: gate & narrative only — no crate, no code, no
  build change; the evidence door does not open on this corpus
  ([ADR-0003](adr/0003-day13-rust-gate.md)).

```bash
uv run python tools/day13_mp_bench.py
uv run python tools/day13_profile.py
uv run python tools/day13_tot_eval.py
uv run python tools/day13_async_bench.py
```

The cross-host red team returned DO_NOT_MERGE with 12 findings on this slice —
all fixed with regression tests ([reviews/day13.md](reviews/day13.md)).

---

## What is *not* measured here

Stated so no reader has to infer it (INV-7, and the full list is in
[EVIDENCE.md](EVIDENCE.md#what-is-not-claimed-honest-boundary-inv-7)):

- Corpus scale is **synthetic and small** (43–45 chunks). Retrieval numbers at
  this size say which design choice is better *here*; they are not a claim
  about production recall.
- Latency figures describe **one dev machine**, warm caches, no concurrency —
  no SLO is claimed.
- "Compliant" means *this project's validator says so*. There is **no expert
  ground truth** for S1000D conformance in this repo.
- Distributed behavior is **simulated on one machine**; interfaces are designed
  as-if-distributed, but no multi-node run exists.
