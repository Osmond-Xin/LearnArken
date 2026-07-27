# ADR-0004: A measurement is bound to the corpus revision that produced it

- Status: accepted
- Date: 2026-07-27
- Deciders: Yi Xin (decision), Claude implementer (drafting — **AI-drafted record
  of a human ruling**; ruling given in-session 2026-07-27)
- Related: [F-21](../reviews/arken-alignment-2026-07-26.md), INV-5, INV-7,
  [eval/results/day4-ablation.json](../../eval/results/day4-ablation.json),
  [docs/BENCHMARKS.md](../BENCHMARKS.md)

## Context

Re-verifying the corpus after a Vespa schema redeploy on 2026-07-26 surfaced
that `learnarken eval ablation` — the documented reproduction command for the
headline retrieval table — disagrees with the frozen
`eval/results/day4-ablation.json` in **12 of 32 metric cells, across all four
modes**, `bm25` included.

The cause is not code. `bm25` is fully offline; with the day's retrieval changes
stashed back to `HEAD` it returns the identical drifted numbers. The cause is
the **source material**: commit `dd210e3` (Day 12, multimodal) added figure
assets to `samples/package-a` and `samples/package-c` and edited one of
package-c's data modules. Each package gained a figure chunk. The Day 4 ablation
was measured before any of that existed and has never been re-measured
(`git log -- eval/results/day4-ablation.json` shows exactly one commit).

The existing guard — `tools/gen_benchmark_tables.py --check`, built after the
2026-07-25 review — verifies that the **published tables match the frozen
JSON**. Nothing verified that the **frozen JSON still matches the corpus and
code that produce it**. The drift sat undetected from Day 12 to Day 26.

## Decision

**The published Day 4 numbers are not re-measured and not restated.** They
remain exactly as published.

What changes is how a measurement is understood in this project:

> **A benchmark number is a statement about a specific corpus at a specific
> revision, not a standing property of the system. When the source material
> changes, every measurement taken on the previous material is void — not
> "approximately still true", and not "in need of a refresh". Void.**

Three consequences:

1. **Published numbers are historical records, scoped to their corpus.** The
   Day 4 table describes the pre-Day-12 corpus. It was true when measured and
   is still an honest record of that measurement. It is not a claim about what
   the repo does today.
2. **Re-measuring is a decision, not maintenance.** Overwriting a frozen
   artifact silently redefines what a published number means. It requires a
   ruling, and the superseded artifact keeps its scope label rather than
   disappearing.
3. **Changing sample data is a benchmark-affecting change.** Day 12 treated
   `samples/package-a` as demo material. It is also evaluation material. Any
   future edit to a package that an eval reads must be recognised as
   invalidating that eval, at the time of the edit.

## Why not the alternatives

- **Re-measure and republish now.** Rejected. It buries the more valuable
  artifact: the *lesson* that source-material changes void prior measurements.
  A repo whose thesis is honest evidence learns more from carrying a visible
  scoped record than from a quietly refreshed table.
- **Delete the Day 4 numbers.** Rejected. They were honestly measured. Deleting
  measurements because they aged is its own kind of dishonesty.
- **Build the drift guard now** (a check that a committed artifact's declared
  inputs still match what the repo would produce). Not rejected — deferred. The
  ruling was to take the lesson, not to automate around it. The guard remains
  available as the structural fix, together with pinning an evaluation corpus
  separately from the demo corpus so feature work cannot move a benchmark again.

## Consequences

- Anyone reading the Day 4 table must be able to see which corpus it describes;
  the tables carry that scope explicitly.
- This ADR is the trace. The next person to change a sample package — including
  a future me — is expected to ask what evaluations read it.
