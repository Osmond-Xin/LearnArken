# Red team — Arken-alignment execution plan (2026-07-26)

Not a day node: this reviews `docs/specs/arken-alignment-2026-07-26.md` (the
execution plan for the Arken-facing work package) **before** implementation, plus
the uncommitted README.md / README.zh-CN.md additions of the same date. Filed
under the day-review convention because the same rules apply.

- **Reviewer**: Codex CLI (`codex exec --sandbox read-only`), routed cross-host
  by `adversarial-review/lib/call-external.sh` — the implementing model (Claude)
  did not self-review the findings half.
- **Host cross-validation**: Claude ran an independent pass and re-derived every
  external finding from source before recording it. Verification verdicts below
  are the host's; they are evidence, not adjudication.
- **External verdict**: `REVIEW_NEEDED` — 6×P0, 9×P1, 2×P2, 1×P3.
- **Review target is a plan, not code.** Nothing was implemented before this
  review, per the 2026-07-26 directive ("走红队测试，红队测试通过后，进行落实").

## Part 1 — Findings (AI, read-only)

Tags: `[cross-validated]` both reviewers found it · `[external-only]` Codex only
· `[host-only]` Claude only. `Verified` = host re-derived it from source.
Fix status is a record of what was changed, **not** an adjudication.

### P0

**F-01 · Authorisation-before-reasoning is not implementable as the plan writes
it** `[cross-validated]` · **Verified — and the plan understated it**
- Plan said: "filter candidates by `securityClassification` … **before**
  retrieval", acceptance "a test asserts the filter runs before the retrieval
  call".
- Source: [`retrieval/__init__.py:92`](../../src/learnarken/retrieval/__init__.py)
  docstring states plainly — "bm25 stays offline and filters *before* scoring
  (Day 3 semantics). **The Vespa-backed modes retrieve first and filter after**".
  So in every mode that matters (dense / hybrid / rerank) admission would happen
  *after* the model-facing candidate set was already built.
- A post-retrieval filter does not satisfy Arken's pillar 1 and claiming it
  would be an INV-7 breach.
- **Required change**: clearance must be pushed into BM25 corpus construction
  *and* into the Vespa YQL before `nearestNeighbor`, and graph fact-injection
  must draw only from admitted chunks. Acceptance must assert the *retrieval
  call itself* never sees inadmissible chunks, not that a filter ran early.

**F-02 · The plan names the wrong rule for trace `status`** `[external-only]` ·
**Verified**
- Plan said `status` reuses "the `XREF-003` issue-number check".
- Source: [`validation/engine.py:417`](../../src/learnarken/validation/engine.py)
  — XREF-003 is "DM `issueInfo` must match its DML registration", i.e. a
  *mismatch* rule. The supersession signal is **XREF-007**
  ([engine.py:289](../../src/learnarken/validation/engine.py)) — "newer issue
  wins the index (入库) with an XREF-007 warning".
- Building "is this source superseded?" on XREF-003 would produce a field that
  is wrong whenever the DML agrees with the DM, which is the normal case.

**F-03 · Unruled AI decisions gate implementation** `[cross-validated]` ·
**Verified**
- Plan marks D4–D7 `[AI-PROPOSED — NEEDS RULING]` and simultaneously schedules
  the phases those decisions gate. An implementer could choose silently — the
  exact INV-6 failure the labelling exists to prevent.
- **Required change**: a Phase −1 that blocks on human rulings.

**F-04 · D7 (borrowed literature figures) is a live INV-5 conflict**
`[cross-validated]` · **Verified**
- Plan proposed publishing "Rolls-Royce ~1 h/engineer/day ≈ £5.25M/yr (Ubhi et
  al. 2004)" labelled as borrowed. INV-5 admits exactly two states: a number
  with a fixed seed + golden set + repro command, or no number. "Attributed but
  not reproducible" is a third state the constitution does not define.
- **Related, and worse**: the same class of number is *already in the
  uncommitted README* — "a £200M military administration system" in the new §6
  note. That shipped without noticing the conflict.
- **Required change**: this needs a human ruling on an external-citation
  policy before any borrowed figure is published. Until then, no borrowed
  numbers.

**F-05 · Arken's published definitions are not pinned** `[external-only]` ·
**Verified — and the host's own sourcing was incomplete**
- Plan's Phase 1 acceptance criteria "quote Arken's published definition", but
  nothing freezes what those definitions were or when they were read. The
  implementer could paraphrase and then test against its own paraphrase.
- Host check: `https://thearken.com/trust`, `/deploy` and `/whitepapers` all
  return HTTP 200 and **were never read** when §6 was drafted — the mapping was
  built from `/architecture`, `/work` and `/about` only. Pillar wording may be
  more precise on the unread pages.
- **Required change**: commit a dated source snapshot (URL, access date, exact
  quote per pillar) before writing any acceptance test against those words.

**F-06 · "All red-team findings get fixed" cannot coexist with the plan's
out-of-scope list** `[external-only]` · **Verified**
- The standing rule (2026-07-18/19) is that every finding is fixed, no severity
  triage. The plan simultaneously puts "re-measuring any frozen Day 8 artifact"
  and "any change to the constitution" out of scope. F-04 is precisely a
  finding whose only real fix is a constitution amendment.
- **Required change**: define "fix" three ways — implementation defects are
  patched; governance conflicts become blocking human rulings; findings whose
  fix is out of scope are resolved by **removing or softening the claim**, never
  by deferral.

**F-07 · Corpus expansion can corrupt benchmark lineage** `[cross-validated]` ·
**Verified**
- Plan said "re-run the Day 4 ablation on the expanded corpus and publish both
  tables". The tables are generated from `eval/results/*.json` by
  `tools/gen_benchmark_tables.py` with a drift test; re-running into the same
  artifact names silently redefines what the published Day 4 numbers mean.
- **Host-added, not in the external report**: `eval/golden/day4.jsonl` labels
  relevance per query. Adding 500–800 chunks including *hard negatives* means
  chunks that are genuinely relevant to existing queries may now exist and be
  unlabelled — they would score as misses and depress recall for reasons that
  are annotation artefacts, not retrieval quality. The plan's "coverage ratio
  changes and must be restated" badly understates this: **the expanded corpus
  needs its own re-annotated golden set, or its recall numbers are not
  comparable to anything.**
- **Required change**: `corpus-v2` as a separate package, `day4-expanded.jsonl`
  as a separately human-annotated golden set, `day4-expanded-ablation.json` as a
  new artifact, a separate generated BENCHMARKS block. Never overwrite a frozen
  artifact.

### P1

**F-08 · README claimed design intent it cannot evidence** `[cross-validated]` ·
**Verified — pre-existing and published**
- README §6 opened "This project **was built against** Arken's publicly
  described architecture".
- Host check: `grep -rn "thearken.com" docs/` returns **nothing**; no spec,
  journal, discussion or ADR across all thirteen days mentions the seven
  properties. `git log -S "thearken.com"` finds no earlier introduction. The
  seven pillars appear in exactly one committed place: the plan written today.
- This is retroactive alignment presented as design intent — the INV-7 failure
  class this repo exists to demonstrate against, in the section that argues the
  repo is honest.
- **Fix applied**: rewritten to "**retrospectively audited** against", with the
  reason stated inline ("the thirteen daily specs were written against this
  project's own constitution, and none of them cites those seven properties …
  a post-hoc audit, not design intent recovered after the fact"). Mirrored in
  README.zh-CN.md.

**F-09 · New README text asserted a benchmark property the tables do not have**
`[host-only]` · **Verified**
- The §1 addition written today claimed "that is why **every benchmark in this
  repo reports both** [latency and recall]".
- `docs/BENCHMARKS.md`: the chunking-strategy table (§2) and the embedding-
  provider table report Recall/MRR/nDCG with **no p50 column**. Only the
  retrieval-mode ablation reports both.
- The claim was inherited from `docs/constitution.md:18` ("Benchmarks in this
  project always report both"), which is itself inaccurate about the tables.
- **Fix applied**: narrowed to the retrieval ablation, with the constitution's
  overstatement recorded inline rather than silently propagated. The
  constitution itself is **not** edited — it is human-owned. Mirrored in zh-CN.

**F-10 · Gap object conflates invalid input with an admitted knowledge gap**
`[external-only]` · **Verified as a definitional problem**
- Arken's definition: a gap is "a detected domain where **admitted** knowledge
  is incomplete". The plan derives gaps from XREF-001 on `samples/package-b` —
  a package that is *deliberately invalid and would be rejected at ingest*, so
  it was never admitted.
- **Required change**: either name the kind `pre_admission_declared_missing`
  and say so, or build a fixture that passes validation yet still declares a
  `dmRef` to a module outside the package. The second is the honest read of
  their definition.

**F-11 · Owner routing acceptance can pass with `null` forever**
`[external-only]` · **Verified**
- "owner resolved from map or explicitly `null` with a reason; `null` is valid"
  — every test passes with an empty owner map, so the feature can ship without
  routing anything.
- **Required change**: one non-null routing test **and** one null-with-reason
  test.

**F-12 · Synthetic owner map is invented governance data** `[host-only]`
- `samples/package-a/owners.json` keyed by SNS is authored by me. Satisfying
  "who should act" from a map I invented is a Toy-scale mechanism, not an
  S1000D-native one, and must be labelled that way wherever the pillar is
  claimed. `responsiblePartnerCompany` is the real S1000D carrier and is absent
  from the synthetic corpus (C3).

**F-13 · Local-model benchmark underspecified** `[external-only]` · **Verified**
- "open-weight local chat model under `LEARNARKEN_LOCAL_ONLY=1`" names no
  model, revision, quantisation, runner version, hardware, seed or decoding
  config. Publishing a degradation number from that is an INV-5 breach on the
  same day the plan invokes INV-5 against D7.

**F-14 · Phase 0 verification does not verify Phase 0** `[cross-validated]` ·
**Verified**
- `pytest -k "doc or link"` plus "visual GitHub check" cannot check that a
  three-tier router's anchors resolve, that a badge points at the right
  workflow, or that a GIF shows what it claims. No README anchor guard exists.

**F-15 · `README.zh-CN.md` contradicts the plan's own "repo output English"
constraint** `[external-only]` · **Verified**
- Phase 0 edits a Chinese outward-facing README while the goal section says
  repo output stays English. The existing README states learning materials are
  Chinese and outward artifacts English; a top-level Chinese README sits across
  that line.

**F-16 · Trace format bump can break already-published evidence** `[host-only]`
- Plan says bump `TRACE_FORMAT` and "update every reader". Traces already
  committed and referenced from `docs/EVIDENCE.md` are at the old version; a
  reader that only accepts v2 retro-breaks published claims.
- **Required change**: readers accept v1 and v2; a test asserts an existing
  committed trace still parses.

**F-17 · Phase 1 blast radius on the measured refusal threshold** `[host-only]`
- 1.3/1.4 modify `answer/engine.py`, whose candidate set feeds rerank and
  therefore gate 7, whose threshold is a *measured artifact*
  (`eval/results/day5-refusal-threshold.json`). Changing what enters the
  candidate list can move refusal behaviour without anyone re-measuring.
- **Required change**: name this as a regression surface and assert the refusal
  rate on the existing golden set before/after.

### P2 / P3

**F-18 · No rollback statement anywhere in the plan** `[cross-validated]`.
One commit per phase, no artifact overwrite, trace v1/v2 compatibility.

**F-19 · Demo GIF is unverifiable by construction** `[cross-validated]`. In a
repo whose rule is claim → artifact → command, a GIF is the one artifact with no
repro path. Commit the trace id of the run it shows alongside it.

**F-20 · No JSON schemas** `[external-only]` · P3. `Gap`, refusal action item,
owner map and trace v2 should be schema'd like the existing Pydantic models.

### Host-only note on sourcing

The external reviewer cited `/trust`, `/deploy` and `/whitepapers`. Host
verified all three return 200. They were not consulted when §6 was drafted.
This is not a finding against the plan so much as a gap in the evidence base the
plan sits on, and F-05's snapshot step should cover them.

### P0 — found during Phase 1.4 verification, not by either reviewer

**F-21 · The published Day 4 ablation table does not reproduce on today's
corpus** `[host-only]` · **Verified — and it is pre-existing, not caused by this
work package**

- Found while re-verifying after the Vespa schema redeploy + reindex: running
  the documented command `learnarken eval ablation` today disagrees with
  `eval/results/day4-ablation.json` in **12 of 32 metric cells**, across *all
  four modes*:

  | Mode | Metric | Published | Today |
  | --- | --- | --- | --- |
  | bm25 | recall@5 · recall@10 · mrr · nDCG@10 | 0.8284 · 0.8806 · 0.7393 · 0.7701 | 0.8060 · 0.8731 · 0.7057 · 0.7417 |
  | dense | recall@5 · mrr · nDCG@10 | 0.9851 · 0.8703 · 0.9003 | 0.9776 · 0.8457 · 0.8814 |
  | hybrid | recall@5 · mrr · nDCG@10 | 0.9254 · 0.8496 · 0.8829 | 0.9403 · 0.7893 · 0.8390 |
  | hybrid-rerank | mrr · nDCG@10 | 0.8520 · 0.8846 | 0.8149 · 0.8574 |

- **Not caused by the authorisation work.** `bm25` is fully offline and never
  touches Vespa, yet it drifted too. Decisive check: with
  `retrieval/__init__.py`, `hybrid.py` and `dense.py` stashed back to `HEAD`,
  bm25 returns **the same** 0.8060 / 0.7057 / 0.7417 as with the changes
  applied. The clearance code is not in the causal path.
- **Cause.** Commit `dd210e3` (Day 12, multimodal) **modified the two packages
  the ablation evaluates**: it added `.describe.json` + PNG assets to
  `samples/package-a` and `samples/package-c`, which introduce a **figure chunk
  in each**, and it edited `DMC-LA100-A-24-50-00-00A-520A-A_EN-CA.xml` in
  package-c (17 lines). Today's corpus is 45 chunks including 2 figure chunks;
  the frozen artifact was measured before those existed
  (`git log -- eval/results/day4-ablation.json` shows one commit, `f030330`,
  Day 4 — it has never been re-measured).
- **Why it went unnoticed**: `tools/gen_benchmark_tables.py --check` verifies
  that the *tables match the JSON*. Nothing verifies that the *JSON still
  matches the code and corpus that produce it*. The guard built after the last
  review closes table-vs-artifact drift; this is artifact-vs-reality drift, one
  layer further out.
- **Severity**: this is the headline retrieval table in README §4 and
  BENCHMARKS §3 — an INV-5 breach of the same class as F-01 in the
  2026-07-25 review, but on the most-read numbers in the repo.
- **Deliberately not fixed unilaterally.** Re-running and overwriting
  `day4-ablation.json` would silently redefine what the published Day 4 numbers
  mean, which is exactly what F-07 forbids. Options for adjudication:
  1. Re-measure on the current corpus, publish the new table, and keep the old
     one labelled with the corpus it described.
  2. Keep the Day 4 numbers as a historical record explicitly scoped to the
     pre-Day-12 corpus, and state that the current corpus gives different
     numbers.
  3. Pin an eval corpus separately from the demo corpus so Day-N feature work
     can never move a Day-M benchmark again (the structural fix).
- **Recommended regardless of choice**: a guard that fails when a committed
  benchmark artifact's declared inputs (packages, chunk-id set) no longer match
  what the repo would produce — the missing layer that let this sit since
  Day 12.

## Part 1b — Second round: Phase 1 implementation review (2026-07-27)

- **Reviewer**: Codex CLI, routed cross-host as before. **Verdict:
  `DO_NOT_MERGE`** — 1×P0, 4×P1, 5×P2, 2×P3 on the Phase 1 code.
- Every finding below was re-derived from source by the host before recording.
  All were **fixed the same session** (standing rule: fix all findings).

**F-22 · P0 · The authorisation feature was unreachable** `[external-only]` ·
**Verified** — `grep -rn "clearance" src/learnarken/cli.py src/learnarken/api/`
returned nothing. `clearance` existed only as a library parameter; no CLI flag
and no API field supplied it, so nothing a user can run enforced it. A capability
no entrypoint reaches is not implemented.
**Fixed**: `--clearance` on `query` and `search` (argparse-constrained to the
closed vocabulary), `clearance` on the API `QueryRequest` (regex-bounded), both
threaded to `answer_question` / `search_package`, verified end-to-end.

**F-23 · P1 · The dense arm bypassed the filter entirely** `[external-only]` ·
**Verified — this was a real fail-open.** `_candidates()` took no `clearance`
and called `_mode_retriever` without it. The chunk list constrained the BM25
arm, but the dense arm queries Vespa, which holds the *whole* corpus — so an
inadmissible chunk could return straight into the candidate set that the
reranker and the model then reason over. The YQL constraint built for F-01 was
never reached from the answer path.
**Fixed**: `clearance` threaded through `_candidates`, plus
`assert_documents_admissible` on the returned candidates as the check that the
engine-side constraint held.

**F-24 · P1 · Clearance made every non-BM25 answer abort** `[external-only]` ·
**Verified.** `partition` ran *before* `verify_corpus`, so the filtered chunk
set no longer matched the manifest's chunk-id set and gate 6 refused. Any
authorised query would have failed closed — wrongly.
**Fixed**: verify the full corpus first, then apply the clearance cut.

**F-25 · P1 · `citation_status` never compared the issues** `[external-only]` ·
**Verified — the module's own docstring described the bug it had.** Any DML
registration produced `state=current`; the cited issue was never compared with
the registered one, so a mismatch would have been reported as current.
**Fixed**: added the comparison and a `superseded` state with a basis naming
both issues; test added.

**F-26 · P1 · Refusals routed on a rejected package's metadata**
`[external-only]` · **Verified.** `route()` matched against *all* gaps,
including pre-admission ones, so ownership from a package the ingest gate had
rejected could be used to route work.
**Fixed**: routing uses `admitted_gaps` only; a pre-admission match is reported
with a reason and explicitly not routed. **Consequence, stated honestly**: since
an admitted declared-missing module cannot occur on this corpus (the same
structural boundary as pillar 4), refusal owner-routing now routes nothing here.
The path is unit-tested against a synthetic admitted gap and labelled as such.

**P2s, all fixed**: narrowed the blanket `except Exception` in
`citation_status` and named the cause in the `basis` (this immediately exposed
`NotAPackageError`, which is not a `ValueError` and had been silently absorbed);
a malformed `owners.json` now degrades to unknown ownership instead of raising
into a decided refusal; `read_trace` accepts v1 and v2 with a test.

**P3s, fixed**: the trace now carries an `authorisation` span recording the
requested clearance and whether it was enforced — an absent clearance can no
longer be mistaken for an authorised query; and the CLI prints *what would
resolve it* / *who should act* on a refusal instead of hiding them behind
`--json`.

### Second fix pass — the remaining findings (same session)

**F-27 · P2 · The trace enumerated classified module identifiers**
`[external-only]` · **Verified.** `sources_excluded` recorded the `dmc` of every
authorisation-withheld chunk. A caller denied a module's *content* could still
learn that module's identity — which names its system and subject — from the
trace.
**Fixed**: the DMC is redacted on authorisation exclusions. `chunk_id` stays,
because it is already an opaque digest, so an auditor with corpus access can
still correlate while the trace alone enumerates nothing.

**F-28 · P2 · A schema edit could not be detected** `[external-only]` ·
**Verified — this is the failure hit live the same day.** The Vespa schema
change deployed, the config server accepted it, and the content node kept
serving the old schema; every clearance query failed with "attribute not found"
and nothing in the repo could notice. Purging and re-feeding did not help;
only a container restart did.
**Fixed**: `vespa.store.schema_digest()` hashes the application package, the
digest is written into the corpus manifest at feed time, and `verify_corpus`
fails closed when it drifts. Confirmed by running it: the pre-existing manifest
was rejected with *"manifest schema digest None != current '2b6d71cf89678b24' —
the Vespa application package changed since this index was fed"*, and a
re-index cleared it.

**F-17 (from the plan review) · discharged with a measurement.** The plan
required the refusal rate over `eval/golden/day4.jsonl` to be measured before
and after Phase 1, since the work changes what enters the candidate list.
`tools/day11_refusal_gate.py` re-run against the frozen
`eval/results/day11-refusal-gate.json`: threshold identical, 18 traps,
`hybrid` 1 refused, `hybrid-graph` 1 refused, **per-query differences: none**,
pass true → pass true. The tool gained an `--out` flag so a regression
re-measure cannot clobber the frozen artifact — ADR-0004 turned into a
mechanism rather than a rule people are asked to remember.

**Host note on the fix round**: four test doubles across `test_day5/6/11/12`
carried the old `_candidates` / `answer_question` signatures and had to be
updated. Two of my own new tests **failed after the F-26 fix because they
asserted the buggy behaviour** — they were rewritten to assert the correct
behaviour rather than the fix being reverted to keep them green.

## Part 1c — Third round: whole-state review (2026-07-27)

Codex, cross-host, on the full current state including the previous round's
fixes. **Verdict `DO_NOT_MERGE`** — 1×P0, 3×P1, 5×P2, 1×P3. All verified
against source and fixed the same session.

**F-29 · P0 · Graph facts bypassed clearance and put classified DMCs in the
prompt** `[external-only]` · **Verified — the worst miss of the day.**
`graph.facts([c.dmc for c in evidence])` takes no clearance. Partitioning
filters *chunks*; it does not touch the dependency graph, whose `REFS` edges
name data modules by DMC — and those DMCs are injected into the LLM prompt and
written to the trace. A caller denied a module's *content* could still learn it
exists, what it is called, and what points at it, straight out of the reasoning
context. The irony is exact: the previous round redacted the DMC from
`sources_excluded` while leaving the same identifier flowing into the prompt.
**Fixed**: `redact_graph_facts` drops neighbours outside the admitted corpus and
records `withheld_refs` so the redaction is visible rather than silent.
"Authorisation constrains reasoning" — and a prompt is reasoning.

**F-30 · P1 · `schema_digest` proved local consistency, not the deployed
schema** `[external-only]` · **Verified.** `index` only deploys when Vespa is
*down*, so editing the schema and re-indexing a running engine writes a fresh
digest while the content node still serves the old schema — the manifest would
attest a capability the engine lacks. The docstring I wrote claimed more than
the mechanism delivered.
**Fixed**: added `assert_attribute_filtering_supported()`, a hits=0 probe that
*issues* the clearance filter before feeding, and called it in `index_package`.
The check is behavioural because nothing declarative works here — on 2026-07-27
the local file, the config server and the active generation all reported the new
schema while the content node still answered "attribute not found". The digest
docstring was corrected to say what it actually proves.

**F-31 · P1 · Eval and repair harnesses still ran unscoped** `[external-only]` ·
**Verified.** They answer over the whole corpus and freeze the output into
committed artifacts, so a classified module relevant to a golden query would be
published by the very tooling that measures the governed path.
**Fixed**: `assert_uniform_or_scoped` refuses to evaluate a corpus mixing
classifications with no clearance declared; wired into `run_eval`,
`run_ablation` and the adversarial harness. Inert on today's uniformly-`01`
corpus **and deliberately so** — it is computed, not assumed, so it starts
working the moment the corpus stops being uniform.

**F-32 · P1 · Figure second-look could load another package's image**
`[external-only]` · **Verified.** `_load_asset` matched on ICN ident alone and
returned the first package that had it — which may not be the package the cited
chunk came from. `ingest.figure_chunks` already requires `source_dm` to match;
the second-look path did not.
**Fixed**: the owning DMC is passed in and required to match.

**P2s, fixed**: a citation with no issue number now reports `unknown` instead of
falling through to `current`; `LEARNARKEN_LOCAL_ONLY` now actually blocks the
external judges — the README claimed the fence covered "the eval harness" while
nothing enforced it, so the code was changed to match the claim rather than the
claim softened; the schema test was rewritten failure-shaped (mutate the
manifest digest, assert `verify_corpus` refuses) after Codex correctly called it
claim-shaped.

**P3, fixed**: README §6 rows for pillars 1 and 3 were stale against the code
(still saying refusals propose no resolution, and that Vespa modes retrieve
first and filter after). Both rewritten, with the honest limit added that
clearance here is *scoping, not authentication* — there is no identity model, so
a caller states its own clearance.

**Deferred with reason**: the P2 on per-query `analyze_package` cost
(`statuses_for` / `collect_gaps` re-parse packages on the answer and refusal
paths). Real, but it is a latency concern on a 45-chunk corpus behind an LLM
call that dominates it by orders of magnitude, and caching keyed on package
digest is Phase 2 work. Recorded rather than silently ignored.

## Part 1d — Rounds 4–9: demo-capture preparation (2026-07-27)

Six cross-host Codex rounds on the working-tree diff that came out of preparing
the Phase 0.2 capture (`llm/minimax.py`, `answer/prompt.py`,
`demo/streamlit_app.py`, tests). Each round re-reviewed the **whole** diff
including the previous round's fixes — and rounds 5, 8 and 9 each broke a fix
from the round before, which is the entire argument for that discipline.

**Why this diff exists at all.** Phase 0.2 could not be filmed honestly: the
"streamed text withdrawn" shot was reachable only through an `llm-contract`
refusal that was our own defect. Measured on the live stack, **7 of 28 runs**
(25%) failed the contract; M3's think block was exhausting the 2048-token
completion budget and truncating mid-JSON, which surfaced as `post-think content
is not JSON: ''` — indistinguishable, to an operator, from a model failure.

**F-33 · P1 · The completion budget was too small, and truncation was
unreadable** `[host-only]` · Measured, not inferred: one question ranged over
1888 / 1467 / 3464 / 7305 completion tokens across repeats at temperature 0,
with think blocks of 497 to 27,102 characters. **Fixed**: budget 2048 → 16384
(covers every observed run with headroom; billing is on tokens produced, so the
headroom costs nothing until used), and `finish_reason == "length"` now raises a
refusal that names the budget. After the fix: **0 contract failures in 24 live
runs**, and the genuine `citation-validation` retraction — unreachable before,
because the budget died first — began to reproduce.

**F-34 · P1 · The `</think>` salvage let attacker-reachable reasoning become
the answer** `[external-only]` · **The finding of these rounds, and it took four
attempts to settle.** M3 sometimes closes its think block a token late, stranding
the JSON's opening brace inside it. A salvage re-spliced the object across that
boundary. Round 4 showed it accepted an object planted *wholly* inside the block;
the narrowing was broken again in round 5 (plant most of the contract, leave it
incomplete), and again in round 9 (the question text is not escaped, so the
planted bytes need not even come from a data module). Uploaded XML becomes
evidence in the prompt, so this is reachable by an uploader, and the only gate
behind it is verbatim quote containment. **Fixed by deletion**: the salvage is
gone. It rescued about one run in forty; refusing that run is the cheaper trade
and is what INV-4 asks for. A test asserts the helper cannot quietly return.

**F-35 · P1 · A literal `</think>` could be carried into the prompt as
evidence** `[external-only]` · `json.dumps` does not escape `<`, so a data
module could put a think tag into the prompt and have the model copy it into
its reasoning, where the transport layer reads it as structural. **Fixed**: the
`<` of a think tag is escaped in the evidence JSON. Deliberately *only* that
sequence — round 9 pointed out that escaping every angle bracket would corrupt
legitimate evidence (`clearance < 0.05 mm`) whose `supporting_quote` must later
match the chunk text verbatim.

**F-36 · P1 · One call could hold a generation slot far past its deadline**
`[external-only]` · Three findings on the same theme, each one closing the hole
the last fix left: retries did not share a deadline (3 × 300 s); the deadline was
then checked only per parsed chunk, which an SSE keepalive flood bypasses; and
then only between lines, which a byte-trickle without a newline bypasses.
**Fixed**: attempts share one wall-clock deadline, it is checked per raw line,
and a watchdog closes the response when it expires. Error bodies are no longer
read at all — capping the bytes never capped the clock.

**F-37 · P2 · Fail-closed gaps around the contract** `[external-only]` ·
Truncation was masked by the empty-content check; a *missing* `finish_reason`
was accepted as success (verified live that both paths do report `stop`, so
requiring it costs no legitimate traffic); content arriving after a terminal
reason was appended; `HTTPError` was unreachable behind `URLError`, so a 401 was
retried three times and reported as "unreachable"; a non-JSON or non-object
HTTP 200 body escaped as an internal error rather than a refusal; more than one
`choice` was silently ignored. All fixed, each with a test.

**F-38 · P2 · Upstream diagnostics reached the demo visitor** `[external-only]` ·
The API forwards `LLMError` text to the browser, and both HTTP error bodies and
MiniMax `base_resp` objects can echo the request — prompt, evidence, auth
detail. **Fixed**: the status code travels, the diagnostic is logged
server-side.

**F-39 · P2 · The demo UI was not the dumb client it claims to be**
`[cross-validated]` · It indexed wire fields directly (`result["refused"]`,
`payload["text"]`, citation rows), so a truncated or version-skewed payload lost
the whole turn to a `KeyError`; an unlabelled gate rendered as `?`; and
`figure-out-of-description` had drifted out of the label table entirely.
**Fixed**: every wire field is read defensively, and a test now asserts every
gate the engine can emit is nameable on screen.

**F-40 · P2 · Phase 1.2's routed refusal was invisible in the demo**
`[host-only]` · Found while planning the capture, not by a reviewer. The CLI
prints all three parts Arken asks for (why / what would resolve it / who should
act); the Streamlit client rendered only the gate and the generic placeholder,
leaving `action` on the wire unread. A GIF of the demo would therefore have
shown none of the pillar the work package was built to demonstrate. **Fixed**.

**F-41 · P1 · The public-demo spend bound moved with the budget** `[external-only]`
· Raised in three separate rounds. The quota counts **calls, not tokens**, so
the 8× budget increase widened worst-case exposure per boot from ~410 k to
~3.3 M output tokens. A token quota cannot replace it honestly — `usage` comes
back null on the streaming path. **Not fixed: this is a decision, not an
implementation detail.** The bound is now documented at the quota; re-deciding
`DEMO_MAX_LLM_CALLS` against the $20 envelope is Yi Xin's call.

**Residual, recorded rather than fixed** — a single SSE line of unbounded size
is still buffered by `readline` before any cap applies. Bounding it means
replacing the line iterator with a chunked reader. The attack needs a hostile
upstream, i.e. the authenticated proxy we already trust for answer content, so
the deadline and the cumulative-content cap were judged proportionate. Flagged
for adjudication.

**State**: `make lint` clean, **523 passed / 9 skipped**, hermetic without
`.env`. Verified live after every round — 12 real queries each time, behaviour
unchanged.

## Part 1e — Rounds 10–12: operator-facing polish (2026-07-27)

Three more cross-host rounds on a small follow-up diff — the demo UI translated
to English, and `learnarken query` stopped interleaving loader noise with its
answer. A "cosmetic" change turned out to carry the round's worst finding.

**F-42 · P1 · Defensive reading had quietly become fail-open** `[external-only]`
· **The one to remember.** Rounds 4–9 replaced the demo client's direct field
reads with `.get()` so a truncated payload could not lose the turn to a
`KeyError`. That fix inverted the failure mode: `{"result": {}}` no longer
crashed — it fell through to the *answered* branch and rendered "✅ Citations
verified" under a result containing no answer and no evidence. The guard added
to stop a crash had removed the check that made the crash meaningful.
**Fixed** by collapsing the whole decision into one pure `classify_turn(entry)`
returning `answered` / `refused` / `failed`, where anything that is not a
*complete* answer (non-empty text, a trace id, at least one citation with all
four of chunk_id/DMC/XPath/quote) or a *complete* refusal (gate, trace,
routed action) is a failure. `render_answer` reads fields directly again —
safe now precisely because the classifier ran first, and a test asserts it
cannot render without asking it. Fourteen malformed payloads are pinned,
including "retracted, then answered anyway".

**F-43 · P2 · Silencing noise silenced signal** `[external-only]` · The first
attempt at removing the hub's anonymous-read notice raised the whole
`huggingface_hub.utils._http` logger to ERROR — which also mutes 429 backoff and
retry warnings, i.e. exactly what explains a run that looks stuck. **Fixed**: a
`logging.Filter` matching that one message, attached idempotently from `main()`
(not at import — importing the CLI must not mutate a whole process's logging and
progress-bar state). A test drives the real logger and asserts the 429 survives.

**F-44 · P2 · Untrusted text still reaching markdown renderers** `[external-only]`
· `st.error` / `st.warning` render markdown, and an indexing error can quote the
document that failed. **Fixed**: static headers, dynamic detail through
`st.text`; unrecognised gate names are stripped to plain characters before they
reach a label.

Also fixed: validator findings rendered through `st.text`, upload payload fields
read as a validated list of dicts, and CLI output-contract tests pinning that
`--json` never contains the divider while answered and refused human output each
contain exactly one.

**State**: `make lint` clean, **546 passed / 9 skipped**. Verified live — the
CLI prints its answer with no HF warning and no `Loading weights` bar, and the
classifier was run against real `/query` payloads (answered / refused / refused)
to confirm the stricter contract does not fail closed on legitimate traffic.

## Part 2 — Adjudication (Yi Xin's rulings)

> **Transcription notice.** Every ruling below was given by Yi Xin in-session on
> 2026-07-26/27 and transcribed by the implementer at his direction, quoting his
> words where they were given verbatim. The decisions are his; the surrounding
> English is the implementer's and is subject to his correction. This follows
> the Day 11 precedent (`docs/reviews/day11.md` Part 2). Rationale in his own
> voice belongs in `docs/journal/`, which AI does not write.

### Standing ruling — every finding is accepted and fixed

> **"红队发现的全修"** (2026-07-27)
> **"该改的都改，不管是不是自己的烂摊子，没别人了。"** (2026-07-27)

Accept **F-01 – F-20, F-22 – F-32**, all three rounds, with no severity triage
and no deferral by ownership. The second instruction explicitly widened the
scope beyond this work package's own defects to **pre-existing** ones, which is
what authorised:

- clearing repo-wide lint (3 findings in `tools/` and `deploy/`, 2 unformatted
  files) that had accumulated outside CI's `src tests` scope;
- **extending `make lint` and CI to the whole repository**, so the scope gap
  that let them accumulate is closed rather than the symptoms swept;
- removing the Vespa `validation-overrides.xml` entry that expired 2026-07-23
  and had been sitting inert.

One item is recorded as **deferred with reason** rather than fixed: the per-query
`analyze_package` cost in `statuses_for` / `collect_gaps` (round 3, P2). It is a
latency question on a 45-chunk corpus behind an LLM call that dominates it, and
the fix (caching keyed on package digest) is Phase 2 work.

### F-21 — accepted, and deliberately **not** fixed

> **"不用改之前的发布，把这个作为学到的内容，当原始素材改了以后，之前的数据都会作废。"**
> (2026-07-27)

Neither re-measurement option was taken. The published Day 4 numbers stand
unchanged. What is taken from the finding is the **rule**, recorded as
[ADR-0004](../adr/0004-measurements-are-bound-to-their-corpus.md): a benchmark
number is a statement about a specific corpus at a specific revision, and when
the source material changes the earlier measurement is *void* — not approximate.
The drift guard was offered and **deferred**: the ruling was to take the lesson,
not to automate around it. The affected tables carry a scope note instead.

### Decisions taken during planning (Phase −1, 2026-07-26)

| # | Ruling | Consequence |
| --- | --- | --- |
| **D4** | Credibility-first phase order (0 → 1 → 4a → S → 2 → 3) | Phase 0 shipped before the deeper corpus work |
| **D5** | Ownership from an external `owners.json`, **not** by editing sample XML | Avoids the chunk-id/manifest churn of C1; the map is labelled Toy-scale wherever the capability is claimed (F-12) |
| **D6** | Corpus target 500–800 chunks **with a newly human-annotated golden set** | Accepts that annotation, not generation, is the cost driver (C7). Phase S not yet started |
| **D7** | **Publish no borrowed literature figures** | Resolves the INV-5 conflict in F-04 by removing the category. The "£200M" figure was deleted from README §6 the same day; Phase 3 becomes method-without-numbers |
| **D8** | `README.zh-CN.md` is a non-authoritative translation | Implementer's proposed default, not objected to; header note added. Resolves F-15 |
| **1.2** | **Option A** — a refusal routes an owner only when it links to an existing gap signature | Accepts that owner routing then routes nothing on this corpus, for the same structural reason as pillar 4 (F-26) |

### Number re-run (INV-6) — performed by Yi Xin, 2026-07-27

Re-ran the refusal-gate regression himself rather than taking the implementer's
run for it. Result:

- **Refusal decisions: identical** on all 18 traps, both modes. `pass=True`,
  `regressions=[]`, threshold unchanged. The gate the finding was about holds.
- **But 10 top-1 score cells differ** from the frozen
  `eval/results/day11-refusal-gate.json` (e.g. 0.4771 → 0.7093).

The scores moved for the same reason as F-21: that artifact was frozen on the
pre-Day-12 corpus, and Day 12 added figure chunks to both evaluated packages.
ADR-0004 therefore applies to this artifact as well as to the Day 4 ablation —
it is a record of what was measured on the corpus of its day, not a current
reading. Under the same ruling it is **left as measured**, and the check that
mattered — per-query refusal non-regression — was verified independently.

This is the case for INV-6 in one line: the implementer's own comparison had
looked only at the refusal booleans and would not have surfaced the score drift.

### Still open

Phase 0.2 demo capture — needs the live stack and a human at the keyboard; the
plan forbids staging it.
