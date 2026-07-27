# Red team — README refactor (2026-07-25)

Not a day node: this reviews the job-search-facing documentation refactor
(README.md / README.zh-CN.md rewritten, `docs/BENCHMARKS.md` created,
`tools/gen_benchmark_tables.py` retargeted, `docs/project-design.md` annotated).
Filed under the day-review convention because the same rules apply.

- **Reviewer**: Codex CLI (`codex exec --sandbox read-only`), routed cross-host
  by `adversarial-review/lib/call-external.sh` — the implementing model
  (Claude) did not self-review the findings half.
- **Host cross-validation**: Claude ran an independent pass and verified every
  external finding against source before it was recorded. Verification verdicts
  below are the host's; they are evidence, not adjudication.
- **External verdict**: `DO_NOT_MERGE` — 5×P1, 8×P2, 2×P3.

## Part 1 — Findings (AI, read-only)

Tags: `[cross-validated]` both reviewers found it · `[external-only]` Codex only
· `[host-only]` Claude only. `Verified` = host re-derived it from source or
artifacts. Fix status is a record of what was changed, **not** an adjudication.

### P1

**F-01 · Day 8 numbers do not reconcile with the committed artifacts**
`[external-only]` · **Verified — and worse than reported**
- Published: overall behavior pass rate `0.94 → 0.93`; intersection
  groundedness `0.53 → 0.63`; per-judge `0.60/0.60 → 0.63/0.69`.
- Artifacts: `day8-behavior-{before,after}.json` hold `mean_pass_rate`
  **0.9375 → 0.9167** — the published "after" is rounded the wrong way (0.9167
  → 0.92, not 0.93), in the flattering direction.
  `day8-adversarial-report.json` records per-judge **0.6875 / 0.75**,
  intersection **0.6875**. The frozen judge files score **0.70 / 0.6667** over
  n=30 answered rows. Three denominators are in play (32 cases vs. 30 judged).
- **Pre-existing**: these rows were carried into BENCHMARKS.md verbatim from the
  old README; the refactor propagated the drift, it did not create it.
- INV-5 breach. Only the X-01 row (3/3 → 0/3) is independently corroborated.
- **Fix applied (revised 2026-07-26 on Yi Xin's instruction — fix it, don't
  flag it)**: the correct values are fully derivable from the *frozen* artifacts,
  so no re-measurement was needed and none was done. `day8-adversarial-before.json`
  gives per-judge 0.60/0.60 and intersection 0.5333; `day8-adversarial-report.json`
  gives 0.6875/0.75 and 0.6875; the N=3 behaviour means are 0.9375 → 0.9167. The
  published "after" trio (0.63/0.63/0.69) was simply wrong — the corrected values
  are **higher**, so the error had been *understating* the groundedness gain while
  *overstating* the behaviour rate.
- **Root fix, not a patch**: the table is now a `<!-- BEGIN gen:day8-before-after -->`
  block rendered by `tools/gen_benchmark_tables.py` from those four artifacts, so
  `--check` and `tests/test_day4_closeout.py` guard it like every other table.
  The reason this drifted is that it was the one hand-typed table; that category
  no longer exists.

**F-02 · "Corpus never leaves" is false** `[external-only]` · **Verified**
- README §6 sovereignty row claimed the corpus never leaves the machine.
  Retrieved chunk text is sent to the remote chat model in the prompt
  (`answer/prompt.py`), and figure bytes go to the remote VLM (`multimodal/vlm.py`).
- **Root cause (found on Yi Xin's challenge — "if the conclusion is wrong, fix
  the implementation")**: this was not an unfinished feature, it was a **blocked**
  one. `config.py` required `MINIMAX_API_URL` to start with `https://`, and every
  local OpenAI-compatible model server (llama.cpp, vLLM, Ollama, TGI) serves
  `http://127.0.0.1:PORT/v1`. The config layer therefore rejected the only URL
  shape that could make the sovereignty claim true. "Swappable interface" was
  rhetoric; the code had closed the door.
- **Fix applied — implementation, not wording**:
  1. endpoint policy replaced with *https off-box, plaintext on loopback only*,
     with the host **parsed** (`urlsplit().hostname`) rather than prefix-matched,
     so `http://127.0.0.1@evil.example/v1`, `http://localhost.evil.example/v1`
     and the decimal form `http://2130706433/v1` all still fail closed;
  2. new hard egress fence `LEARNARKEN_LOCAL_ONLY=1` — a non-loopback endpoint
     raises instead of being called. Every consumer (chat, VLM, adversarial
     harness, API health probe, demo preflight) resolves through the single
     `load_minimax_config()`, so the fence has no sibling door;
  3. 11 tests in `tests/test_day5_answer.py::TestConfigHardening`, plus a live
     check against the real repo `.env`: the fence names the remote host and
     refuses before any network call.
- **Residual gap, stated in the README rather than papered over**: no local
  chat/VLM model is bundled, so under the default config content still leaves.
  The row now reads `Enforceable & tested — no local model bundled`, and
  `docs/local-services.md` documents the loopback setup end to end.

**F-03 · Universal fail-closed claim contradicted by a degraded path**
`[cross-validated]` · **Verified, with a correction to the reporter**
- §1 said "every stage's failure mode is stop". `graph_expand.py` returns `[]`
  and logs a warning when Neo4j is unreachable.
- Codex also cited `multimodal/ingest.py` as fail-open — **refuted**: a degraded
  figure is *recorded but not indexed*, and index-time re-verification withholds
  it. That is fail-closed.
- Also worth recording in the project's favour: the eval path does **not**
  inherit the degradation — `run_ablation` refuses up front on `graph.is_up()`.
- **Fix applied**: §1 now names the graph-route exception explicitly and states
  why eval is unaffected; §2's blanket sentence is scoped to the 16 gates.

**F-04 · DMC decomposition overclaims domain knowledge** `[cross-validated]`
· **Verified**
- The diagram glossed `29-10-00` as "hydraulic power → main system → **pump**".
  The assembly code `00` does not decode to "pump" — that comes from the module
  title. The repo ships no authoritative SNS/info-code dictionary; it models
  field *positions* and syntax only.
- **Host-only additions**: the ASCII leader bars were misaligned by one column
  for 5 of 7 segments; the diagram showed 3 of the 6 field groups the prose
  promises; the Chinese version additionally dropped the systemDiffCode line.
- **Fix applied**: diagram rebuilt with correct column alignment and all field
  groups, the "pump" gloss removed, and an explicit sentence added that the
  semantics come from the sample's own title, not from a decode table. Same in
  the Chinese mirror.

**F-05 · Evidence-guard claim exceeds what the tests cover** `[external-only]`
· **Verified**
- README §6 said a guard test "fails CI on a dead link or a drifted number".
  `tests/test_day9_evidence.py` guards links + the numbers tagged in
  EVIDENCE.md; `gen_benchmark_tables.py --check` guards the generated table
  blocks. Hand-written prose numbers elsewhere are unguarded — F-01 is the proof.
- **Fix applied**: the row now states the guard's exact scope and names the gap
  as a gap.

### P2

**F-06 · Reference cycles counted as a stopping gate but are warnings**
`[external-only]` · **Verified** — `XREF-005` is `Severity.WARNING`; the CLI
exits non-zero on errors only, so a cycle-only package validates with exit 0.
**Fix applied**: gate 4 row now separates the four rejecting errors from the
cycle warning, with the reason S1000D does not forbid cycles.

**F-07 · Gate 11 (G15) narrower than documented** `[external-only]` ·
**Verified** — the positive-grounding check runs only when *every* cited chunk
is a figure (`answer/engine.py`). **Fix applied**: scope stated in the README
gate row and in BENCHMARKS §7.

**F-08 · Corpus-manifest gate not enforced on all query paths**
`[external-only]` · **Verified** — `search_package` never calls
`verify_corpus`; the answer and eval paths do. **Fix applied**: gate 6 row now
says which commands enforce it, and notes the check covers both the manifest
and Vespa's actual doc ids.

**F-09 · Terminal transcripts are not literal output** `[cross-validated]` ·
**Verified** — the validation block showed 4 of 8 findings with no elision mark;
the query block was hand-wrapped; the HF cache warning was stripped; a `fix:`
line and a quote were truncated. Presented under "pasted from an actual run".
**Fix applied**: the framing now says excerpt + reflowed and names each edit;
elision markers added showing exactly how many findings are omitted.

**F-10 · `make test` described as "ruff + pytest"** `[external-only]` ·
**Verified** — the `test` target runs `uv run pytest`; lint is the separate
`make lint`. Pre-existing wording, repeated in the refactor. **Fix applied**:
Quickstart now runs `make lint && make test`; the hero row says lint is separate.

**F-11 · BENCHMARKS Day 3 note contradicts the §3 ablation command**
`[external-only]` · **Verified** — the parenthetical attached
`--strategy semantic` to a sentence about the structure-chunk ablation.
**Fix applied**: the parenthetical now says which command reproduces which row.

**F-12 · Chinese README is not a true mirror** `[external-only]` · **Verified**
— the gate table and CLI table are condensed there. **Fix applied (revised 2026-07-26)**: rather than
labelling the asymmetry, it was removed — the Chinese file now carries the full
four-lane 16-gate table and the ten-command CLI table, matching the English
section for section. `llms.txt` updated accordingly.

**F-13 · Architecture inventory still says the tables live in README**
`[cross-validated]` · **Verified** — three rows in
`docs/architecture/01-file-inventory.md`. **Fix applied**: all three updated,
with the migration date recorded.

### P3

**F-14 · Test-count claim not runnable in the reviewer's sandbox**
`[external-only]` · Static inspection supported it; the read-only sandbox could
not run pytest. Host had already re-measured both numbers directly
(439 collected; 427/12 offline, 430/9 with services). **No change needed**;
Codex's suggestion of a CI badge is recorded as a future option.

**F-15 · `tools/gen_vespa_query.py` interpolates args into YQL**
`[external-only]` · **Verified — kept, documented and hardened (2026-07-26, on
Yi Xin's instruction)**. It is a local developer tool: it writes a JSON payload
for a hand-driven `.http` request against the loopback dev container, never
talks to Vespa, and nothing in `src/` imports it. That is now stated in the
module docstring. It also no longer bypasses the production guards — it reuses
`STRATEGIES`, `_SAFE_PACKAGE` and `MAX_TOP_K` from `vespa.store`, because a
debug payload that skips production constraints stops reproducing production
behaviour. Verified: `--package '../etc'` is now rejected.

### Host-only findings

**F-16 · `docs/constitution.md` INV-5 says "every number appearing in the
README"** `[host-only]` — the benchmark tables now live in
`docs/BENCHMARKS.md`, so the invariant's literal text under-covers where the
numbers actually are. **Fix applied (2026-07-26, on Yi Xin's
instruction to apply the recommendations)**: INV-5 now reads "every number
appearing in an outward-facing document — README, README.zh-CN,
docs/BENCHMARKS.md, docs/EVIDENCE.md, resume". The amendment is **labelled
in-place as AI-drafted against a human-owned document** so it can be reverted
in one edit if that is not the intent. ← *still wants Yi Xin's confirmation*

## Part 2 — Adjudication (human-written, Yi Xin)

> Not drafted by AI. Per-finding accept / reject + rationale goes here.
>
> Status at hand-off (2026-07-26): all 16 findings are addressed in the working
> tree. Yi Xin directed that findings be *fixed at the implementation level
> rather than downgraded in prose*, which changed the outcome of F-01, F-02,
> F-12, F-15 and F-16 from "flag and defer" to "fixed" — those revisions are
> marked inline above. Two things still want a human signature rather than a
> rewrite:
>
> 1. **F-16** — INV-5's wording was amended by AI in a human-owned document
>    (labelled in place). Confirm or revert.
> 2. **F-01** — the corrected Day 8 numbers come from the frozen artifacts, not
>    from a re-run. If the live judge/generator numbers should be re-measured
>    before this is published, that run is yours (it costs model calls).
