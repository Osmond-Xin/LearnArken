# Day 13 — numba decision: no numba target justified

> **AI-generated** (Claude implementer, 2026-07-20), transcribing the honest
> technical reading of the profiler evidence for Yi Xin's review. Authority is the
> SPEC decision layer ([docs/specs/day13.md](../specs/day13.md) Decision 2) and the
> profiler artifact ([eval/results/day13-hotspots.json](../../eval/results/day13-hotspots.json)).

## Verdict

**No numba target is justified.** This is a **passing** result (Decision 2d), not a
failure — and it means **no numba dependency is added** to the project.

## Evidence (measure first, Decision 2a)

`tools/day13_profile.py` ran cProfile over the CPU-bound offline paths
(`analyze_package` + `chunk_package` over package-a/b/c, 20 iterations). Top
functions by **self-time**:

| self-time | function | where | numeric loop? |
| --- | --- | --- | --- |
| ~0.042s | `pyexpat.xmlparser.Parse` | C extension | no — XML parsing (C ext) |
| ~0.020s | `load_data_module` | `loader.py` | no — model building |
| ~0.017s | `build_schema` | `engine.py` | no — **lxml XMLSchema construction** |
| ~0.011s | `parse_file` | `loader.py` | no — parse orchestration + hashing |
| ~0.011s | `_start` / `_fixname` / `_end` | `ElementTree.py` | no — XML event handlers |
| ~0.006s | `validate_python` | `pydantic_core` | no — Pydantic validation (Rust ext) |
| ~0.004s | `_process_file` | `engine.py` | no — L0/L1/L2 orchestration |

The automated screen in the profiler flagged `build_schema` and `_process_file` as
"not obviously excluded" only because they live in `learnarken` and dodge the
XML/Pydantic/IO marker list. On inspection **neither is a pure-numeric loop**:
`build_schema` constructs an lxml `XMLSchema` (XML work), and `_process_file`
orchestrates parse → schema-validate → model-build → BREX (glue over C/Rust
extensions). The screen is necessary-not-sufficient by design (Decision 2b: a human
confirms the loop is numeric and type-stable); this note is that confirmation.

## Why this is the expected outcome, not a shortcoming

Decision 2c excludes exactly what dominates here: **XML parsing, Pydantic models,
lxml XPath, and model inference are not numba targets.** numba compiles numeric
loops over numpy arrays; this project's CPU time is spent in already-compiled C/Rust
extensions (pyexpat, lxml, pydantic-core) with thin Python glue. There is **no
loop-dense numeric Python hotspot** for numba to accelerate. Forcing a numba
decorator onto XML/orchestration code would either silently fall back to object mode
(no speedup, Decision 2 / scan A4) or simply not apply.

This mirrors the Day 4b "证据开门" discipline and the tutorial-16 warning that the
honest conclusion is often "not worth it" — recording that is a mark of maturity,
not a gap. The same profiler that produced this verdict is the evidence gate that
would open a **Rust/PyO3** door too, and it does not open here either (see
[ADR-0003](../adr/0003-day13-rust-gate.md)).

## If the corpus ever grows a numeric hotspot

The path is unchanged and evidence-gated: re-run `tools/day13_profile.py`; if a
pure-numeric, loop-dense, type-stable function appears near the top (e.g. a custom
scoring/fusion loop that is *not* delegated to numpy/Tantivy), then — and only then
— do the three-column `pure-Python / numpy / numba` comparison with
`@njit(nopython=True, cache=True)`, warm-up excluded from timing (scan A4), and
report the gain even if small.
