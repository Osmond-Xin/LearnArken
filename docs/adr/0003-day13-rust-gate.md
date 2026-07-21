# ADR-0003: Rust open-door gate stays shut; free-threading is narrative only (Day 13)

- Status: accepted
- Date: 2026-07-20
- Deciders: Yi Xin (decision), Claude implementer (drafting — **AI-drafted record
  of a human ruling**; see docs/specs/day13.md Decisions 5–6, docs/discussions/day13.md)
- Related: ADR-0001 (Day 4b evidence-gate pattern this reuses), docs/specs/day13.md,
  docs/notes/day13-numba-decision.md, docs/tutorials/16-performance-engineering.md

## Context

Day 13 is a performance-and-inference-strategy experiment day whose deliverable is
**verifiable engineering judgment, not flashy optimization**. Two performance layers
— a self-written Rust/PyO3 extension and a switch to Python free-threading — are on
the JD keyword map but must be handled as **gate/narrative only**, never pulled into
the implementation mainline (Decisions 5–6). This mirrors the Day 4b pattern
(ADR-0001): a door opens only on profiler evidence, and "not worth it, here's the
留痕" is a mark of maturity, not a gap.

The profiler evidence is now in hand: `tools/day13_profile.py` /
[eval/results/day13-hotspots.json](../../eval/results/day13-hotspots.json) show the
CPU is spent in lxml parsing, schema validation, and Pydantic model building —
already-compiled C/Rust extensions with thin Python glue. There is no pure-numeric
Python hotspot for numba (see the numba decision note), and by the same evidence no
Python-side bottleneck for a Rust extension either.

## Decision (Rust — Decision 5)

**Day 13 writes no Rust, builds no crate, changes no build system.** Rust is recorded
as an open-door **gate**: a self-written PyO3 extension would be considered **only
when all four hold**:

1. the profiler shows a **pure-CPU hotspot at a significant share** of total time;
2. Python **multiprocessing / algorithmic fixes have already been tried** (Day 13's
   mp experiment is exactly this prerequisite — and it showed the toy corpus is not
   even CPU-bound enough to benefit from multiprocessing);
3. the hotspot's **input/output boundary is stable** (a pure function: data in,
   data out);
4. **Rust FFI / packaging cost < expected benefit** (PyO3 + maturin + a `cp*` wheel
   matrix is real maintenance).

**The gate does not open on the toy corpus.** None of (1)–(4) is met; end-to-end time
is dominated by external model inference and already-native parsing. The honest
"informed-consumer" stance stands: the latency-critical paths already **consume**
Rust — Tantivy (BM25) and the vector store — which is a legitimate way to get Rust
performance without writing an extension.

## Decision (free-threading — Decision 6)

**Free-threading is narrative / future direction only — not a Day-13 acceptance
item.** No free-threaded Python is installed; no benchmark is run; nothing is written
as a benefit already gained.

Narrative (interview-facing, from tutorial 16 §0): Python 3.13 shipped an
experimental free-threaded build (PEP 703) and 3.14 moved it to officially supported
(PEP 779), with sub-interpreters as a second axis (PEP 734). But these are **separate
builds** (`cp313t`/`cp314t` wheels) and the ecosystem is still catching up — this
project centers on **Python 3.12, multiprocessing, and external model calls**, and
free-threading's compatibility with **lxml / Pydantic / the ML libraries** still
needs future measurement. The load-bearing judgment: once the GIL is removed, the
implicit atomicity of built-in dict/list operations is gone and the old race/lock
risks return — so the **share-nothing architecture becomes *more* valuable, not
less**. Tracking, not sprinting ahead, is the call.

## Consequences

- The performance day ships four honest measurements (mp: no speedup at toy scale;
  numba: no target justified; ToT: k/n reported; asyncio: overlaps I/O waits) plus
  two documented non-actions (Rust, free-threading) — the "judgment over keywords"
  deliverable Yi Xin framed.
- The gate is reusable: if the corpus ever grows a genuine Python-side CPU
  bottleneck, re-run the profiler and re-read these four conditions.
