# Execution plan — Arken alignment & README optimisation (2026-07-26)

> **Revision 2**, incorporating the cross-host red-team review recorded in
> [docs/reviews/arken-alignment-2026-07-26.md](../reviews/arken-alignment-2026-07-26.md)
> (Codex, verdict `REVIEW_NEEDED`, 6×P0). Revision 1 is in git history.
>
> **Not a day node.** This is a job-search-facing work package covering the
> README, the docs surface, and four code changes that close named gaps in the
> §6 seven-pillar table. Filed under `docs/specs/` because the same authorship
> rules apply: the constitution (INV-1 – INV-8) outranks this file.
>
> **Authorship labels (INV-6)**: the Goal and every `[HUMAN]` row of §2 are
> transcribed from Yi Xin's 2026-07-26 directives in-session. Everything marked
> `[AI-drafted, pending approval]` is elaboration and is not effective until
> reviewed. Rows marked `[NEEDS RULING]` block the phases they gate — see
> Phase −1.

## 1. Goal — [HUMAN, transcribed from 2026-07-26 directives]

Make this repository land with Arken specifically: demonstrate that the author
understands their philosophy at its source (GOKM / Dawson's twelve-step
methodology), agrees with it, and has practised its central claim — design from
the frontline user — before knowing its name. Close the gaps that can be closed
with the evidence discipline the repo already enforces, and state the rest.

Standing constraints restated from the directives:

- **All red-team findings get fixed**, not triaged by severity (2026-07-18 and
  2026-07-19 rulings). Operationalised per F-06 below.
- **No claim of having read what was not read.** GOKM (Balafas, Jackson &
  Dawson, 2004) was not obtainable; only Dawson (2009) was read. Written into
  README §6.
- Repo output stays English (except `README.zh-CN.md`, whose status is a
  Phase −1 ruling, F-15).

### What "all findings get fixed" means operationally — [resolves F-06]

Every finding resolves into exactly one of three states, and **deferral is not
one of them**:

1. **Implementation defect** → patched in this work package.
2. **Governance conflict** (the only real fix would breach an invariant or an
   out-of-scope boundary) → becomes a **blocking human ruling** in Phase −1.
3. **Claim the repo cannot support** → the *claim* is removed or narrowed. This
   is always available, so no finding can end unresolved.

## 2. Decision provenance

| # | Decision | Source |
| --- | --- | --- |
| D1 | Do the Arken-alignment work in the shape proposed in-session | `[HUMAN]` |
| D2 | PM/dispatcher narrative + GOKM lineage note in the README | `[HUMAN]` — implemented 2026-07-26 |
| D3 | Red-team the plan **before** implementing | `[HUMAN]` — done; this is revision 2 |
| D4 | Phase order | `[NEEDS RULING]` — see Phase −1 |
| D5 | Owner data source: external map vs. sample-XML edit | `[NEEDS RULING]` |
| D6 | Corpus expansion target size | `[NEEDS RULING]` |
| D7 | External-citation policy under INV-5 | `[NEEDS RULING]` — blocks Phase 3 |
| D8 | Status of `README.zh-CN.md` as outward-facing output | `[NEEDS RULING]` |

## 3. Constraints verified against source — [AI-drafted, pending approval]

**C1 · Editing any sample XML invalidates the corpus manifest.**
`make_chunk_id` ([`chunking/base.py:54`](../../src/learnarken/chunking/base.py))
hashes `dmc|source_path|strategy|file_digest`, `file_digest` = md5 of the source
DM bytes. Editing a DM changes every chunk id in it; gate 6 (`verify_corpus`)
pins the exact chunk-id set. Corpus edit ⇒ forced re-index + manifest regen.

**C2 · Golden sets survive corpus edits.** `eval/golden/*.jsonl` keys relevance
on `dmc` + `source_path`, not chunk ids (verified on `day4.jsonl`). C1's blast
radius stops at the manifest and index, **not** at the human labels — but see
C6, which is the cost C2 does not cover.

**C3 · `responsiblePartnerCompany` is not in the synthetic corpus.** It exists
only in `samples/s1000d/`, marked reference-only and non-copyable by CLAUDE.md.
The synthetic packages do carry `security/@securityClassification`
(9 occurrences in package-a).

**C4 · Frozen Day 8 artifacts must not be silently re-measured** (paid judge
calls, published numbers).

**C5 · The trace format is versioned.** `TRACE_FORMAT` in
[`answer/trace.py`](../../src/learnarken/answer/trace.py) is written into every
trace file. Readers must accept **both** v1 and v2 — traces already committed
and cited from `docs/EVIDENCE.md` are v1, and breaking them retro-breaks
published evidence (F-16).

**C6 · Retrieval is post-filtered in every Vespa-backed mode.**
[`retrieval/__init__.py:92`](../../src/learnarken/retrieval/__init__.py):
"bm25 stays offline and filters *before* scoring … the Vespa-backed modes
retrieve first and filter after". Any authorisation work must change this, not
sit on top of it (F-01).

**C7 · An expanded corpus needs a re-annotated golden set.** Adding chunks —
especially hard negatives — creates chunks that may be genuinely relevant to
existing queries but unlabelled; they score as misses and depress recall for
annotation reasons, not retrieval reasons. Recall on corpus-v2 is **not
comparable** to recall on the current corpus unless the labels are redone
(F-07).

**C8 · Changing the candidate set perturbs a measured artifact.** Gate 7's
threshold lives in `eval/results/day5-refusal-threshold.json`. Work that alters
what enters the candidate list can move refusal behaviour silently (F-17).

## 4. Phases

A phase is done when its acceptance criteria pass **and** `make lint && make
test` is green. **One commit per phase; no frozen artifact is ever overwritten**
(F-18).

### Phase −1 · Blocking human rulings — [HUMAN, required before any other phase]

Nothing below Phase −1 starts until these are ruled. Each has a default that
takes effect only if explicitly approved.

| Ruling | Options | AI recommendation |
| --- | --- | --- |
| **D4** phase order | credibility-first (0→1→4a→S→2→3) vs. depth-first (S→1→0→…) | credibility-first *if* the first reader is a recruiter; depth-first if an engineer |
| **D5** owner source | external `owners.json` (no C1 churn, invented data, must be labelled Toy-scale per F-12) vs. adding `responsiblePartnerCompany` to sample XML (S1000D-faithful, costs re-index + manifest regen) | external map for this package; XML edit later, bundled with corpus-v2 when a re-index is happening anyway |
| **D6** corpus target | 500–800 chunks vs. larger | 500–800, because C7 makes annotation, not generation, the cost driver |
| **D7 / F-04** external-citation policy | (a) no borrowed figures at all; (b) allow them in a clearly fenced "Borrowed from the literature" block that INV-5 explicitly exempts — **requires a dedicated constitution commit** | (a) for now; Phase 3 rewrites to method-without-numbers. Also **removes the "£200M" figure already sitting in the uncommitted README §6** |
| **D8 / F-15** `README.zh-CN.md` | authoritative outward output vs. non-authoritative summary | declare it a non-authoritative translation in its own header |

### Phase 0 · Source snapshot + credibility scaffolding — [AI-drafted]

**0.0 (new, resolves F-05) — pin the sources before quoting them.** Commit
`docs/research/arken-source-snapshot-2026-07-26.md`: exact URL, access date and
verbatim quote per pillar, covering `/architecture`, `/work`, `/about` **and the
three pages not yet read — `/trust`, `/deploy`, `/whitepapers` (all verified
HTTP 200)**. Every Phase 1 acceptance criterion quotes *this file*, not my
paraphrase. If a snapshot quote contradicts the current README §6 mapping, the
README is corrected in this phase, before any code is written.

| Item | Files | Acceptance criterion |
| --- | --- | --- |
| 0.1 CI badge | `README.md` (+zh per D8) | Badge resolves to this repo's `ci.yml` run history |
| 0.2 Demo capture | `docs/assets/demo-retraction.gif` + `docs/assets/demo-retraction.trace.json` | GIF shows one unedited take; **the trace id visible in the GIF is committed alongside it** (F-19). If retraction cannot be triggered on demand, capture a real refusal and label it as such — never stage |
| 0.3 Reading router + TOC | `README.md` (+zh) | Three-tier entry block within the first 60 lines; **an anchor test asserts every in-repo link and `#anchor` in both READMEs resolves** (F-14) |
| 0.4 Promote §6 + llms.txt | `README.md` (+zh) | Header block points to §6 and invites an AI reviewer to `llms.txt` |

**Verification**: new `tests/test_readme_guards.py` (link + anchor resolution)
plus `uv run pytest -k "doc or link"`.

### Phase 1 · Four pillars, in code — [AI-drafted]

Every acceptance criterion quotes the Phase 0.0 snapshot.

**1.1 Gap as a distinct output class** — [resolves F-10]
- Source signal: `XREF-001` at
  [`validation/engine.py:366`](../../src/learnarken/validation/engine.py) — a
  `dmRef` resolving to a DMC absent from the package.
- **Definitional correction**: Arken's gap is about *admitted* knowledge, and
  `samples/package-b` is rejected at ingest, so a gap found there is
  pre-admission. Two kinds, named distinctly:
  `pre_admission_declared_missing` (package-b) and `admitted_declared_missing`
  — the latter requires a **new fixture that passes L0–L3 yet still declares a
  `dmRef` outside its package**. Only the second is claimed against pillar 4.
- New `src/learnarken/gaps.py`, `learnarken gaps <package>` CLI, JSON out,
  schema'd like the existing Pydantic models (F-20). Validator behaviour and
  exit codes unchanged.
- Acceptance: the new admitted fixture yields ≥1 `admitted_declared_missing`
  gap whose signature is the absent DMC; `samples/package-a` yields zero
  (verified today: `validate samples/package-a` → 0 errors, 0 warnings); gap
  output and refusal output are separate objects on separate surfaces.

**1.2 Refusal becomes a routed action item** — [resolves F-11, F-12]
- `why` exists; add `what would resolve it` per gate, mirroring the ingest
  `fix:` discipline; add `who should act` from the D5 source.
- **Honest labelling (F-12)**: if D5 selects the external map, the owner is
  project-authored synthetic data, not an S1000D-native field, and the README
  says so wherever pillar 3 is claimed.
- Acceptance: **one non-null routing test and one null-with-reason test** — the
  criterion cannot pass with an empty owner map. A fabricated owner is a
  failure; an explicit `null` with a reason is a pass only in the null test.

**1.3 Trace gains `sources_excluded` and `status`** — [resolves F-02, F-16]
- `sources_excluded`: candidates dropped below the rerank threshold, with score
  and threshold; later also authorisation exclusions from 1.4.
- `status`: per cited source, whether a newer issue exists — derived from
  **XREF-007** ("newer issue wins the index",
  [`engine.py:289`](../../src/learnarken/validation/engine.py)), **not**
  XREF-003, which is a DM↔DML mismatch rule and would be wrong in the normal
  case.
- Bump `TRACE_FORMAT`; readers accept **v1 and v2**; a test parses an existing
  committed v1 trace.

**1.4 Authorisation before reasoning** — [resolves F-01; the largest item]
- C6 means this is not a filter addition: clearance must be pushed into **BM25
  corpus construction** *and* into the **Vespa YQL before `nearestNeighbor`**,
  and graph fact-injection must draw only from admitted chunks.
- Acceptance: with a clearance below a DM's classification, the retrieval call
  itself never sees that DM (asserted at the query layer, not by inspecting the
  post-filtered result); the exclusion appears in `sources_excluded` with reason
  `authorisation`; the answer refuses or answers from admitted sources only.
- **Regression guard (C8, F-17)**: refusal rate over `eval/golden/day4.jsonl`
  measured before and after; any movement is reported, not absorbed.

**Verification**: `make lint && make test`; new `tests/test_arken_alignment.py`;
`docs/EVIDENCE.md` gains a row per new claim.

### Phase 2 · Deployment & scale honesty — [AI-drafted]

| Item | Acceptance criterion |
| --- | --- |
| 2.1 Air-gapped run | **Pin first (F-13)**: model + revision, quantisation, runner and version, hardware, seed, decoding config — recorded in the results JSON. Only then publish the degradation in BENCHMARKS.md. An unpinned number is not published |
| 2.2 "What changes at scale" | Table naming exact NN → ANN/HNSW, sharding, rerank batching, incremental index, graph hub caps, each with a named mechanism |
| 2.3 Cost/latency envelope | End-to-end p50, tokens/answer, $/query from committed traces, with the repro command |
| 2.4 `SECURITY.md` | Threat model; in-scope vs. explicitly out-of-scope (TLS, per-user authn) |

### Phase 3 · The business half — [BLOCKED on D7]

Closes the gap README §6 now names in its own voice. Under recommendation (a),
this section ships **as method without borrowed figures**: what Step 2 would
measure, what Step 4 would compare it against, what Step 10 would verify, and
the Step 5 note on value to the engineer who feeds the system — with the unit
economics from 2.3, which *are* reproducible here. Acceptance: every number is
reproducible from this repo with a command. No second category.

### Phase 4 · Delivery assets — [AI-drafted]

- **4a** `docs/arken-alignment.md`: seven pillars × snapshot definition × what
  exists × what is missing × Dawson twelve-step self-audit.
- **4b** English "Three AI proposals I rejected, and why", from the Chinese
  journals, each linked to its adjudication.
- **4c** One real code excerpt (citation verification + retraction) in §2.
- **4d** §10: résumé PDF link, explicit demo-token CTA.

### Phase S · Corpus v2 (separate track) — [BLOCKED on D6]

- New package `samples/corpus-v2/` (never edits an existing package, C1),
  self-authored synthetic (INV-1), with hard negatives — near-miss DMCs and
  procedures sharing vocabulary but not applicability.
- **New human-annotated golden set `eval/golden/day4-expanded.jsonl`** (C7).
  This, not generation, is the cost driver, and it is human work — AI may
  propose candidate labels, it may not decide them (INV-6).
- New artifact `eval/results/day4-expanded-ablation.json`, new generated
  BENCHMARKS block. **Frozen Day 4 and Day 8 artifacts are untouched** (C4);
  each table states which corpus it describes.

## 5. Out of scope — [AI-drafted]

- Building the goal layer (pillar 7) — README explains why.
- RDF/SPARQL beyond the existing dependency slice (ADR-0002).
- TLS / per-recipient session auth for the demo.
- Re-measuring any frozen Day 8 artifact (C4).
- Editing the constitution — **except** the D7 ruling, which if decided as
  option (b) *requires* a dedicated human-owned constitution commit.

## 6. Verification summary

```bash
make lint && make test
uv run python tools/gen_benchmark_tables.py --check
uv run pytest -k "doc or link or evidence or readme"
uv run learnarken gaps samples/<admitted-fixture>     # Phase 1.1
uv run learnarken query "APU automatic start sequence" # Phase 1.2
```

## 7. Status (as of 2026-07-27)

**Phase −1 — ruled.** D4 credibility-first · D5 external `owners.json`, labelled
Toy-scale · D6 500–800 chunks with a new human-annotated golden set · D7 **no
borrowed figures** · D8 `README.zh-CN.md` non-authoritative · 1.2 **option A**.
Transcribed with provenance in the review's Part 2.

**Phase 0 — done except 0.2.** Source snapshot (including the three pages that
had never been read), CI badge, reading router + anchor guard, §6 promoted.
**0.2 demo GIF is blocked on a human** — it needs the live stack and a screen
recording, and the plan forbids staging one.

**Phase 1 — done, and it changed two of its own claims.**

| Item | Outcome |
| --- | --- |
| 1.1 Gaps | Built. Found the structural boundary: a declared-missing module is an ingest *error*, so its package is never admitted — Arken's admitted-knowledge gap is unreachable behind a fail-closed gate. Ships `pre_admission_declared_missing`; the admitted class is computed and reported **empty** |
| 1.2 Refusal | Three parts (why / what would resolve / who should act), option A. Owner routes only from an admitted gap — which, per 1.1, routes nothing on this corpus. Stated, not hidden |
| 1.3 Trace | v2 with `sources_excluded` and per-citation `status` (from **XREF-007**, not the XREF-003 the plan named). v1 still readable |
| 1.4 Authorisation | Clearance inside the retrieval call: BM25 corpus construction and the Vespa YQL `where` ahead of `nearestNeighbor`; graph facts redacted; CLI `--clearance` and API field; verified live against the engine |

**Three red-team rounds, 32 findings, all accepted** (standing ruling "红队发现的
全修" + "该改的都改，不管是不是自己的烂摊子"). One deferred with reason
(per-query `analyze_package` cost). Round 3's P0 — graph facts carrying
classified DMCs into the prompt — was the most serious defect of the work
package and was found only because the review was re-run on the *whole* state
after the fixes, not just on the new diff.

**Repo-wide cleanups authorised by the same ruling**: lint extended to the whole
repository in `make lint` and CI (the scope gap that let `tools/` and `deploy/`
drift), and the Vespa validation-override that expired 2026-07-23 removed.

**Outstanding**: Phase 0.2 · Yi Xin's independent number re-run (INV-6) ·
Phases 2, 3, 4, S · nothing committed yet.

## 8. Applied corrections already made (2026-07-26, before implementation)

- README §6 "built against" → "**retrospectively audited** against", with the
  reason inline (F-08). Mirrored in zh-CN.
- README §1 "every benchmark reports both" → narrowed to the retrieval
  ablation, with the constitution's overstatement recorded rather than
  propagated (F-09). Mirrored in zh-CN. The constitution itself is untouched —
  human-owned.
