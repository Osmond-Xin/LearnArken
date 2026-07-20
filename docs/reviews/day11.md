# Day 11 Red-Team Review — Graph-Augmented Retrieval (KG-RAG Slice)

> **Part 1 (below) is AI-written** (cross-host adversarial gate, CLAUDE.md
> step 4, launched automatically on green before proposing a commit). **Mode**:
> external = **Codex** (`codex exec --sandbox read-only`, the non-implementing
> model) cross-validated against the **Claude** host's own independent pass.
> **Part 2 (adjudication) is Yi Xin's** — accept/reject + rationale, and any
> red-team number is re-run by the human before merge (INV-6). AI does not
> write Part 2.
>
> **Process note (disclosed, not hidden):** per this project's established
> default — red-team findings get fixed the same day unless a human scopes
> them out (see [docs/discussions/redteam-fix-all-over-defer.md] precedent,
> Day 9) — the implementer applied fixes for all BLOCKERS and SHOULD-FIX
> findings **in this same session**, before Yi Xin's formal Part 2 ruling.
> This is a **deviation from the Day 9 sequencing** (there, fixes waited for
> the human's "全部修改" instruction). Flagging it explicitly: Yi Xin's Part 2
> below should be read as **ratifying or reverting already-applied fixes**,
> not authorizing fixes yet to be written. If any disposition should have been
> "defer" or "reject", say so and the implementer will revert.
>
> Scope: the Day 11 diff — `src/learnarken/retrieval/entity_link.py` (new),
> `src/learnarken/retrieval/graph_expand.py` (new),
> `src/learnarken/graph/store.py` (`neighborhood()`, corpus-authoritative
> `sync()`, `stats()`), `src/learnarken/retrieval/hybrid.py`
> (`graph_hybrid_retriever`), `src/learnarken/retrieval/__init__.py` (graph
> modes, ablation fail-closed gate), `src/learnarken/answer/engine.py` (graph
> trace span), `src/learnarken/cli.py` (ablation default), `tools/
> day11_refusal_gate.py` (new), `tools/gen_benchmark_tables.py` (day11 block),
> `tests/test_day11_*.py`, `eval/golden/day11-multihop.jsonl`. **Verdict as
> submitted to the reviewer: DO_NOT_MERGE** (graph provenance/staleness, seed
> bound, refusal-gate fail-closed and per-query gating). **All BLOCKER and
> SHOULD-FIX findings have since been fixed** — see the disposition table.
>
> Tags: `[cross-validated]` both caught · `[external-only]` Codex only ·
> `[host-only]` Claude only. On severity disagreement, the higher is taken.

## Part 1 — Findings (AI)

### BLOCKERS (P1)

**#1 Graph sync was append-only — stale edges/nodes from a previous ingest
survive and silently feed retrieval** `[cross-validated]` — `store.py`
`sync()` (MERGE-only, no cleanup); `retrieval/__init__.py` `verify_corpus()`
checked the Vespa manifest but nothing about the graph.
Problem: Day 11's spec (T7) promises the graph and index come from the same
ingest, but `MERGE` alone never removes a `REFS`/`USES_ICN` edge or a `DM`/
`ICN` node that the current chunk set no longer asserts. Scenario: index
A+C, then re-index a smaller corpus or one with an edge removed — the old
edge persists in Neo4j and can still boost a `hybrid-graph` candidate or
appear in `graph.facts()`, producing a fake graph gain or answer evidence
that no longer corresponds to the indexed corpus.
Recommendation: make `sync()` corpus-authoritative in the same transaction
(delete edges/nodes the current chunks no longer assert), and cross-check
live graph counts against the manifest before trusting a graph mode.

**#2 `neighborhood()` bounds discovered nodes, not the seed list itself**
`[cross-validated]` — `graph_expand.py` (seeds built from every linked
entity's `dmcs`, unbounded); `store.py` `neighborhood()` (`MAX_EXPAND_NODES`
caps *discovery*, not the `$frontier`/`$visited` payload sent to Neo4j).
Problem: a common task phrase or a DMC entity that maps to many corpus DMs
(the lexicon's `tasks` values are not size-bounded) could send a very large
seed list to Neo4j before any cap applies.
Recommendation: reject an over-broad seed list deterministically before it
reaches the wire, with an explicit bound.

**#3 The T3 refusal gate can pass with Neo4j down** `[cross-validated]` —
`tools/day11_refusal_gate.py` (no `graph.is_up()` check before building the
`hybrid-graph` retriever); `graph_expand.py` degrades `GraphError` to an
empty result by design (correct for the *search* path).
Problem: the search-path degradation is intentional, but the *refusal gate*
measuring it is not the search path — it exists specifically to test the
graph route's effect on refusal. If Neo4j is down, the gate silently measures
"hybrid vs. hybrid-with-an-empty-third-arm" and can still write a passing,
frozen artifact claiming the graph route was exercised.
Recommendation: fail closed up front, mirroring `run_ablation`'s
`GRAPH_MODES` check.

**#4 The refusal gate's pass criterion was aggregate-rate only** `[cross-
validated]` — `tools/day11_refusal_gate.py` (`refusal_rate` comparison,
`>=`).
Problem: a trap flipping from refuse to answer under `hybrid-graph` can be
exactly offset by a different trap flipping from answer to refuse, leaving
the aggregate rate unchanged and the gate green — hiding a real safety
regression.
Recommendation: gate on a **per-query** non-regression check (every trap
`hybrid` refuses must still be refused under `hybrid-graph`); keep the
aggregate rate as a reported summary only.

### SHOULD FIX (P2)

**#5 The Day 11 graph-explainability trace span was overwritten on every
answered query** `[host-only]` — `answer/engine.py`: `spans["graph"]` is set
once (pre-threshold-gate) with linked entities and per-candidate hop/
direction, then **reassigned** (not merged) after the threshold gate with
`interface-③` facts.
Problem: for any query that is not refused — i.e. exactly the case where
citation-path explainability matters most — the entity/candidate provenance
is lost from the written trace before it reaches disk. The Day 11
explainability claim ("traces carry linked entities and per-candidate hop/
direction") was false for answered queries.
Recommendation: merge into the existing span (`spans.setdefault("graph",
{})["facts"] = …`) rather than overwrite.

**#6 RRF de-duplication can silently drop the graph route's provenance
metadata** `[host-only]` — `hybrid.py` `graph_hybrid_retriever` (retriever
list order `[bm25, dense, graph]`); `EnsembleRetriever.weighted_reciprocal_
rank` de-duplicates documents by key, keeping the *first* object seen in
list order (score is unaffected — it sums contributions by key regardless
of order).
Problem: when the same chunk is returned by both BM25/dense and the graph
route, the surviving document object is whichever route was listed first —
originally BM25/dense, which carries no `graph_hop`/`graph_direction`. The
answer trace would then undercount the graph route's real contribution
(reads as "0 graph candidates" for a query where graph in fact influenced
the fused ranking).
Recommendation: list the graph retriever first so its annotated copy wins
the dedup; document why list order matters here (it is otherwise an
implementation detail nobody would think to preserve).

**#7 Malformed Neo4j responses in `neighborhood()` crash instead of failing
closed** `[external-only]` — `store.py` `neighborhood()` indexed
`row["row"][0]`/`row["row"][1]` without validating shape (same class of
issue as Day 9 #3, not re-fixed for the new code path).
Problem: a proxy or wrong service answering on `127.0.0.1:7474`, or a Neo4j
version returning a different row shape, raises `KeyError`/`TypeError`/
`IndexError` instead of the `GraphError` the search path is designed to
catch and degrade from — the query path 500s instead of degrading to
"no graph signal".
Recommendation: validate row shape and re-raise as `GraphError`.

**#8 README overclaimed "the refusal fence held" from a threshold-only
measurement** `[external-only]` — `README.md` Day 11 section wording.
Problem: the T3 gate measures only the first of the answer layer's three
fail-closed gates (threshold → citation → LLM contract); most adversarial
traps are actually caught downstream (Day 8). The original wording read as
an end-to-end safety claim the artifact does not support.
Recommendation: scope the claim to what was measured (the deterministic
threshold gate, per-query), and say plainly that end-to-end no-answer
safety under graph modes has not yet been re-run.

**#9 The pre-Day-11 `learnarken eval ablation` command silently gained a
Neo4j dependency** `[external-only]` — `cli.py` `ablation_parser --modes`
default was `list(MODES)`, which now includes the two Day 11 graph modes.
Problem: anyone (docs, muscle memory, a script) running the bare Day 4
command without `--modes` would now require Neo4j up, with no indication
why — a silent scope/dependency change to an existing, documented command.
Recommendation: keep the default to the pre-Day-11 mode set; graph modes are
opt-in via `--modes hybrid-graph ...`.

### NICE TO HAVE (P3)

**#10 Lexicon is rebuilt from scratch on every retriever construction and
again for the trace** `[external-only]` — `graph_expand.py`
`graph_expansion_retriever()` calls `build_lexicon(chunks)`; `engine.py`
calls it again for the trace span. Not a correctness issue at 43 chunks;
would be wasted work at scale. Recommendation: cache per corpus / persist a
lexicon artifact alongside the manifest if this ever matters.

**#11 More edge-case coverage suggested**: stale-graph cleanup, seed-cap
behavior, refusal-gate Neo4j-down refusal, and answer-trace provenance
preservation. Recommendation: hermetic tests for each (see disposition —
added for all four).

## Verdict

**DO_NOT_MERGE** as submitted — #1–#4 are real safety/honesty gaps in a
feature whose entire premise is "measure and report the graph route
honestly"; #5–#9 undermine the explainability and command-stability claims
the day's README section makes.

## Implementer's recommended disposition (advisory only — Yi Xin adjudicates)

Already applied this session (see disposition table) — flagged above as a
sequencing deviation from Day 9's precedent. My recommendation for Part 2:
- **#1–#4** — accept; all four are genuine gaps between what the spec/README
  claims and what the code actually guaranteed. Fixes are small, additive,
  and covered by new hermetic tests.
- **#5, #6** — accept; both are real bugs in the explainability feature this
  day exists to deliver, caught only by my own independent pass (Codex did
  not flag them) — worth double-checking in Part 2's re-run.
- **#7** — accept; mirrors the Day 9 #3 pattern exactly, same fix shape.
- **#8** — accept; wording-only, no behavior change.
- **#9** — accept; the alternative (updating every doc/script that assumes
  the old default) is more invasive for the same safety property.
- **#10** — no action recommended (correctly scoped as P3/toy-scale); noted
  in Roadmap-adjacent form only if this resurfaces at larger scale.

## Disposition table (fixes applied this session, pending Part 2 ratification)

| # | Sev | Fix applied |
| --- | --- | --- |
| 1 | P1 | `sync()` rewritten corpus-authoritative: deletes `REFS`/`USES_ICN` edges no longer asserted, `DETACH DELETE`s orphaned `DM`/`ICN` nodes, clears `package` on de-indexed DMs, all in the same transaction. New `graph.stats()` for live counts; `run_ablation` and `day11_refusal_gate.py` cross-check `stats()` against the manifest's recorded `graph` block before trusting a graph mode. `store.py`, `retrieval/__init__.py`, `tools/day11_refusal_gate.py` |
| 2 | P1 | `MAX_EXPAND_SEEDS = 25`; `neighborhood()` raises `ValueError` before querying Neo4j if the seed set exceeds it. `store.py` |
| 3 | P1 | `day11_refusal_gate.py` now calls `graph.is_up()` (and the manifest/stats cross-check from #1) before building `hybrid-graph`, raising `SystemExit` instead of silently measuring an empty arm. |
| 4 | P1 | Pass criterion is now per-query: `regressions = [q for q where hybrid refused and hybrid-graph did not]`; `pass = not regressions`. Aggregate rate kept as a reported summary only. `tools/day11_refusal_gate.py` |
| 5 | P2 | `engine.py` merges into `spans.setdefault("graph", {})["facts"]` instead of overwriting; new hermetic test drives `answer_question(mode="hybrid-graph")` end-to-end and asserts the written trace file has both `entities`/`candidates` and `facts`. `tests/test_day11_graph_expand.py::test_answer_trace_preserves_graph_span_alongside_facts` |
| 6 | P2 | `graph_hybrid_retriever`'s retriever list reordered to `[graph, bm25, dense]` (weights unchanged, still equal) with a docstring explaining why order matters for dedup provenance. `hybrid.py` |
| 7 | P2 | `neighborhood()` wraps row-shape access in try/except, re-raising as `GraphError`; hermetic test with a malformed row. `store.py`, `tests/test_day11_graph_expand.py::test_neighborhood_surfaces_malformed_response_as_graph_error` |
| 8 | P2 | README Day 11 section reworded: "the deterministic threshold gate held, per-query" with an explicit scope note that this is not an end-to-end safety claim. `README.md`, `docs/notes/day11-neighbor-noise.md` |
| 9 | P2 | New `DEFAULT_ABLATION_MODES` (the pre-Day-11 four modes) is the CLI's `--modes` default; graph modes are opt-in. Verified live: the bare `learnarken eval ablation` command now runs 4 modes, not 6. `retrieval/__init__.py`, `cli.py`, `tests/test_day11_graph_expand.py::test_ablation_default_modes_exclude_graph` |
| 10 | P3 | **Applied on Yi Xin's "所有的红队发现的问题都修改" ruling (2026-07-20, transcribed verbatim — see Part 2).** `build_lexicon` is now cached, keyed by the sorted chunk-id set (a chunk_id is a content hash of dmc/source_path/strategy/file_digest, so same key ⇒ same corpus, cache cannot serve stale data); bounded to 8 entries. Avoids rebuilding the lexicon on every retriever construction *and* again for the trace span. `entity_link.py` |
| 11 | P3 | **Applied on the same ruling.** New hermetic test drives `tools/day11_refusal_gate.py`'s `main()` directly (loaded via `importlib`) with `graph.is_up` monkeypatched to `False`, asserting the `SystemExit` fail-closed path — closing the one residual gap noted above. Required reordering the script's checks (Neo4j gate now before the Vespa/manifest verification) so the fail-closed path needs no live services to test; behavior for the all-services-up path is unchanged (re-run, identical output). `tools/day11_refusal_gate.py`, `tests/test_day11_graph_expand.py::test_refusal_gate_fails_closed_when_neo4j_down` |

All fixes verified: `make test` = **373 passed, 9 skipped**, `make lint`
clean; the live ablation (Vespa + Neo4j up) was re-run before and after the
`sync()`/`verify_corpus` changes and produced **byte-identical metrics** on a
freshly-synced corpus (the fix only changes behavior when stale state exists,
which a fresh index run does not exercise); `tools/day11_refusal_gate.py`
re-run after every round of fixes (including #10/#11): `regressions=[]
pass=True`, output unchanged throughout.

## Part 2 — Adjudication (Yi Xin's ruling)

> **Ruling (Yi Xin, 2026-07-20, verbal instruction, transcribed verbatim):
> "所有的红队发现的问题都修改"** — accept every finding (#1–#11) and apply
> every fix, including the two P3s (#10, #11) the implementer had initially
> left as "no action" / "residual gap" pending this ruling. This mirrors the
> Day 9 precedent ("红队标记的全部修改").
>
> **Ruling: accept #1–#11. All fixes applied** (see disposition table above,
> now including #10/#11). Re-run of the full suite and the live artifacts
> after every round of fixes confirms: `make test` 373 passed / 9 skipped,
> `make lint` clean, ablation metrics byte-identical to the pre-fix run on a
> fresh index, refusal gate `regressions=[] pass=True`.
>
> Number re-run: the **implementer (AI)** re-ran `eval/results/
> day11-ablation.json` and `eval/results/day11-refusal-gate.json` after each
> round of fixes in this session and cross-checked them (above) — no number
> changed across any fix round. This is not a substitute for **INV-6**, which
> requires Yi Xin to independently re-run the numbers before merge; that
> independent re-run is still outstanding.
