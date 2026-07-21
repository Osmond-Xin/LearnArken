# Day 12 Review — Multimodal Ingest & QA (`v1.2.0` candidate)

> **Scope note.** This is an **early/partial** red-team pass, run at Yi Xin's
> instruction on the **completed slice only** (VLM client, figures + assets,
> ingest/describe-then-index, loader/model/XSD hotspot extension, index_package
> wiring). **NOT yet implemented at review time** (excluded from scope): the
> query-time second-look consensus wiring into the answer engine, G15 refusal
> wiring, the golden set, and eval. A **second** red-team pass will run on the
> full diff before any merge is proposed.

## Part 1 — Red-team findings (AI-drafted, cross-host)

> **Provenance.** Cross-host review per CLAUDE.md: external reviewer **Codex**
> (`codex exec --sandbox read-only`, the non-implementing model) + independent
> **host-side (Claude)** analysis, cross-validated. Tags: `[cross-validated]`
> both caught it; `[external-only]` Codex only; `[host-only]` Claude only.
> Codex verdict: **REVIEW_NEEDED**. Findings-only; no code changed by the review.

### P1 — Blockers

1. **[cross-validated] Committed describe records are trusted at index time —
   no re-verification.** `index_package`/`figure_chunks` load `.describe.json`
   and gate only on `rec.verified`; the PNG SHA-256, the declared hotspot set,
   the part numbers, and the `verified` flag are **never recomputed** against the
   current PNG/XML at index time
   ([ingest.py](../../src/learnarken/multimodal/ingest.py) `load_records` /
   `figure_chunks`; chunk id uses the stored SHA prefix only). **Exploit:** hand-
   edit a committed record to `verified=true` with a fabricated summary/warnings,
   or swap the PNG bytes without re-describing — the stale/forged record is
   indexed as evidence and the SHA "binding" catches nothing. The binding is
   computed and stored but not *enforced*.

2. **[external-only] Figure chunks are indexed into Vespa but absent from the
   query-side / BM25 / verification corpus.** Index adds figure chunks
   ([retrieval/__init__.py](../../src/learnarken/retrieval/__init__.py)
   `_figure_chunks_for_package`), but the answer/query path rebuilds its local
   corpus via `chunk_package` **only** (text chunks), and corpus-identity
   verification compares manifest ids to that text-only local set. **Effect:**
   after a Day 12 index, a non-BM25 query can **fail closed** ("manifest chunk
   ids differ"), and BM25 never retrieves figures — so the whole feature is not
   actually queryable. Fix requires a **single shared corpus builder** used by
   index, search, query, verification, and ablation. *(This is a functional gap,
   not just a hardening item — figures are not reachable at query time.)*

3. **[cross-validated] A VLM refusal / fabrication can pass as a real
   description.** `desc.refused` is not terminal: `describe_figure` returns any
   schema-valid `FigureDescription`, and ingest ignores `refused`. **Exploit:**
   the unstable proxy returns `{"refused":true,"hotspots":[{"id":"01"}],
   "reads_text":["LA-29-4711-1"],…}` — ingest can mark it verified. A refusal
   with non-empty evidence must be rejected (INV-4).

4. **[cross-validated] Part-number corroboration is spoofable and brittle.**
   Ingest unions `reads_text` with the VLM's **own** `parts` list and uses bare
   substring match ([ingest.py](../../src/learnarken/multimodal/ingest.py)
   `describe_dm_figures`). **Exploit:** the model self-corroborates via its own
   parts list even with empty OCR; and `A-1` substring-matches `A-10`. Anchor
   must be **independent OCR text only** (`reads_text`, ideally the SVG `<text>`
   white-list), matched at **token boundaries**. *(Partially pre-addressed in
   `second_look._corroborated` (token-boundary), but that path still unions the
   VLM parts list, and `ingest` still uses substring — both need the fix.)*

### P2 — Should fix

5. **[external-only] Hotspot labels are keyed DM-wide, not figure-scoped.**
   `format_figure_text` builds `decls_by_id` keyed by `hotspot_id` only; two
   figures in one DM both using hotspot `01` cross-contaminate labels/parts. Key
   by `(icn_ident, hotspot_id)`.

6. **[external-only] ICN id → path is not hardened (traversal + unbounded PNG).**
   `infoEntityIdent` flows unvalidated into `package_dir/icn/{icn}.png`
   ([ingest.py](../../src/learnarken/multimodal/ingest.py)); a crafted id like
   `../../secret` reads outside the icn dir, and an arbitrarily large PNG
   exhausts memory at base64 time. Restrict ids by regex, resolve-and-confine
   under `icn/`, cap bytes/dimensions.

7. **[cross-validated] Malformed HTTP-200 bodies escape the VLM error contract.**
   `_one_call` does `json.loads(response.read())` unguarded
   ([vlm.py](../../src/learnarken/multimodal/vlm.py)); an HTML/array 200 raises
   `JSONDecodeError`/`AttributeError`, not `VLMError`/flaky. Wrap consistently.

8. **[cross-validated] XSD hotspot extension lacks id pattern / uniqueness.**
   `hotspotId` is a plain string with no simpleType pattern and no per-figure
   uniqueness ([learnarken.xsd](../../src/learnarken/schemas/learnarken.xsd));
   blank/path-like/duplicate ids validate. *(Verified: this does **not** mask
   package-b's known violations — its count is unchanged at 7 errors, and
   dangling ICN refs are still caught by XREF-002.)* Add a pattern + uniqueness.

### P3 — Nice to have

9. **[external-only] Strict Pydantic** (`extra="forbid"`, stricter types) on the
   VLM and record models so schema drift is visible.
10. **[external-only] Retry jitter / global budget** — per-call retries are
    bounded, but future bulk describe runs can synchronize sleeps.

### Host-only note (already fixed in the same session, disclosed)

- **[host-only] `vlm._parse` phrase-check ordering (fixed).** The original
  `_parse` ran a "no image" prose check over the whole payload **before** JSON
  parsing, so a legitimate description whose summary contained the words "no
  image" was discarded as a flaky miss. Fixed to **parse JSON first** (non-JSON
  prose — including the real "no image" reply — is the flaky case); regression
  test `test_vlm_valid_json_mentioning_no_image_is_kept`. Disclosed here for the
  trail (fix applied before formal adjudication, per Day 9/11 precedent).

### Fixes applied (disclosure — pending Yi Xin's Part 2 adjudication)

At Yi Xin's instruction ("红队的全修正"), **all findings above were fixed in the
same session**, before formal adjudication (Day 9/11 precedent; disclosed here
for the trail — Part 2 accept/reject remains Yi Xin's). Each fix is
regression-tested in `tests/test_day12_multimodal.py` (23 tests) and the
end-to-end index+query path was re-validated live (figure chunk retrieved rank 1,
no foreign-chunk error).

| # | Fix | Where |
| --- | --- | --- |
| P1.1 | Index-time re-verify: SHA-256(current PNG) + declared set must still match the record, else the figure is skipped (fail closed) | `ingest.figure_chunks` |
| P1.2 | Single shared `corpus_chunks` builder (text + figure) used by index, search, query, ablation, golden-eval — index and query can no longer disagree | `retrieval.corpus_chunks`; callers in `search_package`, `index_package`, `answer/engine`, `run_ablation`, golden eval |
| P1.3 | `refused=true` (even with evidence) is never a positive read → degraded | `ingest.describe_dm_figures`; `second_look` skips refused |
| P1.4 | Corroboration uses OCR `reads_text` **only** (no self-corroboration) at **token boundaries** (not substring) | `ingest._ocr_tokens`, `second_look._corroborated` |
| P2.5 | Hotspot labels keyed per figure (`by_icn`), not DM-wide | `ingest.figure_chunks` / `format_figure_text` |
| P2.6 | ICN id regex + path confined to `icn/`; PNG byte cap | `ingest.png_path`, `read_png` |
| P2.7 | Malformed HTTP-200 body / non-object wrapped as `VLMError`; base_resp rate-limit → `VLMRateLimited` | `vlm._one_call` |
| P2.8 | XSD `hotspotIdType` pattern + per-figure `hotspotId` uniqueness | `learnarken.xsd` |
| P3.9 | `extra="forbid"` on `FigureRecord`/`ConsensusReading` (VLM-output model left tolerant by design — documented) | `ingest`, `second_look`, `vlm` |
| P3.10 | Retry jitter | `vlm.describe_figure` |
| H1 | `_parse` JSON-first (no-image phrase no longer drops valid reads) | `vlm._parse` |

**Design change worth adjudicating:** the indexed figure-chunk text is now
**declared-grounded only** (DM XML hotspots/parts) — the VLM `summary` and
`safety_warnings` stay in the audit record but are **not indexed** as
authoritative (resolves P1c/H3: no unverified VLM free-text in the corpus). If
you want natural-language figure summaries retrievable, we'd need to either
declare them authoritatively in the DM XML or accept indexing verified VLM text —
your call in Part 2.

## Part 1b — Final red-team (round 2, on the full diff)

> Cross-host (Codex external + Claude host), run on the complete diff after the
> round-1 fixes + the new G15/second-look/eval code. Codex verdict: **DO_NOT_MERGE**
> — the round-1 fixes held, but the *new* query-time path had 2 P1 + 5 P2 + 2 P3.
> All fixed in-session (Yi Xin "全修正"); regression-tested (31 Day 12 tests) and
> re-validated live. Accept/reject remains Yi Xin's (Part 2).

### R2 findings + fixes

| # | Finding | Fix | Where |
| --- | --- | --- | --- |
| R2-P1a | **G15 bypass by positive hallucination** — if the LLM says `is_answerable=true` and cites any verbatim figure quote, G15 never runs, so a fabricated value could pass. | **Grounding gate at citation confirmation** (Yi Xin 2026-07-20: free-text visual hallucination is a KEY thing this project must block, and it must be blocked HERE): for a figure-only-cited answer, **every content token — free-text (colour/material) AND concrete (part/measurement) — must be grounded in the cited quote or the question** (numbers/counts + scaffolding words excepted); any ungrounded token → re-look + refuse. | `engine._ungrounded_figure_tokens` |
| R2-P1b | **Chunk identity didn't bind the declared label/part text** — a `partNumberValue` edit changed corpus text but not the (PNG-sha-only) chunk id, so a stale Vespa doc could pass verification. | `FigureRecord.declared_map` (id\|label\|part) now re-verified at index time, and its digest is folded into the **chunk id** — any edit mints a new id → stale doc fails corpus verification. | `ingest.figure_chunks`, `_map_digest` |
| R2-P2 | Second-look raised (not refused) on transport/malformed `VLMError`. | `consensus_read` catches `VLMError` → `FigureRefusal` (fail closed). | `second_look.consensus_read` |
| R2-P2 | Consensus didn't require the read to equal the declared hotspot set (invented ids could "agree"). | A read whose hotspot set ≠ declared casts no vote. | `second_look.consensus_read` |
| R2-P2 | Any figure in top-k could trigger ≤5 VLM calls. | Second-look fires only when a figure is the **top** evidence. | `engine.answer_question` |
| R2-P2 | Eval/judge/threshold tools still built a text-only corpus (figure citations missing for the judge). | `corpus_chunks` in `adversarial/run.py` + `day11_refusal_gate.py` + `answer_sample_eval.py` + `measure_refusal_threshold.py`. | (those files) |
| R2-P2 | `figure_ref` guessed the first hotspot from a multi-hotspot quote. | Emit `[ICN, Hotspot NN]` only when the quote names exactly one hotspot, else `[ICN]`. | `engine._figure_ref` |
| R2-P3 | OCR token match broke on trailing punctuation (`LA-…-2.`). | Shared `_tokenize` strips surrounding punctuation (still no substring false-positive). | `ingest._tokenize` |
| R2-P3 | `day12_resolution.py` printed a renamed key. | Print `measured_minimum_scale` / `render_scale_used`. | (tool) |

### Free-text fabrication — RULED and CLOSED (Yi Xin 2026-07-20)

I initially disclosed free-text visual fabrication (e.g. a fabricated colour) as
a "Day-8 semantic-entailment boundary" to defer. **Yi Xin rejected the defer:**
blocking free-text hallucination is a KEY purpose of this project, and it must be
intercepted at citation confirmation. Done — the grounding gate above now covers
**all** content tokens, not just part/measurement: a figure-only-cited answer
whose content isn't grounded in the cited quote or the question is refused. Unit
test `test_ungrounded_figure_tokens_blocks_freetext_and_concrete` ("blue",
"steel", and a fabricated part are all flagged; a real part number, question-echo,
and counts pass). Fail-safe: legitimate answers may occasionally over-refuse on
unusual phrasing, never fabricate. *(This corrected my own attempt to scope it
out — recorded here for the trail; a red-team finding is not mine to downgrade.)*

## Part 2 — Adjudication (Yi Xin)

> **Transcribed from Yi Xin's instruction (2026-07-20 session: "红队的全修正" +
> "3: 确认").** AI does not author adjudication; this records Yi Xin's explicit
> ruling with provenance (daily-cycle rule: adjudication may be transcribed under
> instruction but must leave a trace). Yi Xin may edit.

- **All findings (4 P1 + 4 P2 + 2 P3 + host-H1): ACCEPTED and fixed.** Yi Xin
  directed a full fix of every red-team finding; the fixes in "Fixes applied"
  above are accepted, each regression-tested, with the end-to-end path
  re-validated live.
- **Design change — index text is declared-grounded only (VLM summary/warnings
  not indexed): CONFIRMED.** Yi Xin confirmed the tightening that keeps
  unverified VLM free-text out of the retrieval corpus (resolves P1c/H3).
- **Open follow-ups (tracked, not blocking this adjudication):** the old-golden
  regression under `hybrid-rerank` is being measured before merge
  ([docs/notes/day12-figure-noise.md](../notes/day12-figure-noise.md); Yi Xin:
  "先量 rerank 路的真实 delta 再定"); the Class B conflict asset is being authored
  (Yi Xin: option (a)).
