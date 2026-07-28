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
refusal that names the budget. The truncation class is gone, and the genuine
`citation-validation` retraction — unreachable before, because the budget died
first — began to reproduce.

> **Corrected 2026-07-28 by Yi Xin's INV-6 re-run.** This finding originally
> read "**0 contract failures in 24 live runs**". That sample was taken while
> the `</think>` salvage of F-34 was still in place, and I never re-measured
> after removing it. Yi Xin's independent run hit `llm-contract` twice in nine.
> Both were the late-tag quirk, not truncation: one post-think body began
> `": "Before removing…` (the tag swallowed `{"answer`), the other began
> `json\n{…}` (it swallowed the opening ```` ```json ```` fence). A further 15
> runs here returned none, so the honest figure across both samples is **2 of
> 24, about 8 %** — intermittent enough that a single clean sample says nothing,
> which is the whole argument for someone else running it.
>
> Removing the salvage is what re-exposed this class, by design: F-34 chose a
> refusal over a rescue that could be steered.
>
> **Ruled the same day: retry once.** A retry re-asks rather than reconstructs,
> so it does not reopen F-34. Shipped, then **caught again by Yi Xin's second
> run**: both retries failed exactly as their first attempts had. The re-ask was
> re-sending a byte-identical prompt at temperature 0 — not an independent
> sample. Each attempt now builds a fresh spotlighting delimiter.
>
> Recorded honestly, because the temptation is to call this fixed: a probe
> re-sending the same delimiter twice *did* return different completions, so
> the endpoint is not deterministic and "identical prompt ⇒ identical failure"
> is more than the evidence supports. Two retries is also too small a sample to
> say the delimiter change helps. **The retry's effectiveness is unmeasured**,
> and the honest way to measure it is another independent run.
>
> **Third run: the retry recovered a query for the first time**, and turned up a
> failure class neither of us had seen — M3 returned `{"is_answerable": false,
> "  answer": "", "citations": []}`. Valid JSON, two spaces inside a key. The
> engine's shape check refused it at the same gate without a retry, because the
> shape check sat *after* the retried unit. It has moved inside: a malformed
> answer object is a generation glitch, not a statement about the corpus, so
> under the same ruling it gets the same single re-ask. Verified live — late
> tag and malformed shape each recover on the second call, a truncated
> completion still refuses on the first.
>
> Three INV-6 runs, three findings the implementer's own testing missed: the
> rate, then the fix for the rate, then a class the fix did not cover.

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

## Part 1f — Rounds 13–23: the INV-6 retry probe (2026-07-28)

Eleven cross-host rounds on one new file, `tools/probe_retry_effectiveness.py`
— the instrument for raising the re-ask's effectiveness above its current n=1.
Eleven rounds because **every single round found defects introduced by the
previous round's fixes**; the first round that came back clean was the
eleventh. The tool is small. What made it hard is that its output is a number
destined for this document, so the failure mode to design against is not a
crash but a *confident wrong answer*.

**F-45 · P0 · The second reading was reading nothing** `[cross-validated]` ·
**The one to remember.** The probe cross-checks the SSE stream against the
run's committed trace, and read `spans.llm` from it. `write_trace` splats the
spans into the trace *root* — `{"format":…, "trace_id":…, **spans}` — so there
is no `spans` key. Every trace read returned an empty dict, and a cross-check
that finds nothing agrees with everything. The implementer's own test passed
because it fed synthetic dicts straight to the comparison function and never
exercised the reader against a real artifact. **Fixed**: read the root, and
the regression test is written against a real `write_trace()` output. This is
the same shape as F-33 — a guard whose subject was never actually inspected.

**F-46 · P0 · A re-ask that died in transport was scored as a recovery**
`[external-only]` · The classifier tested "was there a restart?" before "did
the run finish?". A second generation that dies mid-stream leaves a `restart`
event, no `result`, and therefore no refusal gate — which fell through to
`retried_recovered`. That is the precise value the probe exists to produce,
reported wrongly. **Fixed**: indeterminacy is decided first and kept out of
the denominator entirely.

**F-47 · P0 · A sample with holes still printed a quotable number**
`[cross-validated]` · A missing trace, a stream/trace disagreement, an
indeterminate run, or a paid run with no logged outcome all still produced
`recovered X of Y` on screen. **Fixed**: those become blockers, the run exits
non-zero, and — after round 4 pointed out that a ratio printed beside a warning
is the line that gets copied — the ratio is **withheld** rather than captioned.
A sample where the re-ask never fired is also unquotable: "24 runs, nothing
went wrong" measures the base rate and says nothing whatsoever about recovery.

**F-48 · P0 · Resume erased a run that had been paid for**
`[external-only]` · Run numbers were allocated above the *finished* rows, so a
`start` with no matching outcome — a run killed after the money was spent —
had its number reused, and the next resume saw start/outcome pairs that
balanced. **Fixed**: allocate above every id ever seen.

**F-49 · P0 · A resumed log could launder an older build's verdicts**
`[external-only]` · Rows carry the conclusions of the logic that wrote them,
and this file had already shipped a version whose cross-check agreed with
everything (F-45). **Fixed**: the log carries a version, is only resumable by
the build that wrote it, derived fields are recomputed on load, and — after
round 6 — the version line must be the *first* record, so an old log cannot be
laundered by appending a current one.

**F-50 · P0 · Two probes could interleave into one artifact**
`[external-only]` · Fixed in three rounds, each of which found the previous fix
asymmetric: an existence check before an append (racy), then a sibling lock
taken *after* replay (two probes read the same state first), then a lock keyed
by pathname (a symlink, then a hard link, gets a different one). **Final
shape**: the log's own inode is flocked before it is read, for new and resumed
logs alike.

**F-51 · P1 · Malformed payloads defaulted into clean verdicts**
`[external-only]` · Across rounds 4–7: `refused` recorded but never read (so
`{"refused": true, "refusal_gate": null}` after a restart scored as a
recovery); `refusal_gate: ""` treated as a real gate; `stream_restarts: -1`
truthy; `trace_llm: {}` accepted as a second reading; trace values of `false`
or `""` read as affirmative evidence; `[]` as an SSE payload crashing on
`.get()` after the call was already paid for. **Fixed**: one validator applied
on both the live and replay paths, so the tool can never write a row its own
resume rejects — pinned by a round-trip test over every row `run_once` can
produce.

**F-52 · P1 · An absent trace span was read as a silent one**
`[external-only]` · Rounds 6–8. `read_trace(path).get("llm") or {}` collapsed
"no span" and "corrupt span" into "nothing recorded". Round 7 narrowed it to
pre-model refusals; round 8 caught that "refused with no generation span" is
*also* true of a corrupt post-model trace, so it now names the one gate the
engine takes before the model exists (`threshold`, `engine.py:331`). A gate
added later fails closed here, which is the safe direction.

**F-53 · P1 · The cross-check could switch itself off**
`[external-only]` · Round 9 added a comparison of the trace's own recorded
decision against the stream's, because a threshold refusal writes a
legitimately *silent* llm span — so span-only agreement said nothing. Round 10
then found that a trace with no readable `outcome` left that comparison
skipped while the ratio still printed: the check was present in the code and
absent from the evidence. **Fixed**: no readable decision ⇒ no reading at all.

**F-54 · P2 · The spend fence advertised a bound it did not hold**
`[external-only]` · A run was admitted with one generation of budget left and
could then re-ask and spend two; unreadable runs were charged one when they may
already have funded a retry; and the banner said "worst case" while the
endpoint can also spend VLM second-look calls. **Fixed**: reserve the worst
case before admitting a run, charge `max(2, 1 + restarts)` for unreadable ones,
and scope the claim explicitly to answer generations.

**F-55 · P2 · Losable evidence and misleading labels** `[external-only]` ·
`flush()` survives this process dying, not the host dying, so a lost `start`
line is a paid call the resume cannot know about — appends are now `fsync`'d.
`tokens_streamed` counted SSE frames, not tokenizer tokens, and is now
`token_events`. `--resume` on a typo'd path created the directory before
refusing. The generation count is labelled "budget units charged", not
"spent" — it is derived from observed restart events, not from the provider's
usage counter.

**A note on the shape of this round.** Ten of the eleven rounds found something,
and most of what they found was created by the previous round's fix — a lock
that closed one alias and not another, a validator that rejected the tool's own
output, a cross-check that a later change could silently disable. The final
round was asked three questions — can it print an unsupported ratio, can it
false-block a legitimate run, can it write a row it cannot replay — and
answered no to all three. The no-false-alarm case is now pinned by tests
parameterised over five real engine trace shapes, because a guard that refuses
everything fails exactly as badly as one that refuses nothing.

**State**: `make lint` clean, **625 passed / 12 skipped** offline. The probe
itself has **not been run against the paid endpoint** — that run is Yi Xin's,
under INV-6, and the number it produces is the point of the exercise.

## Part 1g — Rounds 24–30: the defect the instrument found by being used (2026-07-28)

Seven more cross-host rounds, on the fix for the one defect eleven rounds of
reading the code had missed and **one run of it found immediately**: a third of
Yi Xin's 24-run sample was a query the retrieval threshold refuses *before the
model is called*, so it could not have produced a contract failure however the
model behaved — yet it counted as `clean`, sat in the denominator, and was
charged a budget unit. The tool built to prevent an inflated denominator had
one.

The fix is two-sided on purpose: the query that cannot contribute is out of the
mix, **and** the condition is now detected for any query, because which prompts
clear the retrieval threshold is a property of the corpus and will change
without the query list changing.

**F-56 · P1 · A sample larger than the one that exists** `[host-only, from a
real run]` · **The one to remember, and it was not found by reading.** New
outcome `no_generation`, excluded from the recovery denominator and charged
nothing (the model was never called, so nothing was billed). The tally now
prints `runs=`, `reached the model=` and `refused before it=` as three separate
counts. An earlier draft of this fix printed `generations=`, which round 24
caught as false: a run whose re-ask fires spends two, so that label was wrong in
exactly the sample where it mattered most.

**F-57 · P1 · A verdict resting on the stream's word alone**
`[external-only]` · `no_generation` was decided from the refusal gate's name.
Rounds 25–26 closed it in three steps: it also requires zero token events; the
second reading now preserves the raw fact `trace_spans` (did an `llm` span
exist? a `generation` span?) rather than only the absence of contract fields;
and `disagrees()` gives the outcome its own invariant — *no model span existed*
— while every other determinate outcome now asserts the opposite. Without that
last half, a stray `token` frame before a threshold refusal made the run
`clean`, and a trace showing no model span agreed with it.

**F-58 · P1 · A second reading not bound to the run it described**
`[external-only]` · The trace was located by the id the *result* named, with no
check that the id was even id-shaped and no check that the file agreed. Three
holes, closed together: a path-like id can no longer become a filename
(`TRACE_ID_RE`), the trace's own `trace_id` must match, and — the one that
mattered — the trace's recorded `question` must be the question this run asked.
Without it, a stale trace for a *different* question that happened to record a
recovered re-ask could be collected as this run's corroboration and printed as
`recovered 1 of 1`.

**F-59 · P2 · Spend that could be under-counted three ways**
`[external-only]` · A run admitted with one generation of budget left could
re-ask and spend two; a stream that simply stopped carried no transport note
and was charged one; and the charge trusted the stream's restart count even
when the *trace* recorded a re-ask the stream had lost. Now: the worst case is
reserved before a run is admitted, every indeterminate outcome charges
`max(2, 1+restarts)`, and the charge takes the higher of the two readings. The
fence may over-state spend; it may never under-state it.

**F-60 · P2 · A headline that outran its evidence** `[external-only]` · The
three-way count was computed from stream-derived outcomes even for rows whose
two readings disagreed or which had no second reading — those now count as
`unknown`, and the three always sum to the run count. `tally` also stopped
depending on having been called after a validator: it has its own predicate for
"a second reading is all three of its parts, or none".

**F-61 · P2 · A sampling plan nobody wrote down** `[external-only]` · The log's
meta row now records the exact ordered `(tag, question)` pairs, a resume onto a
different mix is refused, and each row's query tag is audited against the tag
the cycle assigns for its run number. Relying on someone remembering to bump
`LOG_VERSION` when the questions change is not a guard.

**On the evidence for this fix.** The committed artifact
`eval/results/probe-retry-2026-07-28.jsonl` is a `probe-retry/5` log and the
current `load_prior` **refuses** it — `run 1 is missing trace_spans` — which is
the version gate working as designed. What was re-run is narrower and is not
claimed as more: its 24 committed traces, re-read through the current reader
with question binding and re-classified, give `runs=24 · reached the model=16 ·
refused before it=8` with zero stream/trace disagreements. That is evidence the
tightening does not false-alarm on real traces. It is not a replay, and the
2026-07-28 sample is not resumable under the current schema — a new sample
starts a new log, which is the honest consequence of changing what is measured.

**State**: `make lint` clean, **645 passed / 12 skipped** offline, 648/9 with
the services up. The re-ask's effectiveness is still **n=1**; nothing in this
work package measured it, and the probe now says so in three ways instead of
one.

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

### Standing ruling extended — F-33 – F-61 (2026-07-28)

> **Transcription notice.** The five rulings below were given by Yi Xin
> in-session on 2026-07-28 and transcribed by the implementer at his direction,
> quoting his words where they were given verbatim. The decisions are his; the
> surrounding English is the implementer's and is subject to his correction.
> Day 11 precedent, as elsewhere in this Part.

> **"以后红队发现的一律全修"** (2026-07-28)

**1 · The standing ruling is standing.** It reads forward, not only over
F-01 – F-32. Accept **F-33 – F-61** — twenty-nine findings across rounds 4–31,
covering the demo capture, the operator-facing polish, the INV-6 retry probe and
the defect its first real run exposed — on the same terms as before: no severity
triage, no deferral by ownership, all fixed in this work package. Every future
red-team finding on this repository is accepted and fixed by default; a
deferral now needs a reason recorded against it, not the other way round.

**2 · The sampling plan may change when the measurement requires it.**
> **"采样计划被改了就改了，不影响整体项目就没问题。"**

Ratifies F-56: dropping the demo's coffee-maker query from the probe's mix.
The 2026-07-28 run measured it refused before generation on 8 of 8 runs, so it
could not contribute to the denominator while still being counted in it. The
change is scoped to the probe's own sampling and touches no published benchmark.

**3 · The 2026-07-28 sample is closed, not migrated.**
> **"接受，重开一份。"**

The log schema moved from `probe-retry/5` to `/9` while the findings were being
fixed, so `load_prior` refuses the committed artifact
(`run 1 is missing trace_spans`). Ruled: leave it as the record of what was
measured that day and start a fresh log for any further sample; do not write a
migration. This is ADR-0004's rule applied to the instrument rather than the
corpus — when what is measured changes, the earlier sample is not approximately
the same measurement, it is a different one.

**4 · The cost fence may over-state, never under-state.**
> **"高报没问题，有注释说明就行，计算用上限是核算成本的常见手段。"**

Ratifies F-59: a run is admitted only if the worst case fits, indeterminate runs
are charged `max(2, 1 + restarts)`, the charge takes the higher of the stream's
and the trace's evidence, and a run the trace proves never reached the model is
charged nothing. The requirement attached to the ruling — that the basis be
stated rather than assumed — is met in the code comments and in the banner the
probe prints before spending.

**5 · No engine facts hard-coded in the instrument.**
> **"修改探针，不许写死，要向后兼容。"**

Amends F-52 / F-58 rather than accepting them as shipped. The probe had named
the engine's one pre-model gate (`threshold`) and cited its line number, which
tied the measurement to a single engine revision and would have made any later
gate fail closed. Now whether a run reached the model is read from the trace's
**structure** — an absent `llm` span together with an absent `generation` span —
and the gate's name is reported rather than relied on. A gate this build has
never heard of classifies correctly.

The accepted consequence: a trace recording an `llm` span while refusing at a
gate that ought to precede the model is now `clean` (the model demonstrably ran)
instead of being flagged as an engine contradiction. The probe measures re-ask
recovery; policing the engine's internal consistency was never its job, and
buying that check with a hard-coded dependency was the wrong trade.

**And the work on this instrument is closed.**
> **"这个探针到此为止。要收敛了。不要再堆砌无用的内容了。"**

Recorded as a ruling because it is one, and because the thing it stops is the
implementer's behaviour, not the tool's: nineteen cross-host rounds on one
measurement script, ending with the number it exists to produce still at n=1.
INV-8 is the anti-slippage invariant and it applies to rigour that has stopped
buying anything. One round was run on the change above — it returned SHIP — and
the file is done.

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

### Number re-run (INV-6) — performed by Yi Xin, 2026-07-28

> **Transcription notice.** Yi Xin ran the probe himself and authorised the
> implementer to write this section up from the run's output. The run and the
> decision to publish it as-is are his; the wording is the implementer's and is
> subject to his correction.

Ran `tools/probe_retry_effectiveness.py --runs 24` against the live paid
endpoint — the instrument the implementer built but, under INV-6, did not run.

**Result: 24 runs, 24 clean, and the tool refused to publish a number.**

```
runs=24
  clean                  24
recovery metric withheld — see the blockers below

UNQUOTABLE — the evidence has holes; do not publish a number from this run:
  - no run exercised the re-ask — the recovery metric has no denominator
```

Not a single first attempt broke the output contract, so the re-ask never
fired, so the sample contains **no observation whatsoever** about recovery. The
probe exited non-zero rather than print `recovered 0 of 0`. That refusal is the
one behaviour of this tool that mattered, and it is the behaviour that got
exercised first.

**What the run did establish, and what it did not.**

- **The re-ask's effectiveness remains n=1.** It is no better measured today
  than it was this morning. The review's existing statement — not sufficiently
  measured — stands unchanged.
- **The contract-failure base rate is now 2 observed failures across two
  samples.** F-33's corrected figure was 2 in 24; this run adds 0 more. The two
  samples are **not** simply addable, because their denominators are not the
  same kind of thing — see below.
- **A clean sample is not evidence the fault is gone.** At the ~8 % rate F-33
  records, sixteen consecutive clean generations is an unremarkable outcome, not
  a signal. The failure is intermittent; that intermittency is precisely why
  F-33 was wrong in the first place, and why one run — by anyone — settles
  nothing.

**A defect in the instrument, found by running it.** Eleven rounds of cross-host
review examined the probe's logic and none of them looked at what its three
queries actually do. Checking the traces afterwards:

| query | runs | reached the model | outcome |
| --- | --- | --- | --- |
| `answer` | 8 | 8 | answered |
| `refusal` | 8 | **0** | refused at `threshold`, before generation |
| `retraction` | 8 | 8 | refused at gate `llm` |

The refusal query is refused by the retrieval threshold gate, so **no generation
happens and no contract failure is possible**. A third of the sample could never
have contributed to the denominator, while still charging a budget unit each.
The honest size of this sample is therefore **16 generations, not 24 runs** —
and "24 runs" is exactly the sort of inflated denominator this probe was built
to prevent, reproduced by the probe itself.

Whether the earlier 24-run sample has the same problem is **unknown**: its
composition was not recorded. So the two cannot be pooled into a single rate
without inventing the missing information, and no pooled rate is published here.

This is the case for INV-6 in one line, again: the implementer built an
instrument against a wrong number, had it adversarially reviewed eleven times,
and the *first actual run of it* surfaced a defect that no amount of reading the
code had found.

### Still open

- **The re-ask's effectiveness.** Denominator 0 after 24 runs. Raising it needs
  either many more runs at ~8 % — roughly a dozen generations per observation —
  or a way to induce a contract failure that is honest about not being the
  natural event.
  With the query mix fixed, both remaining queries reach the model, so a
  24-run sample now buys 24 generations rather than 16.
- **The probe's query mix** — closed by rulings 2 and 5 above; the instrument
  itself is closed to further work.
