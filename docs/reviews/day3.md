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

## Part 2: Adjudication — [HUMAN, Yi Xin — not AI]

> Per CLAUDE.md and the daily cycle: the implementer (AI) drafts Part 1 only;
> each finding's accept/reject + one-line rationale is written by Yi Xin, and
> any red-team number is re-run by Yi Xin before merge. Left blank for you.

| # | accept / reject | rationale |
| --- | --- | --- |
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 6 | | |
| 7 | | |
| 8 | | |
| 9 | | |
| 10 | | |
| 11 | | |
| 12 | | |
