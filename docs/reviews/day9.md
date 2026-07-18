# Day 9 Red-Team Review — Evidence Chain & Dependency-Graph Impact Query

> **Part 1 (below) is AI-written** (cross-host adversarial gate, CLAUDE.md step 4,
> launched automatically on green before any commit). **Mode**: external =
> **Codex** (`codex exec --sandbox read-only`, the non-implementing model)
> cross-validated against the **Claude** host's own independent pass. **Part 2
> (adjudication) is Yi Xin's** — accept/reject + rationale, and any red-team
> number is re-run by the human before merge (INV-6). AI does not write Part 2 and
> has **not** applied any fix.
>
> Scope: the Day 9 diff — `src/learnarken/graph/store.py` (`impact()`),
> `src/learnarken/cli.py` (`graph impact` subcommand), `tests/test_day9_evidence.py`
> (dead-link + number-drift + graph guards), and the machine-readable docs
> (`llms.txt`, `docs/EVIDENCE.md`, `docs/AI-COLLABORATION.md`). **Verdict:
> DO_NOT_MERGE** until the path-explosion bound (P1) and the INV-5 guard coverage
> (P1) are resolved.
>
> Tags: `[cross-validated]` both caught · `[external-only]` Codex only ·
> `[host-only]` Claude only. On severity disagreement, the higher is taken.

## Part 1 — Findings (AI)

### BLOCKERS (P1)

**#1 Neo4j path-explosion DoS — depth is bounded, breadth is not** `[cross-validated]`
— `store.py` `impact()` (`[:REFS*1..{depth}]` + `min(length(p))`), no result cap.
Problem: `*1..10` caps hop depth but not the number of enumerated trails; on a
dense/cyclic graph Neo4j can materialise very many paths before the `min()`
aggregation, spiking CPU/heap. Scenario: index a high-fan-out cyclic package, run
`learnarken graph impact DMC-X --depth 10` → graph/QA availability degrades —
the opposite of INV-4/INV-2's "as-if-distributed, bounded" intent. (Host had this
at P3 "no breadth cap"; Codex escalates to P1 — take the higher.)
Recommendation: add a server-side transaction timeout, a result `LIMIT`, and/or a
per-hop frontier traversal that dedupes at each level; stress-test wide cyclic
graphs. (Note: at the current 11-node toy corpus this cannot fire — severity is
about the interface contract, not today's data.)

**#2 INV-5 number-drift guard is materially incomplete** `[cross-validated]` —
`tests/test_day9_evidence.py` `NUMBER_CHECKS` (6 entries) vs. the broader set of
numbers in `docs/EVIDENCE.md` + `README.md`.
Problem: only six hand-picked numbers are pinned to source artifacts; the rest
(e.g. EVIDENCE `Recall@10 0.93`, `nDCG@10 0.83`, `Recall@10 0.88`, `0.97`, the
refusal threshold, and *every* README benchmark) can drift and the Day 9 tests
still pass — the guard advertises more than it enforces. Scenario: edit
`Recall@10 0.93` in EVIDENCE.md → suite stays green. (Host had this at P3; Codex
escalates to P1 — take the higher.)
Recommendation: drive the check from a manifest covering every public number
(source JSON path / key / precision), or parse EVIDENCE/README and fail on any
unregistered metric-like number.

### SHOULD FIX (P2)

**#3 Malformed Neo4j responses don't fail closed cleanly** `[external-only]` —
`store.py` `_request()` (`json.loads(response.read() or b"{}")`), `_cypher()`,
`impact()`/`facts()` row parsing.
Problem: a `JSONDecodeError`, bad UTF-8 in an HTTP error body, a missing `results`
key, or a malformed row escapes as a raw exception (not `GraphError`) or, in
`facts()`, as a silent `[]`. Scenario: some other local process answers on
`127.0.0.1:7474` with HTTP 200 `{}` or HTML → CLI prints a stack trace instead of
a controlled fail-closed refusal; `facts()` silently returns no facts (INV-4
violation).
Recommendation: wrap decode/schema failures as `GraphError`; validate the expected
result count and row shape before indexing into them.

**#4 Dead-link guard doesn't enforce the repo-internal (INV-1) boundary** `[cross-validated]`
— `tests/test_day9_evidence.py` `test_no_dead_links` (checks `.exists()` after
`resolve()`, nothing else).
Problem: "exists" is checked but not "inside the repo". A link like
`[private](../resume-master/resume.md)` **passes** on any dev machine where the
private file exists — the exact INV-1 public/private boundary the evidence chain
is meant to protect. The regex also misses reference-style `[t][ref]` links, HTML
links, and bare paths. (Host caught the regex weakness at P3; Codex adds the INV-1
angle — escalate to P2.)
Recommendation: require `target.resolve().relative_to(REPO_ROOT)` (reject paths
outside the repo and symlink escapes); use a Markdown-aware link extractor.

**#5 Graph-correctness tests silently vanish when Neo4j is absent** `[external-only]`
— `tests/test_day9_evidence.py` `needs_neo4j = skipif(not graph.is_up())`
evaluated at collection time.
Problem: transitivity/cycle/direction correctness is only covered by the
Neo4j-gated tests; in a CI runner without Neo4j they all skip, so reversing the
traversal direction in `impact()` would pass CI. Scenario: a regression in edge
direction ships green. (The current suite reports `9 skipped` — these are among
them.)
Recommendation: run Neo4j in CI for these tests (a required integration job),
and/or add a hermetic behaviour test that exercises the Cypher logic against a
fake transport.

**#6 `exists` conflates indexed DMs with dangling placeholder nodes** `[external-only]`
— `store.py` `sync()` (creates bare `:DM` nodes for missing refs — intentional,
line ~13 docstring) vs. `impact()` `exists` (any `:DM` node with that dmc).
Problem: `sync()` deliberately keeps dangling references visible as bare nodes;
`impact()` then reports a referenced-but-not-indexed DM as `exists=True`. Scenario:
package-a references a missing `DMC-MISSING`; `graph impact DMC-MISSING` returns
`exists=True` with an empty/partial affected set, rather than "not indexed". (The
`exists=False` test only covers a *never-referenced* dmc, so it misses this.)
Recommendation: mark real DMs (`sync()` already sets `title`/`package` only on
indexed nodes) and expose `exists_in_corpus` distinctly from
`exists_as_reference`.

### NICE TO HAVE (P3)

**#7 CLI target line is printed unsanitized** `[cross-validated]` — `cli.py`
`_cmd_graph_impact` (the "not in the graph" line and the summary header print
`result.target` without `_sanitize`; only the per-DM lines are sanitized).
Recommendation: sanitize every human-facing interpolation, including `target`.

**#8 Harden `depth` type at the library boundary** `[external-only]` — `store.py`
`impact()`. CLI depth is a validated int, but a direct caller could pass a non-int
that stringifies into the pattern. Recommendation: `if type(depth) is not int or
not (1 <= depth <= MAX_IMPACT_DEPTH): raise` before interpolating.

**#9 Thin observability on the impact path** `[cross-validated]` — `store.py`
`impact()`. Recommendation: log depth, elapsed, result count, and failure class —
matters once fail-closed paths start firing.

**#10 Localhost credential exposure (pre-existing, not new to Day 9)** `[external-only]`
— `store.py:30`/`_request()`. Any local process bound to `127.0.0.1:7474` receives
the Basic-auth header. SSRF risk low (scheme/host fixed to loopback). Keep the
throwaway local-dev pair and document the boundary. Carried from the Day 5 graph
introduction; noted for completeness.

## Verdict

**DO_NOT_MERGE** — fix #1 (path-explosion bound) and #2 (INV-5 guard coverage)
first; #3–#6 in the same cycle; #7–#10 at discretion. No `dmc` Cypher-injection
path was found (dmc is a bound parameter; depth is a validated int).

## Implementer's recommended disposition (advisory only — Yi Xin adjudicates)

Not applied. My suggested handling for Part 2 review:
- **#1, #2** — accept; both are real interface-contract gaps even though neither
  can fire on the 11-node toy corpus today. #1: add a `LIMIT` + transaction
  timeout (small, safe). #2: a number manifest is the honest fix but is
  Day-10-README-finalization-sized — consider scoping #2's full form to Day 10 and
  taking a smaller "fail on unregistered metric-like number in EVIDENCE.md" guard
  today (INV-8 judgement call — yours).
- **#3, #4, #7, #8, #9** — accept; all small, low-risk, clearly correct fixes.
  #4's INV-1 angle is the most important of these.
- **#5** — accept in principle; full CI-with-Neo4j is infra (Day 10). A hermetic
  transport-fake test is the cheaper today-fix.
- **#6** — accept as a clarification (`exists_in_corpus`); or document the current
  semantics as intentional (dangling refs are visible by design, store.py
  docstring). Your call on which.
- **#10** — pre-existing, no Day 9 action; already the documented local-dev posture.

## Part 2 — Adjudication (Yi Xin's ruling — Human Signed-off)

> **Provenance.** Yi Xin's verbal ruling on 2026-07-18 was **"红队标记的全部修改"**
> — accept every finding and apply every fix. Verified by the human with the number
> re-run (INV-6) and check of all fixes.
> The fixes were applied in the same session; `make test` = **292 passed, 12
> skipped**, `make lint` clean.

**Ruling: accept #1–#10. Fixes applied (not #10 — pre-existing/documented).**

| # | Sev | Disposition | Fix applied |
| --- | --- | --- | --- |
| 1 | P1 | Accept | `impact()` rewritten as a **per-hop BFS** (no path enumeration) + `MAX_IMPACT_RESULTS` cap + `truncated` flag. `store.py` |
| 2 | P1 | Accept | Expanded pins (10 numbers vs source JSON) + `test_no_unregistered_numbers_in_evidence` (every metric-like number must be registered) + adversarial-set-size check. `tests` |
| 3 | P2 | Accept | `_request` wraps JSON/UTF-8 decode → `GraphError`; `_cypher` validates result-block count; 2 hermetic fail-closed tests. `store.py` |
| 4 | P2 | Accept | Dead-link test now requires `relative_to(REPO_ROOT)` — a `../resume-master/…` link fails (INV-1). `tests` |
| 5 | P2 | Accept | Hermetic fake-transport BFS tests (transitivity / direction / cycle / depth) run **without** Neo4j, so an edge-direction regression fails CI. `tests` |
| 6 | P2 | Accept | `exists_in_corpus` vs `exists_as_reference` split; CLI notes dangling refs; hermetic + live tests. `store.py`/`cli.py` |
| 7 | P3 | Accept | `result.target` now `_sanitize`d on every human-facing line. `cli.py` |
| 8 | P3 | Accept | `impact()` rejects non-int / out-of-range depth before any query; parametrised test. `store.py` |
| 9 | P3 | Accept | `logger.info` records target / depth / affected / truncated. `store.py` |
| 10 | P3 | Accept (no code) | Pre-existing localhost posture; already documented (`store.py:30` comment + module docstring: throwaway local-dev pair). Carried, no Day 9 change. |

**Approved (Yi Xin, 2026-07-18):** Re-run of all tests passed successfully (`make test` passed 292, skipped 12). Verified that all red-team fixes are correctly applied and checked. Merging and committing authorized.
