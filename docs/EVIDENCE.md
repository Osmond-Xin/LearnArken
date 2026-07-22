# EVIDENCE — claim → repository evidence map

> **Purpose.** Every outward capability claim about this project maps here to
> **repo-internal evidence** and a **copy-pasteable reproduction command**. It is
> built for a reviewer — human *or* a hiring-side AI agent — to verify any
> benchmark number without trusting prose. Machine-first: reading only this file
> plus [`llms.txt`](../llms.txt), an agent can locate how to re-run any number
> below in minutes.
>
> **Provenance.** AI-generated (Day 9, 2026-07-18), pending human review. Numbers
> are copied **only** from committed artifacts on the current `main`
> (`eval/results/*.json`, `eval/golden/`) — never from a historical handoff. A
> guard test ([`tests/test_day9_evidence.py`](../tests/test_day9_evidence.py))
> enforces two invariants: every path linked below **exists** (no dead links),
> and every number tagged below **matches its source artifact** (no drift).
>
> **INV-1 boundary.** This is a *public* file: it carries **abstracted capability
> claims only** — no resume text or personal job-search numbers. Resume lines map
> onto these public anchors from the non-committed `resume-master/` private doc,
> which points inward and never the reverse.

## How to read this file

- Each row is one **claim** → its **evidence** (a committed file) → a **reproduce**
  command → a **layer** label.
- Links are **relative to this file** (`docs/`), so they resolve both on GitHub
  and for an agent walking the tree; a linked path that stops existing fails CI.
- Reproduction commands assume `uv sync` has run. Rows marked *(needs services)*
  additionally need the local Vespa + Neo4j containers up
  ([`docs/local-services.md`](local-services.md)).
- **Honesty layer** (INV-7), mapped from the evidence-tier model in the Day 9 DR
  report:
  | Layer | Meaning | Evidence tier |
  | --- | --- | --- |
  | `Implemented` | code + tests + a number tied to a golden set & result JSON | public fact / disclosure |
  | `Toy-scale` | works, but at synthetic-corpus scale — labelled, not hidden | disclosure / derived |
  | `Planned` | design/notes only, no runnable artifact | hypothesis |

## Retrieval quality

| Claim | Number(s) | Evidence | Reproduce | Layer |
| --- | --- | --- | --- | --- |
| Structure-aware chunking leads the BM25 baseline on the versioned golden set | `Recall@10 0.93`, `nDCG@10 0.83`, `zero-hit 0.40` | [README](../README.md) retrieval section; [eval/golden/day3.jsonl](../eval/golden/day3.jsonl) | `learnarken eval retrieval` *(needs services)* | `Toy-scale` |
| Dense retrieval reaches full recall at 10 on the hybrid golden set | `Recall@10 1.00`, `Recall@5 0.99`, `nDCG@10 0.90` | [eval/results/day4-ablation.json](../eval/results/day4-ablation.json) (`results.dense`) | `learnarken eval ablation --json` *(needs services)* | `Toy-scale` |
| BM25 stays indispensable for identifier queries despite lower semantic recall | `Recall@5 0.83`, `Recall@10 0.88` | [eval/results/day4-ablation.json](../eval/results/day4-ablation.json) (`results.bm25`) | `learnarken eval ablation --json` *(needs services)* | `Toy-scale` |
| Local Qwen3-Embedding-8B leads the local embedding bake-off over BGE-M3 | Qwen3 `Recall@5 0.99 / Recall@10 1.00`; BGE-M3 `0.92 / 0.97` | [eval/results/day4-bakeoff.json](../eval/results/day4-bakeoff.json) (`results.qwen3-8b`, `results.bge-m3`) | `uv run python tools/dense_bakeoff.py` *(needs services)* | `Toy-scale` |

## Grounded QA & citations

| Claim | Number(s) | Evidence | Reproduce | Layer |
| --- | --- | --- | --- | --- |
| Answers carry citations or an explicit refusal — no third state (INV-4) | — (behavioural, tested) | [tests/test_day5_answer.py](../tests/test_day5_answer.py); [eval/results/day5-answer-sample.json](../eval/results/day5-answer-sample.json) | `uv run python tools/answer_sample_eval.py` *(needs services)* | `Implemented` |
| Refusal threshold measured, not guessed | see artifact | [eval/results/day5-refusal-threshold.json](../eval/results/day5-refusal-threshold.json) | `uv run python tools/measure_refusal_threshold.py` *(needs services)* | `Toy-scale` |

## Adversarial evaluation (Day 8)

| Claim | Number(s) | Evidence | Reproduce | Layer |
| --- | --- | --- | --- | --- |
| Two heterogeneous judges are calibrated against human blind labels via Cohen's κ | Codex `κ 0.737`; agy `κ 0.667` (n=30) | [eval/results/day8-kappa.json](../eval/results/day8-kappa.json); [eval/golden/day8-human-labels.json](../eval/golden/day8-human-labels.json) | `uv run python tools/adversarial_eval.py --kappa-only` | `Toy-scale` |
| The cross-document aggregation defect (X-01) is deterministically eliminated | `3/3 → 0/3` occurrences | [docs/notes/day8-defects.md](notes/day8-defects.md); [eval/results/day8-adversarial-before.json](../eval/results/day8-adversarial-before.json) | `uv run python tools/adversarial_eval.py --repeat 3 --label after` | `Toy-scale` |
| Judge groundedness improved after the prompt-guardrail fix | `0.53 → 0.63` | [eval/results/day8-judge-codex.json](../eval/results/day8-judge-codex.json); [docs/notes/day8-defects.md](notes/day8-defects.md) | `learnarken eval adversarial --seed 42` *(needs services)* | `Toy-scale` |
| The adversarial set is a 32-case, four-class golden set (English-only, anti-leak) | `32` cases | [eval/golden/day8-adversarial.jsonl](../eval/golden/day8-adversarial.jsonl); [tests/test_day8_adversarial.py](../tests/test_day8_adversarial.py) | `uv run pytest tests/test_day8_adversarial.py -q` | `Implemented` |

## Dependency-graph impact analysis (Day 9)

| Claim | Number(s) | Evidence | Reproduce | Layer |
| --- | --- | --- | --- | --- |
| S1000D `dmRef` relations sync into Neo4j and answer reverse-dependency impact queries | — (behavioural, tested) | [src/learnarken/graph/store.py](../src/learnarken/graph/store.py) (`impact`); [tests/test_day9_evidence.py](../tests/test_day9_evidence.py) | `learnarken graph impact <DMC>` *(needs services)* | `Toy-scale` |
| Impact traversal is cycle-safe against VIO-7 reference loops and depth-bounded | — (tested) | [tests/test_day9_evidence.py](../tests/test_day9_evidence.py) | `uv run pytest tests/test_day9_evidence.py -q` | `Implemented` |

## Graph-augmented retrieval (Day 11)

| Claim | Number(s) | Evidence | Reproduce | Layer |
| --- | --- | --- | --- | --- |
| A third RRF route (deterministic entity linking → `REFS` graph expansion) is fused with BM25 + dense — **candidate expansion**, no LLM on the graph path | — (behavioural, tested) | [src/learnarken/retrieval/graph_expand.py](../src/learnarken/retrieval/graph_expand.py); [src/learnarken/retrieval/entity_link.py](../src/learnarken/retrieval/entity_link.py); [tests/test_day11_graph_expand.py](../tests/test_day11_graph_expand.py) | `uv run pytest tests/test_day11_graph_expand.py -q` | `Implemented` |
| The graph route's benchmark contribution is **honestly flat**: on the toy multi-hop set its post-rerank ablation is identical to plain hybrid — shipped as a KG-RAG capability, not a benchmark gain | — (deterministic ablation, flat) | [eval/results/day11-ablation.json](../eval/results/day11-ablation.json) (`multihop_set.results`); [docs/tutorials/14-kg-rag.md](tutorials/14-kg-rag.md) | `learnarken eval ablation --modes hybrid-graph hybrid-graph-rerank --json` *(needs services)* | `Toy-scale` |

## Multimodal figure ingest & second-look (Day 12)

| Claim | Number(s) | Evidence | Reproduce | Layer |
| --- | --- | --- | --- | --- |
| Synthetic ICN figures are described by a VLM into a schema-constrained structure, mechanically diffed against the DM-declared hotspot set, and bound to the image by SHA-256 | — (behavioural, tested) | [src/learnarken/multimodal/ingest.py](../src/learnarken/multimodal/ingest.py); [samples/package-a/icn/](../samples/package-a/icn/) (`*.describe.json` + `.png`) | `uv run pytest tests/test_day12_multimodal.py -q` | `Toy-scale` |
| A figure's description is re-bindable: re-render the SVG, recompute SHA-256, re-describe, diff the committed record | — (behavioural) | [tools/gen_figures.py](../tools/gen_figures.py); [src/learnarken/multimodal/figures.py](../src/learnarken/multimodal/figures.py) | `uv run python tools/gen_figures.py` then diff the `.describe.json` sha256 | `Toy-scale` |
| Figure chunks join the same index/query/verification corpus and are cited as `[ICN-…, Hotspot NN]` | — (behavioural, tested) | [src/learnarken/retrieval/__init__.py](../src/learnarken/retrieval/__init__.py) (`corpus_chunks`); [src/learnarken/answer/engine.py](../src/learnarken/answer/engine.py) (`_figure_ref`) | `uv run pytest tests/test_day12_multimodal.py -q` | `Toy-scale` |
| Out-of-description visual questions fail closed via a G15 second-look consensus refusal, never fabricate | — (behavioural, tested) | [src/learnarken/answer/figure_relook.py](../src/learnarken/answer/figure_relook.py); [src/learnarken/multimodal/second_look.py](../src/learnarken/multimodal/second_look.py) | `uv run pytest tests/test_day12_multimodal.py -q` | `Toy-scale` |

## Engineering discipline (cross-cutting)

| Claim | Evidence | Reproduce | Layer |
| --- | --- | --- | --- |
| Every README number has a fixed seed + versioned golden set + repro command (INV-5) | this file; [eval/golden/](../eval/golden/) | `uv run pytest tests/test_day9_evidence.py -q` | `Implemented` |
| AI-first workflow with independent red-team + human adjudication | [docs/AI-COLLABORATION.md](AI-COLLABORATION.md); [docs/reviews/](reviews/) | read the review files | `Implemented` |
| Fail-closed ingestion gate rejects non-compliant / out-of-domain modules | [tests/test_validation.py](../tests/test_validation.py); [samples/package-b](../samples/package-b) | `uv run learnarken validate samples/package-b` | `Implemented` |
| Multiprocessing validation sharding is byte-equivalent to the serial baseline (INV-2 — sharding behind an abstraction, no shared-memory shortcut) | [src/learnarken/validation/parallel.py](../src/learnarken/validation/parallel.py); [tests/test_day13_perf.py](../tests/test_day13_perf.py) | `uv run pytest tests/test_day13_perf.py -q` | `Implemented` |
| Full test suite green | [tests/](../tests/) | `make test` | `Implemented` |

## What is *not* claimed (honest boundary, INV-7)

- Distributed deployment is **simulated** on one machine (INV-2) — interfaces are
  designed as-if-distributed, but no multi-node run exists.
- Latency numbers describe the dev machine only (constitution §2); no production SLO.
- "Compliant" is judged by this project's own validator — **no expert ground
  truth** (constitution §2 known limitation).
- Version/issue-semantics graph, full RDF/SPARQL platform, and production serving
  are `Planned` — design notes only, see [docs/execution-plan.md](execution-plan.md).
- **Graph-augmented retrieval (Day 11) claims no ranking gain.** The third RRF
  route is implemented, but on the toy corpus its contribution is absorbed by the
  cross-encoder rerank, so the post-rerank ablation is flat — an honest null. The
  value is the KG-RAG mechanism and its deterministic entity linking, not a number.
- **The performance day (Day 13) claims no speedup.** Multiprocessing sharding is
  byte-equivalent to the serial baseline (above) but shows no wall-clock gain at
  toy-corpus scale — end-to-end time is dominated by external model inference and
  already-native parsing, not Python CPU. ToT best-of-N repair yields no quality
  improvement at roughly 2.76× token cost. numba, self-written Rust/PyO3, and
  Python free-threading are held as **evidence-gated non-actions** — the profiler
  shows no target on this corpus ([docs/adr/0003-day13-rust-gate.md](adr/0003-day13-rust-gate.md)).
