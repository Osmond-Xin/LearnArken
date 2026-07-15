# Day 3 Red-Team Review & Adjudication

## Part 1: Red-Team Findings (non-implementing model, read-only review)

- Review target: branch `feat/day3` vs `main` (Day 3: chunking + BM25 +
  retrieval eval)
- Reviewing model: **Codex** (`codex exec --sandbox read-only`, cross-host via
  adversarial-review 0.5.0), 2026-07-14
- Inputs: Day 3 source (`chunking/`, `retrieval/`, `cli.py`) diff + focus brief
- Cross-validation: the implementer (Claude) ran an independent host-side pass
  and reproduced the two sharpest claims with experiments **before** filing.
  Tags record who caught what; `[host-only]` findings are the implementer's
  supplements, honestly labeled.
- ✅ = reproduced by a concrete experiment before filing (command noted).
- Verdict from the external reviewer: **DO_NOT_MERGE**.

| # | Grade | Tag | Finding | Location | Suggestion |
| --- | --- | --- | --- | --- | --- |
| 1 | P1 | cross-validated ✅ | BM25 hit cutoff `score <= 0` drops real matches: a term present in all/most chunks gets **negative IDF** in BM25Okapi, so its match scores ≤ 0 and is discarded as "no overlap". Verified: on a 2-chunk corpus where "remove" is in both, `search("remove")` → `[]` | `retrieval/bm25.py` `BM25Index.search` (score cutoff) | gate hits on actual token overlap (query∩chunk tokens), not BM25 score sign |
| 2 | P1 | external-only | `chunk_package` is **fail-open**: an unparseable/oversized DM is skipped with only a log, and the package still returns success. A malformed safety DM silently vanishes from the index; `search`/`eval` report `0`/clean as if the content never existed — undercuts the fail-closed ingestion promise (INV-4) | `chunking/__init__.py` DM loop `except` | collect parse failures; fail the package by default, `--skip-bad` opt-in only |
| 3 | P1 | external-only | Eval is **blind to false positives**: `evaluate_strategy` skips queries with no resolvable relevant, which includes the 5 no-answer traps — a retriever that hallucinates hits for "engine oil filter" is never penalized. Unresolved anchors are also silently skipped, so eval can *improve* when the golden set breaks | `retrieval/evaluate.py` `evaluate_strategy`; golden no-answer rows | fail on unresolved anchors; add no-answer metric (zero-hit accuracy / FP@k). NB: adversarial no-answer scoring is partly Day 8 scope |
| 4 | P1 | cross-validated | reqSafety **preliminary warnings are separate chunks**, not folded into the procedural steps they guard, yet `structure.py`'s docstring claims "keeps a step and its preceding warning together". A step retrieved alone omits its preliminary safety warning. NB: standalone warning chunks are per SPEC ("one per warning block outside steps"); the real gap is the docstring overclaim + a Day 5 answer-time safety-expansion need | `chunking/structure.py` docstring + reqSafety branch | fix the docstring; decide whether retrieval/answer-time must always pull the DM's safety chunk |
| 5 | P2 | cross-validated ✅ | `applies_to` lexical range fallback wrongly matches: for non-numeric ranges it does string comparison, so `"A2" ∈ "A10~A20"` → `True`. Latent — samples use numeric ranges only | `chunking/base.py` `_values_match` | reject/typed-parse malformed ranges; do not fall back to lexical `<=` on ranges |
| 6 | P2 | external-only | Substring-containment relevance creates **false matches**: a short/common anchor text ("Install") can mark unrelated same-DMC chunks relevant; duplicate matching chunks can inflate Recall/nDCG. Low risk today (anchors are long step texts) | `retrieval/evaluate.py` `_relevant_chunk_ids` | exact `(dmc, source_path)` match for structure chunks; span/token-overlap threshold for recursive |
| 7 | P2 | external-only | `chunk_id` omits package/file identity and truncates SHA1 to **48 bits**: two packages sharing a DMC+XPath collide (package-a and package-b share DMCs) → eval could credit the wrong package's chunk. Latent — eval currently mixes only package-a + package-c | `chunking/base.py` `make_chunk_id` | include a stable package/file digest in the key; avoid the truncated id as sole metric identity |
| 8 | P2 | host-only | `applies_to` **fails open** when the query omits a constrained property (a `variant=B`-only chunk is kept when the caller passes only `serialNumber=…`). Documented as intended ("absence of exclusion = applicable"), but for safety-critical 排除场合 a tri-state (applicable / excluded / unknown) that fails closed on unknown may be wanted | `chunking/base.py` `applies_to` | adjudication call: keep fail-open, or fail-closed/tri-state on unknown constrained properties |
| 9 | P3 | external-only | CLI accepts non-positive `--top-k` / `--k`: `--top-k -1` slices "all but the last", `--k -1` yields nonsensical metric labels | `cli.py` search / eval argparse | enforce positive integers |
| 10 | P3 | external-only | Golden `source_path` is executed as an **arbitrary XPath** and assumed to return an element; a malformed path could raise or run costly XPath over every file. Low risk — golden is trusted/versioned | `retrieval/evaluate.py` `resolve_anchor_texts` | whitelist simple absolute paths; check `isinstance(found[0], _Element)` |
| 11 | P3 | host-only | `random.seed()` in the eval command mutates **global** RNG state for a pipeline that is already deterministic — a near-dead "forward guard" | `cli.py` `_cmd_eval_retrieval` | drop it, or use a local `random.Random(seed)` if/when sampling is added |
| 12 | P3 | external-only | Tokenizer doesn't normalize `P/N 1234-567` (space-separated prefix) or dotted/underscored part forms, so equivalent part-number queries can miss | `retrieval/bm25.py` `tokenize` | add DMC/ICN/P-N normalization + tests for slash/dot/underscore/space |

**External reviewer's blocking set**: #1 (BM25 cutoff), #2 (fail-open index),
#3 (eval false-positive blindness), #4 (safety-warning chunking). Verdict
**DO_NOT_MERGE** until these are resolved or explicitly scoped-out.

## Part 1b: Convergence loop (Producer → Challenger → Reviser)

On 2026-07-15 Yi Xin directed: *fix per the red-team recommendations, then
re-run the red team until no P0 remains and the verdict is SHIP.* The
implementer (Claude) applied fixes; Codex (read-only, cross-host) re-reviewed
each revision. Rounds:

| Round | Verdict | New blockers found (P1) | Resolution |
| --- | --- | --- | --- |
| R1 | DO_NOT_MERGE | BM25 score-sign cutoff; fail-open index; eval FP-blind; safety-warning chunking | all fixed |
| R2 | DO_NOT_MERGE | default `eval` broken; broad-XPath binds to first; unmapped anchor only warned | all fixed |
| R3 | DO_NOT_MERGE | duplicate package → recall > 1.0; faultDescription dropped | all fixed |
| R4 | REVIEW_NEEDED | *(none — P2/P3 only)* | `_windows` progress, size-cap on chunk path, up-front pkg validation, recursive token-overlap |
| R5 | SHIP | *(none)* | partial multi-anchor denominator, scalar-XPath guard, stricter one-token rule |
| R6 | **SHIP** | *(none — no P0/P1/P2)* | regression tests added |

Final external verdict **SHIP** (Codex, R6): no P0/P1/P2. Each round's fixes
ship with tests (108 passing); metric integrity fixes are covered by explicit
regression tests (recall never > 1.0; partial multi-anchor; no-answer;
unmapped-anchor zero-recall).

## Part 2: Adjudication — [Yi Xin's directed ruling, AI-transcribed]

> **Authorship note**: Yi Xin did not hand-write per-finding rationales this
> time; instead they issued a single directed ruling in the 2026-07-15 session
> — *"apply all red-team recommendations and loop until SHIP"* — transcribed
> here by the AI per that instruction. Two boundaries preserved: (a) the
> benchmark numbers in the README are still to be **re-run by Yi Xin** before
> merge (data red line — not delegated); (b) finding #8 (applies_to fail-open
> on an unconstrained property) was **kept as-is by design**, not "fixed",
> because flipping it would contradict Day 3 decision 2 ("absence of exclusion
> = applicable").

| # | ruling | note |
| --- | --- | --- |
| 1 | accept — fixed | BM25 hits gated on token overlap, not score sign |
| 2 | accept — fixed | `chunk_package` fails closed; `--skip-bad` opt-in |
| 3 | accept — fixed | eval fails closed on unresolved anchors; `zero_hit_rate` metric added |
| 4 | accept — fixed | docstring corrected; precondition/closeout/faultDescription now chunked |
| 5 | accept — fixed | numeric-only range parsing (no lexical fallback) |
| 6 | accept — fixed | canonical-XPath (structure) / token-overlap (recursive) relevance |
| 7 | accept — fixed | chunk_id carries file md5, widened to 64 bits |
| 8 | **keep by design** | fail-open on unconstrained property = Day 3 decision 2; not a defect |
| 9 | accept — fixed | CLI rejects non-positive `-k`/`--k`; `BM25Index.search` guards `k<=0` |
| 10 | accept — fixed | golden XPath guarded (XPathError + list/element checks) |
| 11 | accept — fixed | global `random.seed` removed; `--seed` documented as reserved |
| 12 | accept — fixed | tokenizer keeps `_`/`-`/`/` identifiers whole |

> Pending Yi Xin before merge: re-run `learnarken eval retrieval` and confirm
> the README benchmark numbers (structure 0.93/0.93/0.80/0.83, recursive
> 0.85/0.89/0.79/0.80, zero-hit 0.40).
