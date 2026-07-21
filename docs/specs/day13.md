# SPEC — Day 13: 性能与推理策略实验日 (`v1.3.0`)

> Decision layer **AI-summarized from Yi Xin's session directives (2026-07-20)
> + the already-adjudicated Day 11–13 planning decision**
> ([docs/discussions/day11-13-planning.md](../discussions/day11-13-planning.md)
> Decision 3), **pending human review** — this session's instruction was "我给你
> 信息，你来总结转录". Provenance is marked per item: `[HUMAN, transcribed]` = a
> Yi Xin ruling this session or an adjudicated planning decision; `[AI-drafted,
> pending approval]` = elaboration; `[OPEN — needs Yi Xin]` = a decision-layer
> point not yet ruled, drafted with the scan's proposed position for Yi Xin to
> confirm or overturn. Nothing in the decision layer is AI-invented; open items
> are flagged, not silently defaulted.
>
> **Framing (HUMAN).** This is a **性能与推理策略实验日** — the deliverable is
> **verifiable engineering judgment, not flashy optimization**. The experiments,
> each of which may honestly conclude "no benefit / not justified" and still count
> as a *passing* result: (1) does multiprocessing give **measured** benefit on
> **per-DM validation / chunking** (CPU-bound); (2) is numba used **only on real
> profiler-proven hotspots**, never for a résumé keyword; (3) does ToT give a
> **quantifiable** improvement on package-b repair/diagnosis; (4) Rust and Python
> free-threading are **gate/narrative only — not in the implementation mainline**;
> plus a **minimal asyncio orchestration experiment** (Decision 7) for the
> **I/O-bound** side — concurrent ToT candidate evaluation — **strictly separated
> from mp** (no `async def` around CPU hotspots).
>
> **Daily-cycle note.** Step 1 研→读→扫 is complete **before** this SPEC: 研 =
> two DR reports archived —
> [day13a-LLM 推理期搜索](../gemini-deepresearch/day13a-LLM%20Inference%20Search%20Research.md)
> + [day13b-Python 性能与并发调研](../gemini-deepresearch/day13b-Python性能与并发调研.md);
> 扫 = [docs/research/day13-unknowns.md](../research/day13-unknowns.md) (A1–A7,
> B1–B6); tutorial [16-performance-engineering.md](../tutorials/16-performance-engineering.md).
> The scan's positions feed the elaboration layer.
>
> **Constitutional note.** INV-1 (synthetic-only): package-b is the existing
> synthetic-with-known-violations package; **no new real data**, no replication of
> real packages. INV-2 (distribution): the mp shard sits **behind an abstraction**,
> writes are **idempotent**, **no shared-memory shortcut** — worker gets a shard
> *description* (DM file path), not a live parsed tree (Decision 1). INV-4
> (fail-closed): ToT final selection is decided by the **deterministic validator**,
> never LLM self-judgment; reward-hacking patches are vetoed (Decision 3). INV-5
> (determinism / denominator): every benchmark reports fixed seed, data-size
> denominator, warm/cold state, and a **distribution not a single point**; numba
> warm-up is excluded from timing (Decision 2). INV-7 (toy-scale honesty): small
> corpus may not speed up; ToT may not improve; numba may not fit — all reported
> as **"toy-scale / directional only"**, never inflated. INV-8 (slippage): Rust
> and free-threading are **already out of the implementation mainline** (Decisions
> 5–6); within Track A, validation-mp is the must-have and chunking-mp is the first
> cut (eval is not an mp target, Decision 7a); the ToT half is a **half-day toy** and
> its breadth is cut before its honesty (k/n reporting stays).

## Goal (one sentence) — [HUMAN, transcribed from 2026-07-20 directives + planning Decision 3]

Run a **性能与推理策略实验日** whose deliverable is **verifiable engineering
judgment**: (1) measure whether **multiprocessing** gives real speedup on package
validation / chunking via **DM-file-granularity sharding** checked against a
**deterministic single-process baseline**; (2) apply **numba only on
profiler-proven pure-numeric hotspots**, recording **"no numba target justified"**
as a *passing* result when none exists; (3) measure whether **Tree-of-Thoughts**
(**heterogeneous 3-role candidates + deterministic-validator selection**) gives a
**quantifiable, k/n-reported** improvement over single-shot repair on **package-b**;
and (4) keep **Rust and Python free-threading as gate/narrative only, never in the
implementation mainline**; plus (5) a **minimal asyncio orchestration experiment**
for the I/O-bound side (concurrent ToT candidate evaluation), **strictly separated
from mp** — tagged `v1.3.0`.

## Key Decisions

1. **mp shard granularity = per-DM-file, NOT "replicate N whole packages".**
   `[HUMAN, transcribed — Yi Xin 2026-07-20]` **Reason (HUMAN):** replicating N
   packages manufactures fake I/O and memory load — the benchmark would not
   represent real scaling; DM-file granularity is closer to the real ingestion
   pipeline and easier to merge results and localize errors.
   **Requirements (HUMAN):** (a) each worker processes **one or a batch of DMC
   XML**; the main process **merges findings / chunks / timing**. (b) the result
   **must be equivalent to the single-process deterministic baseline**. (c) the
   benchmark report must give **wall time, worker count, speedup, overhead**
   simultaneously, and **state that a too-small corpus may not speed up**.

2. **numba only on profiler-proven real hotspots; "no target" is a passing result.**
   `[HUMAN, transcribed — Yi Xin 2026-07-20]` Accept "may not fit, honest trace";
   **no forcing numba for a résumé keyword.** **Requirements (HUMAN):** (a) **run
   profiling first, list top hotspots**. (b) only a **pure-numeric, loop-dense,
   type-stable** function may be attempted. (c) **XML parsing, Pydantic models,
   lxml XPath, LangChain / model inference are NOT numba targets.** (d) if there is
   no suitable hotspot, the SPEC **requires a recorded "no numba target justified"
   output — this counts as a passing result, not a failure.**

3. **ToT diversity = heterogeneous 3-role + low/mid-low temperature (preferred);
   final selection by deterministic validator.** `[HUMAN, transcribed — Yi Xin
   2026-07-20]` Compare three approaches — (a) temperature diversity; (b)
   heterogeneous 3-role prompts, e.g. **conservative fixer / schema-focused fixer
   / reference-focused fixer**; (c) temperature + role combined — but the
   implementation **may pick the minimum viable**, and the SPEC **prefers (b) + low
   or mid-low temperature over pure high-temperature random sampling**. **Reason
   (HUMAN):** repair/validation needs **explainable strategy diversity**, not
   creative-writing randomness. **Requirements (HUMAN):** (a) each thought /
   candidate must carry **rationale, target finding, proposed patch summary, risk
   note**. (b) the final choice **must be re-verified by the deterministic
   validator — the LLM must not judge its own success** (INV-4).

4. **ToT evaluation scope = package-b full repair-eligible cases; report k/n.**
   `[HUMAN, transcribed — Yi Xin 2026-07-20]` Evaluate over **package-b's full
   findings / repair-eligible cases**; **report k/n, not only percentages**.
   **Must report (HUMAN):** attempted cases `n`; generated candidates per case;
   **validator-pass** `k/n`; **human-review-needed** `k/n`; **no-fix / refused**
   `k/n`; **regression** `k/n`. **Small sample ⇒ label "toy-scale / directional
   only", no exaggeration.** **Baseline comparison:** single-shot repair / the
   existing repair agent **vs** ToT. **Accepted outcome:** ToT need not improve; if
   it does not, **record the failure reason and the next hypothesis** (INV-7).

5. **Rust = open-door gate only, not the Day-13 implementation mainline.**
   `[HUMAN, transcribed — Yi Xin 2026-07-20]` Write **when Rust would be
   considered**: (i) the profiler shows a **pure-CPU hotspot at a significant share
   of total time**; (ii) Python **multiprocessing / algorithmic fixes have already
   been tried**; (iii) the hotspot's **input/output boundary is stable**; (iv)
   **Rust FFI / packaging cost < expected benefit**. **Day 13 writes no Rust, builds
   no crate, changes no build system** — only a **Roadmap gate** in the SPEC.

6. **Python free-threading = narrative / future direction only, not an acceptance
   item.** `[HUMAN, transcribed — Yi Xin 2026-07-20]` **No** free-threading Python
   install, **no** benchmark. Statement only: the project currently centers on
   **Python 3.12, multiprocessing, external model calls**; free-threading's
   compatibility with **lxml / Pydantic / ML libraries** still needs future
   measurement. **Do not write free-threading as a benefit already gained.**

7. **asyncio = a minimal I/O-bound orchestration experiment, strictly separated
   from multiprocessing.** `[HUMAN, transcribed — Yi Xin 2026-07-20]` **Positioning
   (HUMAN):** asyncio is **not** a replacement for multiprocessing; it is **only**
   for **I/O-bound orchestration** — concurrently scheduling external-service
   requests, file/subtask status polling, LLM/judge call orchestration, SSE/HTTP
   waiting-type work. **CPU-bound work** (XML parsing, validation, chunking, BM25
   scoring, rerank / model inference) **does not get force-wrapped in asyncio** —
   it stays synchronous / multiprocessing / as-is.
   **Requirements written into SPEC (HUMAN):**
   - **(7a) Clear mp/asyncio division of labor:** multiprocessing = CPU-bound /
     per-DM validation / chunking / profiling experiment; asyncio = I/O-bound /
     many-waiting-tasks / orchestration layer. **No `async def` wrapped around a
     CPU hotspot to fake concurrency.**
   - **(7b) One minimal asyncio experiment, small scope:** e.g. an async
     orchestrator concurrently scheduling multiple LLM-judge / repair-candidate
     evaluations; or async subprocess/status polling; or async HTTP health checks
     for Vespa / Neo4j / API. **Do not rewrite the main pipeline.**
   - **(7c) Control required:** **sync baseline vs asyncio orchestration**;
     report **wall time, task count, concurrency limit, error count**. If no clear
     benefit, **honestly record why** (too few tasks, CPU-bound bottleneck,
     external-API rate limit).
   - **(7d) Throttle + timeout required:** a **Semaphore** concurrency limit; **each
     async task has a timeout**; a single task's failure must **not** cancel the
     whole experiment unless the SPEC explicitly declares fail-fast; the output
     records **success / timeout / error**.
   - **(7e) Forbidden:** no async lxml/Pydantic validation; no async CPU-heavy
     loop; no synchronous heavy task run inside a FastAPI route blocking the event
     loop; no keyword-driven async-ification of the whole codebase.

### Rulings that resolved the prior open items (2026-07-20)

- **asyncio scope → RULED (Decision 7).** asyncio **is** in scope, as the minimal
  orchestration experiment above. Its concrete target this day is the **concurrent
  generation + sandbox evaluation of the 3 ToT candidates** (Decision 7b's
  "repair-candidate evaluation" example) — the seam planning called out (scan B6);
  an optional async HTTP health-check for Vespa/Neo4j/API is a permitted minimal
  alternative. **Not** a rewrite of the main pipeline (7e).
- **Track A mp targets → RULED (Decision 7a).** multiprocessing covers **per-DM
  validation and chunking** (both CPU-bound). **eval is dropped from the mp scope**
  — evaluation orchestration (LLM-judge / candidate) is **I/O-bound and belongs to
  the asyncio experiment**, not mp. Profiling (Decision 2) is its own experiment.

---

## Interfaces — [AI-drafted, pending approval]

### Track A · 1. mp sharding behind an abstraction (INV-2) — `src/learnarken/perf/shard.py` (new)

- `run_sharded(shards: Sequence[ShardSpec], worker_fn, *, workers: int) ->
  MergedResult` over `concurrent.futures.ProcessPoolExecutor` (symmetric with a
  thread-pool, testable; DR B §实操要点). `ShardSpec` is a **lightweight
  description — a DM-file path (or a batch of DMC XML paths) — never a parsed
  `etree`** (Decision 1(a); DR B 铁律 "传分片描述不传数据"). Worker reads its own
  slice, returns `{findings, chunks?, timing}`; the main process **merges
  deterministically** (findings sorted by the existing `validation.engine._issue_key`
  so output is byte-equal to the single-process baseline, Decision 1(b)).
- **Serial-fraction honesty (Amdahl, scan A2/A6):** the **cross-file
  parse/resolve/merge段** — duplicate-DMC resolution and package-level reference
  integrity (`engine._resolve_dm_identities`, `_crossfile_findings`) — needs the
  **whole package** and therefore **stays serial**. This is the concrete Amdahl
  serial fraction and must be named in the report, not hidden.
- Shard targets (Decision 7a, both CPU-bound): **validation**
  (`validate_package` / `analyze_package`,
  [validation/engine.py](../../src/learnarken/validation/engine.py)) and
  **chunking** (`chunking/`). **eval is NOT an mp target** — its LLM-judge /
  candidate orchestration is I/O-bound and goes to the asyncio experiment
  (Decision 7a). Within Track A, validation is the must-have and chunking is the
  first slippage cut (INV-8).

### Track A · 2. mp scaling benchmark — `tools/day13_mp_bench.py` → `eval/results/day13-mp-scaling.json`

- Runs the sharded validation over **DM-file shards** at **workers ∈ {1, 2, 4, 8}**,
  fixed seed (INV-5). Emits per-worker-count `{wall_time, speedup_vs_serial,
  overhead, worker_count}` **as a distribution over repeats, not a single point**
  (scan A6). Asserts **result-equivalence to the single-process baseline**
  (Decision 1(b)) — the benchmark fails if parallel findings ≠ serial findings.
- **Platform caveats recorded (scan A2):** macOS **spawn** (not fork) start cost,
  the `if __name__ == "__main__"` guard, and any Docker CPU-quota effect on
  `os.cpu_count()`. The report **explicitly states a too-small corpus may not
  speed up** (Decision 1(c)) — a flat/negative curve is a *valid, reported*
  result, not a failure to hide.

### Track A · 3. Profiling + numba decision — `tools/day13_profile.py`, `docs/notes/day13-numba-decision.md`

- `tools/day13_profile.py` runs **py-spy** (sampling, flame graph, `--native` to
  see into lxml's C ext) **and** cProfile (deterministic cross-check) over the
  index / validate / eval paths; dumps **top hotspots** → `eval/results/day13-hotspots.json`
  (Decision 2(a)). Measure-before-optimize (scan must-master #5).
- **numba gate (Decision 2):** a hotspot is a numba candidate **only if** it is
  **pure-numeric, loop-dense, type-stable** (Decision 2(b)); XML parsing / Pydantic
  / lxml XPath / model inference are **excluded** (Decision 2(c)).
  - **If a qualifying hotspot exists** (e.g. an RRF fusion or cosine-scoring numeric
    loop): three-column compare **pure-Python / numpy / numba** in
    `eval/results/day13-numba.json`; `@njit(nopython=True, cache=True)`, **warm-up
    excluded from timing** (scan A4); small gain reported small (Day 4b).
  - **If no qualifying hotspot exists:** write `docs/notes/day13-numba-decision.md`
    recording **"no numba target justified"** with the profiler evidence — **this
    is a passing result** (Decision 2(d)). No numba code is added in that case.

### Track B · 4. ToT repair — `src/learnarken/repair/tot.py` (new)

- `tot_repair(finding: Finding, *, roles: Sequence[Role], temperature: float) ->
  ToTResult`. Generates **k candidates** (default k=3) via **heterogeneous role
  prompts** (Decision 3 preferred (b)): `conservative_fixer`, `schema_focused_fixer`,
  `reference_focused_fixer` — at **low / mid-low temperature** (not high-temp
  random). Reuses [repair/agent.py](../../src/learnarken/repair/agent.py) (today
  `temperature=0.0`, single candidate — scan B1) and [repair/prompt.py](../../src/learnarken/repair/prompt.py).
- Each `Candidate` is a schema-constrained model carrying **`rationale`,
  `target_finding`, `patch_summary`, `risk_note`** (Decision 3(a)) plus the patch.
- **Selection = deterministic validator, not LLM judge (Decision 3(b), INV-4):**
  every candidate is re-verified in the **dry-run sandbox**
  ([repair/sandbox.py](../../src/learnarken/repair/sandbox.py)) — the **perfect ORM
  / engineering world-model** (scan B2); the winner is the validator-passing
  candidate. **Reward-hacking veto (scan B3, reuse Day 7):** a candidate whose diff
  deletes > a configured fraction of the source or empties a key data region is
  vetoed regardless of sandbox pass, reusing the existing
  [repair/apply.py](../../src/learnarken/repair/apply.py) / `repair/core.py:83`
  high-risk-class gate — not re-invented.
- **Concurrency = the asyncio experiment (Decision 7):** candidate generation +
  sandbox evaluation is the **I/O-bound orchestration** target. The orchestrator
  lives in `src/learnarken/perf/orchestrate.py` (Interface 7); `tot.py` calls it.
  The sandbox subprocess exec and the LLM candidate calls are the waiting-type work
  asyncio schedules; the CPU-bound validator logic itself is **not** made async
  (Decision 7e).

### Track B · 5. ToT evaluation — `tools/day13_tot_eval.py` → `eval/results/day13-tot.json`

- Scope: **package-b full repair-eligible findings** (Decision 4). For each case,
  run **baseline single-shot** (existing agent, temp 0) **and** ToT (k candidates
  + validator selection). Fixed seed; record generation trace for reproducibility
  (DR A §7.3).
- Reports, all as **k/n not just %** (Decision 4): `attempted=n`, candidates/case,
  **validator-pass k/n**, **human-review-needed k/n**, **no-fix/refused k/n**,
  **regression k/n** — for **both** baseline and ToT, side by side. **FSR is the
  compound boolean** (target violation fixed **AND** no new violation introduced —
  DR A §7.1), not "sandbox stopped erroring".
- **Token cost two columns (planning Decision 3 / scan B4):** prompt vs completion
  tokens; 3 candidates ≈ 3× completion, prompt may be 1× under caching. The report
  frames the **funnel-fallback** narrative (single-shot first, ToT only on failure)
  and the marginal-ROI question — **"when is search not worth it" is the interview
  asset** (planning). Small-n ⇒ **"toy-scale / directional only"** (Decision 4,
  INV-7); if ToT does not beat baseline, the **failure reason + next hypothesis**
  are recorded (Decision 4).

### Track B/asyncio · 7. asyncio orchestrator + benchmark (Decision 7) — `src/learnarken/perf/orchestrate.py` (new), `tools/day13_async_bench.py` → `eval/results/day13-async.json`

- `orchestrate.py`: `async def run_bounded(coros, *, limit: int, timeout: float) ->
  list[TaskOutcome]` — a **Semaphore(limit)**-throttled runner (Decision 7d) using
  `asyncio.TaskGroup`; **each task wrapped in `asyncio.timeout(timeout)`**; a
  single task's failure is captured as a `TaskOutcome{status: success|timeout|error}`
  and **does not cancel siblings** (non-fail-fast default, Decision 7d). This is the
  **I/O-bound orchestration layer only** — it schedules waiting-type work (LLM
  candidate calls, sandbox subprocess exec), **never** wraps CPU logic (7a/7e).
- **Primary experiment target (Decision 7b):** concurrent **ToT candidate
  generation + sandbox evaluation** (the seam, scan B6) — `tot.py` uses
  `run_bounded` to schedule the k candidates. `tools/day13_async_bench.py` runs
  **sync baseline vs asyncio orchestration** over the package-b ToT cases and
  reports **wall time, task count, concurrency limit, error count** (Decision 7c),
  fixed seed (INV-5), distribution not single point (scan A6). **If no clear
  benefit**, the report records **why** (too few tasks / CPU-bound / external-API
  rate limit — MiniMax `429`, memory `minimax-vision-channel`) (Decision 7c) —
  a flat result is a *valid, reported* outcome.
- **Optional minimal alternative (Decision 7b):** an async HTTP health check
  fanning out to Vespa / Neo4j / API endpoints — permitted if the ToT-candidate
  orchestration proves too small to show a signal; same control/throttle/timeout
  contract.

### Track A · 6. Rust & free-threading — docs only (Decisions 5–6)

- **Rust open-door gate:** a Roadmap section (in this SPEC / a short ADR note) with
  the **four gate conditions** (Decision 5 i–iv) and the honest "informed consumer"
  stance (BM25 = Tantivy, vector store already Rust — scan A5). **No crate, no
  build change, no Rust code** (Decision 5).
- **free-threading:** one **narrative paragraph** (Decision 6) — project centers on
  3.12 / mp / external calls; free-threading vs lxml/Pydantic/ML compat needs future
  measurement; **not written as a gained benefit**; **no install, no benchmark**.

## Acceptance Criteria — [AI-drafted, pending approval]

1. **mp equivalence + report (Decisions 1, 7a):** sharded **validation** (and
   chunking) over DM-file shards produces results **byte-equivalent to the
   single-process baseline** (asserted), and `eval/results/day13-mp-scaling.json`
   reports **wall time, worker count, speedup, overhead** for workers ∈ {1,2,4,8}
   as a **distribution**, with an explicit **"small corpus may not speed up"** note
   and the named Amdahl serial fraction (**cross-file parse/resolve/merge**). eval
   is **not** an mp target. INV-2 holds (shard-description passed, not data;
   idempotent; no shared memory).
2. **Profiling first (Decision 2):** `eval/results/day13-hotspots.json` lists top
   hotspots from py-spy + cProfile **before** any numba code exists.
3. **numba gate (Decision 2):** *either* a qualifying pure-numeric hotspot gets a
   **pure-Python / numpy / numba three-column** result (`@njit`, warm-up excluded,
   small gain reported small) *or* `docs/notes/day13-numba-decision.md` records
   **"no numba target justified"** with evidence — the latter is a **passing**
   result. No numba on XML/Pydantic/XPath/inference paths.
4. **ToT candidates are explainable + validator-selected (Decision 3):** each
   candidate carries **rationale / target_finding / patch_summary / risk_note**;
   candidates come from **heterogeneous roles at low/mid-low temperature**; the
   winner is chosen by the **deterministic sandbox validator, never LLM
   self-judgment**; reward-hacking patches are vetoed. Asserted with a mocked LLM
   producing distinct role candidates and a sandbox that deterministically selects.
5. **ToT eval k/n (Decision 4):** `eval/results/day13-tot.json` reports over
   **package-b full repair-eligible cases**, **baseline vs ToT**, as **k/n** for
   validator-pass / human-review-needed / no-fix-refused / regression, plus
   candidates/case and **two-column token cost**; small-n is labeled **"toy-scale /
   directional only"**; if ToT does not improve, the **failure reason + next
   hypothesis** are recorded.
6. **Rust = gate only (Decision 5):** the four gate conditions are documented; **no
   crate, no Rust code, no build-system change** exists in the diff.
7. **free-threading = narrative only (Decision 6):** a single non-benefit-claiming
   paragraph; **no** FT install or benchmark in the diff.
8. **asyncio orchestration experiment (Decision 7):** `eval/results/day13-async.json`
   reports **sync baseline vs asyncio** over concurrent ToT candidate evaluation
   with **wall time, task count, concurrency limit, error count**; the runner is
   **Semaphore-throttled with per-task timeout**, a single task failure does **not**
   cancel siblings, and outcomes are recorded as **success/timeout/error**; no clear
   benefit ⇒ the reason is recorded (7c). No `async def` wraps any CPU hotspot; no
   lxml/Pydantic path is made async; no blocking task runs in a FastAPI route (7e) —
   asserted by test + review.
9. **INV-5 across all benchmarks:** fixed seeds, data-size denominators, warm/cold
   state, distributions not single points; numba warm-up excluded from timing.
10. `make test` + `make lint` green; the existing suite (404 + 9 skip at Day 12
    HEAD) unbroken.
11. Cross-host `coding-adversarial-review` on the day's diff → findings in
    `docs/reviews/day13.md` Part 1 (automatic gate, before proposing merge).

## Out-of-Scope — [AI-drafted, pending approval]

- **No Rust code / crate / build change** (Decision 5) — Roadmap gate only.
- **No free-threading install / benchmark** (Decision 6) — narrative only.
- **No "replicate N whole packages"** (Decision 1) — DM-file granularity only.
- **No numba on XML / Pydantic / lxml XPath / model-inference paths** (Decision 2);
  no numba at all if no qualifying hotspot ("no target" is the deliverable).
- **No LLM-judge selection in the ToT loop** (Decision 3) — deterministic validator
  only.
- **No async-ification of CPU-bound code** (Decision 7e): no async lxml/Pydantic
  validation, no async CPU-heavy loop, no synchronous heavy task inside a FastAPI
  route blocking the event loop, no keyword-driven whole-codebase async rewrite.
  asyncio is confined to the minimal I/O-bound orchestration experiment (Decision 7).
- **No mp on eval** (Decision 7a) — eval orchestration is the asyncio target, not mp.
- **No new golden-corpus modality, no new real data** (INV-1) — package-b is the
  existing synthetic violation package.
- **No drive-by optimization** — every change traces to one of the four experiments
  or its measurement/reporting.

## Verification (how to check) — [AI-drafted, pending approval]

```bash
make test && make lint                                   # existing suite + day13 perf/tot green
# Track A — multiprocessing scaling (Decision 1)
uv run python tools/day13_mp_bench.py                    # → eval/results/day13-mp-scaling.json (1/2/4/8 workers; asserts == serial baseline)
# Track A — profiling + numba decision (Decision 2)
uv run python tools/day13_profile.py                     # → eval/results/day13-hotspots.json (top hotspots FIRST)
#   then either eval/results/day13-numba.json (3-column) OR docs/notes/day13-numba-decision.md ("no target justified")
# Track B — ToT vs single-shot on package-b (Decisions 3–4)
uv run python tools/day13_tot_eval.py samples/package-b  # → eval/results/day13-tot.json (baseline vs ToT, k/n, two-column tokens)
# asyncio — sync baseline vs orchestration on concurrent ToT candidate eval (Decision 7)
uv run python tools/day13_async_bench.py                 # → eval/results/day13-async.json (wall/task-count/limit/error-count; reason if no gain)
```

Then the automatic cross-host red-team gate on the diff →
`docs/reviews/day13.md` Part 1 → Yi Xin adjudicates (Part 2, human).
