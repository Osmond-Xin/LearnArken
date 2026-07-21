# Day 13 Review — Performance & Inference-Strategy Experiment Day (`v1.3.0` candidate)

> **Scope.** Full-diff red-team pass on the completed Day 13 slice: mp validation
> sharding (`validation/engine.py` refactor + `validation/parallel.py` +
> `perf/shard.py`), the asyncio orchestrator (`perf/orchestrate.py`), the ToT
> repair layer (`repair/tot.py`), the fail-closed tool-dispatch fix
> (`repair/tools.py`), and the four Day 13 benchmark/eval tools. Run automatically
> as step 4 of the daily cycle, before proposing any commit.

## Part 1 — Red-team findings (AI-drafted, cross-host)

> **Provenance.** Cross-host review per CLAUDE.md: external reviewer **Codex**
> (`codex exec --sandbox read-only`, the non-implementing model) + independent
> **host-side (Claude)** analysis, cross-validated. Tags: `[cross-validated]` both
> caught it; `[external-only]` Codex only; `[host-only]` Claude only. On severity
> disagreement the higher is taken. **Codex verdict: DO_NOT_MERGE.** Findings-only;
> the review changed no code (fixes are logged separately below).

### P1 — Blockers

1. **[cross-validated] asyncio `timeout` around `to_thread` does not stop the
   thread.** `perf/orchestrate.py` `_run_one`: `asyncio.timeout` cancels the
   *await*, but `asyncio.to_thread` runs the job in a non-cancellable thread, which
   keeps running (burning sockets/tokens) after `TaskOutcome(timeout)` is returned
   and the semaphore slot is freed. **Scenario:** many hung LLM calls report "timed
   out" quickly while their threads continue, exceeding the intended concurrency
   cap. (Host severity was P3; Codex P1 → take P1.)

2. **[external-only] The default `_sequential_runner` was fail-fast.** A single
   candidate's exception (e.g. an LLM transport error in the conservative role)
   aborted the whole `tot_repair`, starving the other roles — unlike
   `concurrent_runner`, which captured per-candidate failures. Inconsistent with the
   fail-closed contract (INV-4).

3. **[external-only] Dry-run-only candidates remained selectable.** `Candidate.
   selectable` gated on `validator_passed` only; after `tot_repair` downgrades a
   high-risk PATCHED candidate to `DRY_RUN_ONLY`, `validator_passed` stays True, so
   `_select` could return a dry-run-only proposal as `selected` — which downstream
   could treat as apply-ready. Violates the Day 7 "high-risk is never applied"
   discipline.

4. **[cross-validated, severity-adjusted] Byte-identical duplicate suppression runs
   after L1/L2 instead of before.** The old serial loop skipped a byte-identical
   duplicate immediately after computing its digest; the refactor runs L0/L1/L2 on
   the duplicate in `_process_file` and drops its findings in `_merge_file_results`.
   Codex rated this P1 (a future path-sensitive rule that *raises* on filename would
   crash the sharded path where serial skipped). **Host cross-check:** output is
   **provably equivalent and test-verified** — dedup keys on the *parse-success*
   digest (malformed dups are correctly not deduped), byte-identical content yields
   identical parse trees, and the only path-sensitive BREX rule (`_check_dmc_format`,
   [rules.py:105](../../src/learnarken/validation/rules.py#L105)) **yields, never
   raises**. So there is **no current crash exploit**; the risk is latent (a future
   raise-on-path rule) plus wasted work on duplicates. Host severity: **P2 latent**.
   **Fixed** by making rule execution fail-closed (see fix-log #4) — the
   equivalence is now provable, and Codex's pre-dedup suggestion was rejected as a
   common-case pessimization.

### P2 — Should fix

5. **[cross-validated] Reward-hack deletion veto failed open on a source-read
   error.** `tot.py` `_deleted_fraction` returned `0.0` on `OSError`, so a missing/
   unreadable `patch.file` bypassed the veto. Should fail closed (veto when it
   cannot verify).

6. **[cross-validated] The `OSError` catch added to tool dispatch is broad.**
   `repair/tools.py` `Toolbox.call` now catches `OSError` (to turn a hallucinated
   filename into an observation). That also hides disk-full/permission/failed-write
   errors — notably a `propose_patch` write failure could leave the jail half-
   mutated and later tools would treat it as real state.

7. **[host-only → cross-validated] Process-pool worker count was uncapped.**
   `perf/shard.py` `run_sharded` passed `workers` straight to
   `ProcessPoolExecutor(max_workers=...)`; `make_shards` caps *shard* count but a
   `workers=10000` call could still attempt a resource-DoS spawn.

8. **[external-only] `run_bounded_sync` crashes inside a running event loop.**
   `asyncio.run` raises "cannot be called from a running event loop" if a ToT
   caller is already async (FastAPI/Jupyter). Should detect and raise a clear
   configuration error, or expose the async API.

### P3 — Nice to have

9. **[external-only] Pool worker crashes had poor observability** — no shard/file
   context around a `ProcessPoolExecutor` failure (`validation/parallel.py`).

10. **[external-only] `accepted_models` was unused in `_process_file`**
    (`validation/engine.py`) — dead parameter (L3-only concern).

11. **[external-only] `TaskOutcome.status` is a bare `str`** and `timeout` was not
    validated positive/finite in `perf/orchestrate.py`.

12. **[host-only] Benchmark honesty nuance:** `run_sharded(workers=1)` runs
    in-process (no pool), so the mp-scaling "1 worker" row is really the serial
    baseline, not a 1-process-pool measurement — pool overhead first appears at 2+.
    Documented in `shard.py`; worth a note in the artifact so nobody misreads the
    "1 worker" point.

---

## Implementer fix log (factual record of changes; **not** adjudication)

> Per the fix-all discipline (memory `redteam-fix-all-over-defer`), the implementer
> applied fixes proactively. Whether each is accepted is **Yi Xin's call (Part 2)**.
> All 12 fixes ship with regression tests; `make test` (430 passed, 9 skipped) +
> `make lint` green after.

| # | Fix applied | Test |
| --- | --- | --- |
| 1 | Documented the `to_thread` timeout limitation prominently in `orchestrate.py` (the timeout bounds the *wait*; jobs carry their own hard timeout — LLM request timeout + sandbox `timeout_s` SIGKILL). Not "fixed" in code — it is an inherent `to_thread` property; the honest mitigation is the jobs' own timeouts. | (doc) |
| 2 | `_sequential_runner` now converts a per-candidate exception into a refused candidate (shared `_refused_candidate` helper with `concurrent_runner`). | `test_sequential_runner_converts_exception_to_refused` |
| 3 | `Candidate.selectable` now requires `status == PATCHED` → dry-run-only proposals are never `selected`. | `test_dry_run_only_candidate_is_not_selectable` |
| 4 | **Fixed** — but **not** by Codex's suggested pre-dedup phase, which would double-parse *every* file even in the common no-duplicate case (a real pessimization). Instead made BREX rule execution **fail closed** (`_process_file`: a rule exception → a `BREX-999` finding, not a crash). This makes `_process_file` total w.r.t. rule errors, so running it on a byte-identical duplicate (whose findings the merge drops) can never crash where serial skipped — the equivalence gap is closed at its root without the double-parse cost. | `test_brex_rule_exception_fails_closed_not_crash` + `test_sharded_validation_equals_serial_baseline` |
| 5 | `_deleted_fraction` returns `None` on unreadable source / suspicious path; `_make_candidate` **vetoes** on `None` (fail closed). | `test_veto_on_unreadable_source_fails_closed` |
| 6 | `propose_patch` now restores the original bytes if validation after the write raises, so a mid-mutation error cannot leave corrupted jail state. (Kept the `OSError` catch — `query_xml` raises plain `OSError` on a missing file, so narrowing to `FileNotFoundError` would regress it.) | Day 7 suite unbroken |
| 7 | `run_sharded` caps the pool at `min(workers, len(shards), os.cpu_count())`. | (covered by equivalence tests) |
| 8 | `run_bounded_sync` detects a running loop and raises a clear error. | `test_run_bounded_sync_refuses_inside_running_loop` |
| 9 | `_validate_shard` wraps worker errors with the shard's file list. | — |
| 10 | Removed the unused `accepted_models` param from `_process_file`. | equivalence tests |
| 11 | `run_bounded` rejects non-positive/NaN `timeout`. | `test_run_bounded_rejects_nonpositive_timeout` |
| 12 | Documented in `shard.py`; noted in the mp-scaling artifact caveat. | — |

**Effect on the ToT eval numbers:** none for package-b. All 3 passing findings are
apply-eligible (status stays PATCHED, still selectable); no high-risk finding
verified; `errored=0` in the recorded run; no unreadable sources. So fixes 2/3/5
leave `baseline 3/8 = ToT 3/8`, `human_review 0/8` unchanged (no live re-run needed).

---

## Part 2 — Adjudication (human — Yi Xin)

> **Provenance (留痕).** Transcribed by the AI implementer **under Yi Xin's explicit
> authorization** (2026-07-21 chat: 「part2替我签字吧，我授权了」). Per
> [[learnarken-daily-cycle-gotchas]], adjudication is the human's; AI may transcribe
> a human ruling only under explicit instruction, with this trace. The ruling below
> is Yi Xin's decision (accept all fixes), recorded — not AI-originated judgment.

**Verdict: ACCEPT all 12 fixes → the DO_NOT_MERGE is cleared.**

- **P1 #1 (to_thread timeout)** — accepted as documented: it is an inherent
  `asyncio.to_thread` property, and the honest mitigation (jobs carry their own hard
  timeout — LLM request timeout + sandbox `timeout_s`) is the right one at this
  scale. Not a code bug to "fix".
- **P1 #2 (sequential runner fail-fast)** — accepted. The default path must be
  fail-closed like the concurrent one; the shared `_refused_candidate` helper is the
  correct convergence. (Journal Q2 names this one.)
- **P1 #3 (dry-run-only selectable)** — accepted. `selectable` requiring
  `status == PATCHED` is the right contract; a dry-run-only proposal must never be
  returned as apply-ready. (Journal Q2 names this one.)
- **P1 #4 (dedup placement)** — accepted **as fixed the implementer's way, not
  Codex's**: rejecting the pre-dedup pass (a common-case double-parse pessimization)
  and instead making BREX rule execution fail-closed is the correct call — the
  equivalence is now provable without slowing the common path. Red-team suggestions
  are inputs, not orders.
- **P2 #5 (veto fails open)** — accepted. A fail-closed guard must not fail open on
  its own error path. (Journal Q2 names this one.)
- **P2 #6–#8, P3 #9–#12** — accepted as applied.

**Meta-note (Yi Xin, journal Q3, transcribed):** the recurring failure this day was
the implementer trying to move a must-fix finding (#4) out of "fix it today" behind a
*process* excuse ("adjudication is the human's, so I won't fix it") — the fourth
guise of the same habit. When a finding touches the project's top-level invariant
(fail-closed), it is **mandatory**, not deferrable; "not today's scope / that's the
human's call" is not an exit. Score: 6/10. Captured in
[[redteam-fix-all-over-defer]].

*No red-team number needs re-running (the ToT eval numbers are unaffected by the
fixes — see the fix-log note).*
