# Day 3 SPEC — Chunking, BM25 Baseline & Retrieval Eval (v0.3.0)

> **Authorship note (INV-6)**: the decision layer below was dictated by
> Yi Xin in the 2026-07-14 working session (in Chinese); AI transcribed and
> translated it with content unchanged (see docs/discussions/day3.md for the
> full option analysis). The Interfaces section is AI-drafted.
> **Status: APPROVED by Yi Xin, 2026-07-14** — open questions Q1–Q4 were
> adjudicated in the same session (answers transcribed in "Adjudicated
> decisions" below); implementation authorized on that reply.

## Goal (one sentence) — [HUMAN, transcribed]

Chunk the sample packages with a structure-aware strategy (recursive as
control), index and query them with BM25, and prove retrieval quality with a
human-annotated golden set and reproducible Recall@k / MRR / nDCG numbers,
tagged `v0.3.0`.

## Key Decisions — [HUMAN, transcribed from the 2026-07-14 session]

1. **Three chunking strategies will be compared in this project**:
   recursive, semantic, structure-aware. Day 3 delivers **structure-aware +
   recursive**; **semantic moves to Day 4** (it needs the embedding model
   that arrives with dense retrieval).
2. **Chunk metadata is designed from the project's scenarios**, including:
   - **紧急场合 (urgency)** = the chunk's content contains danger warnings —
     modeled as hazard flags (`has_warning` / `has_caution`);
   - **排除场合 (exclusion)** = applicability-based filtering — chunks carry
     the Day 2 structured assertions so queries can exclude inapplicable
     models/variants (package-c is the test input).
3. **Vector database = Vespa**, run via docker (docker already installed and
   running). Chosen with ColBERT-class late-interaction storage requirements
   explicitly in mind; paper decision today, implementation Day 4. This
   supersedes the execution plan's "Qdrant" mention for Day 4 (plan
   amendment to be approved with the Day 4 spec).
4. **Graph store = Neo4j**, via docker. Store decided now; whether/when a
   minimal graph query enters the slice stays with the Day 4 re-evaluation
   checkpoint. Day 3 only guarantees chunks carry the graph hooks
   (DMC, dmRefs, ICN refs).
5. **Backlog recorded**: real S1000D already defines structure; direct
   S1000D→graph-database mappings exist in industry. This project keeps
   traditional RAG chunking due to scope/data limits; noted in the README
   Roadmap (Planned) now and expanded in the Day 4 ADR; revisit if time
   allows.
6. **Basic testing** = human golden set + retrieval metrics, plus storage
   sanity tests (count reconciliation, deterministic chunk IDs, metadata
   round-trip, applicability-exclusion filter test).

## Interfaces — [AI-DRAFTED, pending review]

### Module layout

```text
src/learnarken/
  chunking/
    __init__.py   # chunk_package(package, strategy) -> list[Chunk]
    base.py       # Chunk model + deterministic chunk_id
    structure.py  # structure-aware: step/warning/description boundaries
    recursive.py  # recursive character splitter (control; no new deps)
  retrieval/
    __init__.py   # build_index / search
    bm25.py       # rank-bm25 wrapper + identifier-preserving tokenizer
    evaluate.py   # Recall@k, MRR, nDCG over the golden set
eval/
  golden/day3.jsonl   # versioned human annotations
```

### Chunk model (Pydantic)

```python
class Chunk(BaseModel):
    chunk_id: str            # sha1(dmc | source_path | strategy) — stable across runs
    strategy: str            # "structure" | "recursive"
    dmc: str
    dm_title: str
    issue_info: str
    chunk_type: str          # step | warning | caution | description | fault | ipd
    source_path: str         # XPath into the source DM (anchor for golden set)
    text: str
    applicability: Applicability | None   # Day 2 model: display + assertions
    security_classification: str | None
    effective_date: date | None
    expiry_date: date | None
    has_warning: bool        # 紧急场合 flags (decision 2)
    has_caution: bool
    outbound_dm_refs: list[str]   # graph hooks (decision 4)
    icn_refs: list[str]
```

- Structure-aware boundaries: one chunk per procedural step (a warning/caution
  *inline to that step* is folded in and sets the hazard flag); each *preliminary*
  reqSafety warning/caution is its own standalone chunk (not merged into the
  steps it guards); preliminary conditions/support equipment → `precondition`
  chunks and close requirements → a `closeout` chunk (no procedural content
  dropped); description sections split at paragraph level.
- Recursive control: fixed-size character windows with overlap
  (~800 chars / 100 overlap), same metadata inherited from the containing DM;
  `source_path` = the DM root plus a window ordinal.
- Tokenizer rule (tutorial 02's top lever): DMC strings, ICNs, and part-like
  identifiers are preserved as single tokens — never shredded on `-`.

### CLI

Day 3 adds three subcommands to the existing tree (`validate`, `dm` from
Day 2). Conventions inherited from Day 1/2: human-readable output by default,
`--json` for machine output, exit `2` = "not a package". No new global flags.

```text
learnarken chunk  <package-dir> [--strategy structure|recursive] [--dm DMC] [--json]
learnarken search <package-dir> "<query>" [--strategy structure|recursive]
                                          [-k N] [--applies-to KEY=VALUE ...] [--json]
learnarken eval retrieval [--golden PATH] [--k 5 10] [--strategy STRAT] [--seed N] [--json]
```

#### `learnarken chunk` — split a package into chunks

| Arg / option | Default | Meaning |
| --- | --- | --- |
| `<package-dir>` | — | package to chunk (required) |
| `--strategy` | `structure` | `structure` or `recursive` |
| `--dm DMC` | all DMs | chunk only this one DM (debugging aid) |
| `--json` | off | emit full `Chunk` objects instead of the summary table |

- **Exit codes**: `0` success · `2` not a package.
- **Human output**: one row per chunk + a trailer. Flags column shows `⚠W`
  (has_warning) / `⚠C` (has_caution); applic column shows the assertion
  summary or `—`.

  ```text
  CHUNK_ID  DMC                                    TYPE     FLAGS  APPLIC          TEXT
  a1b2c3d4  DMC-LA100-A-29-10-00-00A-520A-A        step     ⚠W     serial 1-50     Discharge the accumulator…
  e5f6a7b8  DMC-LA100-A-29-10-00-00A-520A-A        warning  ⚠W     —               Nitrogen under pressure…
  …
  24 chunks from 6 DMs · strategy=structure · 3 carry hazard flags
  ```

- **JSON output**: `[ <Chunk>, … ]` — every field of the `Chunk` model above.

#### `learnarken search` — BM25 query over the chunked package

| Arg / option | Default | Meaning |
| --- | --- | --- |
| `<package-dir>` | — | package to index and search (required) |
| `<query>` | — | free-text query (required) |
| `--strategy` | `structure` | which chunking feeds the index |
| `-k`, `--top-k` | `10` | number of ranked results |
| `--applies-to KEY=VALUE` | none | **排除场合 filter** (kept on the CLI — Yi Xin, 2026-07-14) — drop chunks whose applicability assertions exclude this context (e.g. `--applies-to variant=B`, `--applies-to serialNumber=0032`); repeatable, AND-combined |
| `--json` | off | machine output |

- Builds the BM25 index **in-process** each call (corpus is tiny; no
  persistence today — see Out of Scope). Tokenizer preserves identifiers
  (see concept #1 below).
- `--applies-to` filtering happens **before** scoring: a chunk carrying a
  structured assertion that excludes the given context is removed from the
  candidate set; chunks with no assertion on that property are kept (absence
  of exclusion = applicable). This is the executable form of 排除场合.
- **Exit codes**: `0` success (even on zero hits) · `2` not a package.
- **Human output**:

  ```text
  RANK  SCORE  DMC                                    TYPE  SOURCE_PATH               TEXT
  1     8.42   DMC-LA100-A-29-10-00-00A-520A-A        step  …/mainProcedure/step[2]   Discharge the accumulator…
  2     6.10   DMC-LA100-A-29-10-00-00A-520A-A        warn  …/reqSafety/warning[1]    Nitrogen under pressure…
  query="discharge accumulator" · strategy=structure · k=10 · 2 hits · filters: none
  ```

- **JSON output**: `[ {"rank": 1, "score": 8.42, "chunk": <Chunk>}, … ]`.

#### `learnarken eval retrieval` — reproducible retrieval metrics

| Arg / option | Default | Meaning |
| --- | --- | --- |
| `--golden PATH` | `eval/golden/day3.jsonl` | versioned human golden set |
| `--k` | `5 10` | one or more cut-offs for Recall@k |
| `--strategy STRAT` | both | limit to one strategy, else runs `structure` + `recursive` |
| `--seed N` | fixed (e.g. `42`) | seeds any nondeterministic step; pinned for reproducibility |
| `--json` | off | machine output |

- Runs each strategy over the same golden set and prints the comparison
  table (rows: strategy; columns: Recall@5, Recall@10, MRR, nDCG@10). The
  package(s) to chunk are inferred from the `dmc` anchors in the golden set.
- **Exit codes**: `0` success · `1` golden set missing/malformed.
- **Human output**:

  ```text
  Retrieval eval · golden=eval/golden/day3.jsonl (34 queries) · seed=42
  STRATEGY    Recall@5  Recall@10  MRR    nDCG@10
  structure     0.79      0.91     0.74    0.81
  recursive     0.62      0.78     0.55    0.64
  ```

- **JSON output**:

  ```json
  {"golden": "eval/golden/day3.jsonl", "n_queries": 34, "seed": 42,
   "results": {
     "structure": {"recall@5": 0.79, "recall@10": 0.91, "mrr": 0.74, "ndcg@10": 0.81},
     "recursive": {"recall@5": 0.62, "recall@10": 0.78, "mrr": 0.55, "ndcg@10": 0.64}}}
  ```

(All numbers above are **illustrative placeholders** — the real figures are
produced by the run and go into the README benchmark table + release notes.)

### Golden set format (annotation is HUMAN-only)

```json
{"query_id": "Q001", "query": "How do I discharge the accumulator safely?",
 "relevant": [{"dmc": "DMC-LA100-A-29-10-00-00A-520A-A",
               "source_path": "…/mainProcedure/step[2]"}],
 "notes": "hazard step; warning must rank"}
```

- Relevance is annotated at the **(DMC, source_path) anchor** level, not at
  chunk-id level — one annotation serves both strategies (a chunk is
  relevant if it contains, or is contained by, an annotated anchor).
- AI drafts 50–60 candidate queries covering: procedural how-tos,
  identifier/part-number lookups, warning/hazard questions,
  applicability-conditional questions, and a few no-answer traps.
  **Yi Xin selects and annotates 30–50** — this is the human red line.

### Storage sanity tests (decision 6)

- Chunk-count reconciliation per DM (every step/warning accounted for,
  nothing double-emitted).
- `chunk_id` determinism: two runs produce identical id sets.
- Metadata round-trip: model → chunk → JSON → model, lossless.
- Exclusion filter: filtering package-c chunks by a variant/serial assertion
  provably removes the inapplicable chunks and keeps the rest.

## Acceptance Criteria — [AI-assembled from execution-plan Day 3 + the
2026-07-14 decisions; pending approval]

- [ ] `learnarken chunk` works on package-a and package-c with both
      strategies; package-c chunks carry structured applicability assertions
- [ ] Hazard flags set correctly on chunks containing warnings/cautions
- [ ] Graph hooks populated: chunks referencing other DMs / ICNs list them
- [ ] Storage sanity tests pass (all four families above)
- [ ] Golden set: ≥ 30 human-annotated pairs, versioned in `eval/golden/`
- [ ] `learnarken eval retrieval` reproducible (fixed seed, versioned golden
      set); structure vs recursive comparison table generated
- [ ] README gains the first benchmark table (BM25 × two chunking rows) and
      a Roadmap Planned line for direct S1000D→graph-DB mapping (decision 5)
- [ ] CI green; feature branch → PR → squash merge → tag `v0.3.0` with
      release notes carrying the day's numbers

## Explicitly Out of Scope (today) — [AI-DRAFTED, pending approval]

- **No semantic chunking, no embeddings** (Day 4, per decision 1). Provider
  for Day 4 embeddings is now fixed to **MiniMax** (2026-07-14 instruction;
  config + special `X-Proxy-Token` impl in docs/local-services.md,
  discussion D8) — but no embedding code is written today.
- **No Vespa deployment** — selection recorded only; docker compose lands
  Day 4 (decision 3)
- **No Neo4j, no triple export** — store selected; build gated on the Day 4
  checkpoint (decision 4)
- No RRF fusion, no reranking (Day 4); no answer generation (Day 5)
- No LLM calls anywhere in today's pipeline
- No index persistence layer — in-process BM25 rebuild per command is
  acceptable at this corpus size

## Adjudicated decisions on Q1–Q4 — [HUMAN, transcribed from Yi Xin's
2026-07-14 reply]

1. **Q1 — rank-bm25.**
2. **Q2 — accepted.** Recursive control at 800 chars / 100 overlap.
3. **Q3 — accepted.** Golden-set queries EN-only, with the honest note in
   the README.
4. **Q4 — adjusted from the recommendation.** execution-plan.md is amended
   **now** (edited 2026-07-14: Day 4 dense-retrieval line, Qdrant → Vespa).
   Additionally directed: pull the Vespa and Neo4j docker containers up on
   the dev machine **today** (environment prep only — compose files and any
   in-repo deployment remain Day 4, per Out of Scope).

## Risks & Open Questions — [adjudicated above; original questions kept for
the record]

- **Q1 — BM25 library.** *Recommendation:* `rank-bm25` (pure Python, zero
  infra, trivially inspectable — fits a baseline whose job is to be
  understood). Alternative: Tantivy (faster, closer to production, adds a
  Rust wheel). Note: Vespa itself ships BM25 — whether Day 4 re-homes the
  baseline into Vespa or keeps it in-process for ablation comparability is a
  Day 4 spec question.
- **Q2 — Recursive splitter parameters.** ~800 chars / 100 overlap proposed
  above; any preference, or accept and let the eval table judge?
- **Q3 — Golden-set query language.** Samples are EN; queries drafted in EN.
  Confirm, or should a few zh queries be included (would drag in
  cross-lingual issues BM25 can't handle — recommend EN-only today, honest
  note in README)?
- **Q4 — execution-plan.md amendment** (Qdrant → Vespa on Day 4): approve
  editing that line now, or defer the edit to the Day 4 spec session?
  *Recommendation:* defer, keep plan edits batched with their day.

## The 3 tutorial concepts to verify during implementation:

1. **分词管线中的标识符完整性 (Identifier Preservation in Tokenizer)**
   验证在自定义分词器中，DMC、ICN 等特有编码在建立倒排索引和查询解析时被视为不可分割的整体，防止其被标点符号（如 `-`）切碎，从而保障精确匹配场景下的极高 IDF 得分。
2. **检索指标在 RAG 上下文中的分工 (Retrieval Metrics Division for RAG)**
   验证 Recall@k 是决定下游生成质量的天花板（若未召回则 LLM 无法参考），而 nDCG@k 和 MRR 则反映了排序质量。在自建 Golden Set 上分别运行两套分块策略，对比两者的各项指标差异。
3. **检索优化的收益杠杆排序 (Leverage Ranking of Retrieval Optimizations)**
   验证对于技术手册这类高垂直、高精确度领域，分词器修正和结构化分块边界的收益杠杆（通常可提升 ~10+ 个 nDCG/Recall 点）远高于对 BM25 超参数 k1/b 的网格搜索微调（通常仅有 ~1-3 点的稀疏提升）。

### 1. Tokenization Protection for Identifiers

- **Means** (tutorial 02 §1, §8, failure mode 1): a standard analyzer splits
  on punctuation, so a DMC like `DMC-LA100-A-29-10-00-00A-520A-A` or a part
  number `P/N 1234-567` shatters into meaningless fragments — then querying
  `P-1002` drags in every doc containing a bare `1002`. Identifier fields
  must be tokenized as **keyword** (whole-token), not shredded on `-` or `/`.
  This is the single highest-leverage IR fix in a technical corpus.
- **Verify during Day 3**: a dedicated tokenizer test — feed a DMC / ICN /
  part number, assert it survives as **one** token; then an end-to-end
  `search` test where a DMC query returns the exact DM and does **not**
  return unrelated DMs that merely share a numeric fragment. This is the
  `bm25.py` "identifier-preserving tokenizer" line in the module layout.

### 2. Prioritization of Retrieval Metrics for RAG

- **Means** (tutorial 02 §4 实践口诀): the three metrics answer different
  questions — **Recall@k is first for RAG** because the LLM can only ground
  on evidence that made it into the top-k context window (evidence not
  recalled can never appear in the answer); **nDCG** judges overall ranking
  quality (graded relevance + position discount); **MRR** fits single-answer
  scenarios. k should equal the number of chunks we plan to feed downstream.
- **Verify during Day 3**: `evaluate.py` computes all three, but the eval
  table and README lead with **Recall@k** (k = the future context budget),
  with nDCG@10 as the ranking-quality column; MRR reported but framed as
  secondary. Sanity check the implementations against hand-worked tiny cases
  (e.g. one relevant doc at rank 3 → MRR = 1/3, Recall@5 = 1.0).

### 3. Leverage Ranking of Retrieval Optimization

- **Means** (tutorial 02 §6): optimization effort has a stable payoff order —
  analyzer/chunking (≈10+ nDCG points, can be 0-vs-full on identifier
  queries) ≫ hybrid + rerank (≈5–15) > field weighting (a few) > k1/b grid
  search (≈1–3). "Fix the tokenizer and chunking first; k1/b last" — doing it
  backwards is polishing the trigger on a gun with no sights.
- **Verify during Day 3**: this is *why* Day 3 spends its whole budget on
  chunking + tokenizer and leaves k1/b at library defaults (documented, not
  tuned). The structure-vs-recursive eval table is the empirical proof of the
  top lever; a note in the README records that k1/b tuning is deliberately
  deferred as low-leverage (revisited only if Day 4's ablation says so).
