# SPEC — Day 11: Graph-Augmented Retrieval / KG-RAG (`v1.1.0`)

> Decision layer **transcribed from Yi Xin's written instructions** (2026-07-19
> session message: 实体链接器 / 图谱检索扩展 / 多跳评估集三点要求), grounded in
> the already-adjudicated Day 11–13 planning decision
> ([docs/discussions/day11-13-planning.md](../discussions/day11-13-planning.md)
> Decision 1). Goal and Key Decisions are [HUMAN, transcribed]; Interfaces /
> Acceptance / Out-of-Scope / Verification are **AI-drafted, pending approval**
> (Day 6–10 labeling precedent). Nothing in the decision layer is AI-invented.
>
> **Daily-cycle note.** Step 1c 扫
> ([docs/research/day11-unknowns.md](../research/day11-unknowns.md)) was
> completed **before** this SPEC. Its tensions T1–T8 feed the elaboration layer
> below: T1 (deterministic virtual ranking), T2 (degree cutoff, no PPR), T6 (no
> harness rewrite), T7 (graph in the index pipeline), T8 (deterministic-only
> linking) are resolved by elaboration-layer 裁法 already written in the scan;
> T3 (refusal regression gate) and T5 (old-set ceiling) are pinned into
> Acceptance; **T4 (multi-hop authoring circularity) contains one open question
> for Yi Xin** — see "Open question" below the Key Decisions.
>
> **Schema note — RULED (Yi Xin, 2026-07-19: "使用 :REFS").** The instruction
> originally named the traversal edge **`CITES`（引用/依赖）**; the edge that
> exists in the repo's Neo4j schema is **`:REFS`** (`(:DM)-[:REFS]->(:DM)` from
> `dmRef`, Day 9, [store.py:9](../../src/learnarken/graph/store.py#L9)) — same
> semantics (citation/dependency). Ruling: Day 11 **traverses the existing
> `:REFS` edge; no rename.**
>
> **Constitutional note.** INV-5 governs determinism (the entire graph route —
> linking, expansion, ranking — must be reproducible with zero randomness);
> INV-4 governs fail-closed behavior (unlinkable entity ⇒ no graph signal,
> never a guess; the refusal-rate regression gate is this day's most important
> safety check); INV-2 governs idempotent graph sync inside the index pipeline;
> INV-8 governs slippage (the multi-hop golden set is the first slice cut back
> to a smaller n if the day overruns — the retrieval path itself is not
> cuttable).

## Goal (one sentence) — [HUMAN, transcribed 2026-07-19]

Build a **query-side deterministic entity linker** (regex + lexicon, no LLM)
that extracts DMC, part-number, and task entities from the query; implement
**graph expansion** — traverse the extracted entity nodes 1–2 hops along the
Neo4j citation/dependency edges (`CITES` per instruction ⇒ in-repo `:REFS`)
and fuse the expansion candidates as a **third signal** into RRF alongside
dense vector retrieval and BM25; **create a new evaluation set containing
cross-module multi-hop QA** (answers spread across multiple Data Modules
connected by a citation chain) and run the ablation comparing `hybrid` vs
`hybrid+graph` on **Recall@k, nDCG, zero-hit, p50**, **honestly reporting both
the gains and the neighbor noise** — tagged `v1.1.0`.

## Key Decisions — [HUMAN, transcribed from the 2026-07-19 instructions + the adjudicated planning discussion]

1. **Entity linking is deterministic-only: 正则 + 词表, 无需 LLM.** The linker
   extracts DMC, part-number, and task entities from the query using regex and
   corpus-derived lexicons. No LLM call anywhere in the linking path. (NER/LLM
   fallback is explicitly out of scope — planning Decision 1 "实体链接
   (确定性优先)"; scan T8.)

2. **Graph expansion is a third RRF route, 1–2 hops along the citation edges.**
   Linked entity nodes are expanded 1–2 hops along `:REFS` (the instruction's
   `CITES` — see schema note), and the expansion candidates enter fusion as a
   third ranked signal beside dense and BM25, inside the existing RRF
   framework. Candidate **expansion**, not score reweighting — the point is
   rescuing chunks that are not in the semantic/lexical candidate pool at all
   (tutorial 14 §2).

3. **New multi-hop golden set, new/old reported separately.** The evaluation
   set is supplemented with a **new** set of cross-module multi-hop questions
   whose answers span multiple DMs connected by reference chains. Old golden
   sets are untouched; new and old questions are scored and reported
   **separately** (planning Decision 1 "多跳 golden 题新旧分开报分"; scan T5:
   the old set's ceiling is already at 1.00 — it guards regression, the new
   set is where any gain can show).

4. **Ablation adds `hybrid+graph` and reports honestly, 涨平都如实报.** The
   ablation table gains a `hybrid+graph` row compared against `hybrid` on
   Recall@k, nDCG, zero-hit, and p50. Gains **and neighbor noise** are both
   reported; a flat result is a valid, publishable conclusion ("at this scale
   the graph route adds no retrieval gain; its value is citation-path
   explainability" — planning 理由, Day 8 evaluation discipline).

5. **No RDF/SPARQL, no GraphRAG.** The full-graph platform stays Planned
   (planning Decision 1; ADR-0002 boundary). This day reuses the Day 9
   citation graph and the Day 4 RRF framework — maximum-reuse slice.

### Open question — RULED (Yi Xin, 2026-07-19): option (a)

Yi Xin authors the multi-hop questions directly, blind to the edge list;
the authoring worksheet is
[eval/golden/day11-multihop.worksheet.md](../../eval/golden/day11-multihop.worksheet.md)
(human-written content; AI afterwards only verifies anchors and formats into
`day11-multihop.jsonl`). Original question kept below for provenance.

<details><summary>Original open question (as drafted before the ruling)</summary>

Scan T4 rules that to avoid evaluation circularity ("按边出题 = 裁判偏向图路"),
the multi-hop questions must be authored **from maintenance-scenario intent,
blind to the edge list**, and the authoring process documented in the golden
README. The established pipeline (Day 3/4) has AI drafting
`*.candidates.jsonl` for human curation — but an AI drafter has seen the graph
structure, which weakens the blindness guarantee. **Pick one:**

- **(a) Yi Xin authors the questions directly** from business scenarios
  without consulting the edge list; AI only formats/validates anchors
  afterwards. Strongest anti-circularity; costs Yi Xin ~30–60 min.
- **(b) AI drafts candidates from scenario templates** (not from edge
  enumeration), Yi Xin curates; the README discloses the residual circularity
  risk and the red team is invited to attack it. Cheaper, weaker.

The elaboration below assumes **(a)** as the default (matches the T4 裁法 as
written); switch to (b) only by explicit ruling.

</details>

---

## Interfaces — [AI-drafted, pending approval]

### 1. `src/learnarken/retrieval/entity_link.py` — deterministic entity linker

- `link_entities(query: str, lexicon: EntityLexicon) -> list[LinkedEntity]`
  where `LinkedEntity` is a Pydantic model: `{surface, kind: dmc|part|task,
  node_key}`. Pure function, no I/O, no LLM.
- **DMC**: regex over the S1000D DMC syntax as it appears in the corpus
  (`DMC-LA100-…`), tolerant of the `DMC-` prefix being present or absent.
- **Part numbers**: matched against a **lexicon built at index time** from
  `<partRef partNumberValue="…">` occurrences in the ingested packages (e.g.
  `LA-29-4711-9`) — lexicon match, not a naked `[A-Z0-9-]+` regex, so free
  text cannot false-positive into a part entity.
- **Task entities**: lexicon of task/procedure vocabulary derived at index
  time from DM titles (`techName`/`infoName`) of procedural modules; longest-
  match, case-insensitive.
- **Existence check, fail-closed (INV-4)**: every candidate link is verified
  against the graph (`GraphStore`); an entity with no graph node yields **no
  graph signal** (and is recorded in the trace as `unlinked`), never a fuzzy
  guess. Neo4j unreachable ⇒ the graph route contributes nothing and the
  answer path degrades to plain `hybrid` **with the degradation recorded in
  the trace** — retrieval itself does not refuse (the graph route is additive;
  refusal semantics stay in the answer layer).
- Lexicons are serialized alongside the corpus manifest at `learnarken index`
  time (T7: same-ingest provenance, INV-2 idempotent).

### 2. `src/learnarken/retrieval/graph_expand.py` — expansion as a Retriever

- Wraps expansion as a LangChain `BaseRetriever` so it can slot into the
  existing `EnsembleRetriever` unchanged
  ([hybrid.py:48](../../src/learnarken/retrieval/hybrid.py#L48)).
- **Traversal**: from each linked node, per-hop BFS along `:REFS`, depth ≤ 2,
  visited-set de-duplicated (cycle-safe by construction — same pattern as the
  Day 9 impact walk, VIO-7-proof). **Both directions** (cites and cited-by)
  are traversed; direction is recorded per candidate so the red team can probe
  direction semantics (scan "不知道自己不知道" #1).
- **Virtual ranking (T1 裁法)**: hop-0 (the linked DM's own chunks) ranks
  first, then hop-1, then hop-2; **within a hop, ordering is by the
  deterministic double key (edge-type priority, chunk id)** — zero randomness,
  same query twice ⇒ byte-identical candidate list (INV-5).
- **Hub guard (T2 裁法)**: static `is_hub` degree threshold computed at index
  time + edge-type whitelist; hub nodes are traversed *through* but their
  full neighborhoods are truncated at a fixed per-node fan-out cap. **No PPR**
  (Roadmap, with its documented trigger condition: >10⁴ nodes and cutoff
  visibly costing R@k).
- Node→chunk mapping reuses the existing DMC→chunk metadata; a DM node whose
  chunks are absent from the index contributes nothing (manifest consistency,
  T7).

### 3. Fusion — third route in the existing RRF

- `hybrid_retriever(...)` gains an optional graph route: `EnsembleRetriever`
  over `[bm25, dense, graph]` with weights `[w, w, w_graph]`, same `c=60`. RRF
  natively handles the same chunk arriving from multiple routes (contributions
  sum) — no bespoke dedup rule needed; this is stated in the module docstring
  (scan "不知道自己不知道" #3).
- New mode names follow the existing ablation convention
  (`hybrid`, `hybrid-rerank` → **`hybrid-graph`, `hybrid-graph-rerank`**);
  report tables may label them `hybrid+graph`. Running both rows doubles as
  the DR §4.1 pre/post-rerank dual measuring point with **zero harness
  changes** (T6 裁法).
- Answer-layer traces record the graph route's linked entities, hops, and
  per-candidate provenance — the citation-path explainability artifact.

### 4. Graph build joins `learnarken index` (T7)

- Graph sync (existing `GraphStore` MERGE-based sync) is invoked from the same
  `learnarken index` pipeline that builds BM25/dense indices and the corpus
  manifest, so index and graph always come from the same ingest. The
  standalone graph-build entry (if any remains) is removed from the documented
  path. Manifest records the graph node/edge counts for drift detection.

### 5. `eval/golden/day11-multihop.jsonl` (+ README section) — multi-hop set

- Same schema as existing golden sets (anchors resolved via
  `resolve_anchors`); a multi-hop item's anchors live in ≥ 2 distinct DMs
  connected by a `:REFS` chain, plus `hops` metadata for reporting.
- Authored per **ruling (a)**: Yi Xin writes the questions from maintenance
  scenarios, blind to the edge list, into
  [eval/golden/day11-multihop.worksheet.md](../../eval/golden/day11-multihop.worksheet.md);
  AI then verifies each item's answer really spans ≥ 2 reference-connected DMs
  and formats anchors into the `.jsonl`.
- The golden README documents the authoring protocol verbatim (T4 anti-
  circularity provenance); if the corpus's reference density yields < 5 viable
  multi-hop items, the count is reported and the new-set rows are marked
  *indicative* (Day 4 precedent, scan "known-unknown" #3).
- No-answer traps: the new set includes multi-hop-flavored no-answer items
  (entity exists, neighbors exist, answer does not — tutorial 14 failure
  mode 5), feeding the T3 gate.

### 6. Ablation + results artifacts

- `learnarken eval ablation` grows the two new modes; frozen output at
  `eval/results/day11-ablation.json` (fixed seeds, INV-5), README table
  updated with old-set and new-set sections **reported separately**.
- Metrics per instruction: Recall@k, nDCG, zero-hit, p50 — all already emitted
  by `evaluate_strategy` / the ablation harness; no new metric columns (T6).
- A short `docs/notes/day11-neighbor-noise.md` (or README section) names the
  neighbor-noise observations honestly: candidates pulled in by structure that
  the reranker had to kill, zero-hit movement, latency cost.

### 7. `tests/test_day11_*.py`

- Linker: DMC / part / task extraction positives, near-miss negatives (free
  text that looks like a part number but is not in the lexicon), fail-closed
  on unknown entity, determinism.
- Expansion: cycle fixture (VIO-7-style), depth bound, hub truncation,
  deterministic ordering (two runs ⇒ identical list), Neo4j-down degradation
  to plain hybrid with trace record (live-Neo4j tests `skip` when the
  container is absent, mirroring existing graph tests).
- Fusion: `hybrid-graph` returns a superset-or-equal candidate pool vs
  `hybrid` on a fixture where the graph rescues an out-of-pool chunk.
- Golden set: schema validation + every multi-hop item's anchors actually span
  ≥ 2 reference-connected DMs.

## Acceptance Criteria — [AI-drafted, pending approval]

1. `link_entities` extracts DMC, part-number, and task entities from queries
   with **zero LLM calls** (asserted by test — no LLM client import in the
   linking/expansion path), and fails closed on unlinkable entities.
2. Graph expansion is depth-bounded (≤ 2), cycle-safe on a cyclic fixture, and
   **deterministic**: the same query yields a byte-identical ranked candidate
   list across runs (INV-5).
3. `hybrid-graph` (and `hybrid-graph-rerank`) run end-to-end; the ablation
   table shows `hybrid` vs `hybrid+graph` on **Recall@k, nDCG, zero-hit, p50**
   for the old set and the new multi-hop set, **reported separately**, frozen
   at `eval/results/day11-ablation.json`.
4. **Refusal regression gate (T3, most important safety check)**: on the
   no-answer traps (Day 8 adversarial no-answer items + the new multi-hop
   no-answer items), the refusal rate under `hybrid-graph` is **not lower
   than** the `hybrid` baseline.
5. **Old-set no-regression**: old-golden metrics under `hybrid-graph` do not
   drop below the `hybrid` baseline beyond noise (dense R@10=1.00 ceiling —
   flat is the expected pass).
6. Neighbor noise is honestly reported (notes/README): what the graph pulled
   in, what it cost (p50 delta), and a flat-gain conclusion stated plainly if
   that is what the data says.
7. The multi-hop golden README documents the authoring protocol per the T4
   ruling; if < 5 multi-hop items, new-set rows are marked *indicative*.
8. `make test` + `make lint` green; existing 327-test suite unbroken.
9. Cross-host `coding-adversarial-review` run on the day's diff, findings in
   `docs/reviews/day11.md` Part 1 (automatic gate, before proposing merge).

## Out-of-Scope — [AI-drafted, pending approval]

- **No LLM/NER entity-linking fallback, no natural-language coreference**
  (T8) — Roadmap, with the honest reason recorded: the synthetic corpus's
  entities are 100% strict-syntax, so a fallback tier is untestable here.
- **No PPR / graph-algorithm ranking** (T2) — Roadmap with an explicit
  "when it becomes worth it" trigger.
- **No RDF/SPARQL platform, no GraphRAG / community summaries** (Decision 5;
  ADR-0002).
- **No `:REFS` → `CITES` schema rename** (schema note) — separate decision if
  wanted.
- **No evaluation-harness restructuring / new metric columns** (T6) — the two
  mode rows are the dual measuring point.
- **No changes to answer-layer refusal logic** — the graph route feeds
  retrieval candidates only; evidence-sufficiency judgment stays where it is
  (its non-regression is *measured*, not re-engineered).
- **No re-tuning of RRF `c` or reranker parameters** — single-variable
  discipline: the only change under ablation is the added route.
- **AI does not author the multi-hop questions' decision content** under
  ruling (a); AI never touches `docs/journal/`; adjudication stays human.

## Verification (how to check) — [AI-drafted, pending approval]

```bash
make test && make lint                                   # 327 + day11 linker/expansion/fusion/golden tests green
uv run pytest tests/test_day11_entity_link.py tests/test_day11_graph_expand.py -q
learnarken index samples/package-a ...                   # index + graph + lexicons in one ingest (T7)
learnarken eval ablation --modes hybrid,hybrid-graph,hybrid-graph-rerank \
  --golden eval/golden/day4.jsonl,eval/golden/day11-multihop.jsonl
# → eval/results/day11-ablation.json; old/new reported separately; run twice, diff = empty (INV-5)
# T3 gate: re-run no-answer traps under hybrid-graph; refusal rate ≥ hybrid baseline
```

Then the automatic cross-host red-team gate on the diff →
`docs/reviews/day11.md` Part 1 → Yi Xin adjudicates (Part 2, human).
