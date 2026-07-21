# Day 13 design discussions — 性能与推理策略实验日

> **AI-distilled** (Claude, 2026-07-20, pending human review). Distills the
> decisions made in the Day 13 working session. The slice scope came earlier
> ([day11-13-planning.md](day11-13-planning.md) Decision 3); this memo records
> what was decided *this* day. Authority is the SPEC decision layer
> ([docs/specs/day13.md](../specs/day13.md)); this is a labelled summary.

## Framing decision

Yi Xin reframed the day as a **性能与推理策略实验日** whose deliverable is
**verifiable engineering judgment, not flashy optimization**. The load-bearing
consequence: **each experiment may honestly conclude "no benefit / not justified"
and still count as a *passing* result** — a flat mp scaling curve, a "no numba
target justified" record, a ToT that does not beat single-shot. This is the Day 4b
"证据说话、不涨照报" discipline made the day's explicit success criterion, not a
risk to hide.

## Decisions (rationale captured; full text in SPEC)

1. **mp shard granularity = per-DM-file, not "replicate N whole packages".**
   *Why:* replicating packages manufactures fake I/O and memory load — the
   benchmark would not represent real scaling. DM-file granularity is closer to the
   real ingestion pipeline and makes result-merging and error-localization easier.
   Requirement: parallel result **must equal the single-process deterministic
   baseline**; report wall / workers / speedup / overhead together and state a small
   corpus may not speed up.

2. **numba only on profiler-proven pure-numeric hotspots; "no target" is a pass.**
   *Why:* refusing to force a résumé keyword. Profiling runs **first**; only
   pure-numeric / loop-dense / type-stable functions qualify; XML / Pydantic / lxml
   XPath / model inference are excluded. If nothing qualifies, the deliverable is a
   recorded **"no numba target justified"** — a passing result.

3. **ToT diversity = heterogeneous 3-role + low/mid-low temperature (preferred);
   deterministic-validator selection.** *Why:* repair/validation needs
   **explainable strategy diversity**, not creative-writing randomness — so
   distinct roles (conservative / schema-focused / reference-focused) beat pure
   high-temperature sampling. Each candidate carries rationale / target-finding /
   patch-summary / risk-note; the winner is chosen by the **deterministic sandbox
   validator, never LLM self-judgment** (INV-4).

4. **ToT eval over package-b full repair-eligible cases; report k/n.** *Why:* small
   samples must not be laundered into percentages. Report attempted-n,
   candidates/case, validator-pass, human-review-needed, no-fix/refused, regression
   — all k/n; label small-n **"toy-scale / directional only"**; compare against the
   single-shot baseline; **if ToT does not improve, record the failure reason + next
   hypothesis** (INV-7).

5. **Rust = open-door gate only.** No crate, no Rust code, no build change this day
   — only the four gate conditions written as Roadmap (informed-consumer stance:
   BM25=Tantivy, vector store already Rust).

6. **free-threading = narrative only.** No install, no benchmark; a single
   paragraph that does **not** claim a gained benefit; 3.12 / mp / external-calls
   remains the project's center.

## The one genuine discussion point — asyncio scope (raised by Claude, ruled by Yi Xin)

Claude flagged a **decision-layer divergence**: planning Decision 3 listed asyncio
as Track A layer 1 and the unknowns scan (A1) pinned its honest target to the
external-API batch loops, **but the day's four-experiment framing did not list
asyncio**. Rather than silently defaulting, this was surfaced as an OPEN item.

**Yi Xin's ruling (Decision 7):** asyncio **is** in — as a **minimal I/O-bound
orchestration experiment, strictly separated from multiprocessing**. The division
of labor is the point:

- **multiprocessing** = CPU-bound (per-DM validation, chunking, the profiling
  experiment).
- **asyncio** = I/O-bound orchestration (concurrent LLM-judge / repair-candidate
  evaluation, subprocess/status polling, async HTTP health checks).
- **Forbidden:** wrapping a CPU hotspot in `async def` to fake concurrency; async
  lxml/Pydantic validation; a blocking heavy task inside a FastAPI route; a
  keyword-driven whole-codebase async rewrite.

Requirements: a **Semaphore** concurrency limit + **per-task timeout**; a single
task's failure does not cancel the experiment (non-fail-fast default); outcomes
recorded as **success / timeout / error**; **sync baseline vs asyncio** control with
wall / task-count / limit / error-count; if no gain, record why (too few tasks /
CPU-bound / external-API rate limit).

**Resolution folded into the SPEC:** asyncio's concrete target this day is the
**concurrent generation + sandbox evaluation of the ToT candidates** — the seam
planning called out (scan B6), matching Yi Xin's "repair-candidate evaluation"
example. This also resolved the secondary open item: **mp covers validation +
chunking; eval is dropped from mp** because its orchestration is I/O-bound and
belongs to asyncio.

## Honesty threads carried in (from memory)

- Non-deterministic generators (ToT): repeat-test, report robust not noise-mean
  ([[honest-nondeterministic-eval]], [[verify-real-signal-before-acting]]).
- Benchmark denominator discipline: distribution not single point, fixed seed,
  data-size denominator (INV-5); numba warm-up excluded from timing.
- Toy-scale privilege declaration (INV-7): a flat/negative result is reported, not
  buried.
