# Day 5 Red-Team Review & Adjudication ⚑ heavy node

## Part 1: Red-Team Findings (non-implementing model, read-only review)

- Review target: `main...feat/day5` (grounded `query` CLI: MiniMax-M3 client,
  hardened config loader, Neo4j graph sync + interface-③ injection, answer
  engine with three fail-closed gates, five-span trace, threshold + sample
  eval tools, hermetic + live tests)
- Reviewing model: **Codex** (`codex exec --sandbox read-only`, cross-host via
  adversarial-review 0.5.0), 2026-07-16
- Cross-validation: the implementer (Claude) disclosed four self-review items
  in the review brief and ran an independent host-side pass. Tags: ✅ =
  implementer had already flagged it in docs before the review (spec
  Open-Questions / unknowns scan / discussions D3) — genuine convergence, not
  hindsight. Adjudication (Part 2) is the human's.
- Verdict from the external reviewer: **REVIEW_NEEDED** — "the answer path is
  fail-closed against some malformed citations, but not against unsupported
  claims with valid citations, prompt injection from metadata/graph, threshold
  artifact poisoning, or evaluation overclaiming."

| # | Grade | Tag | Finding | Location | Suggestion |
| --- | --- | --- | --- | --- | --- |
| 1 | P1 | cross-validated ✅ | **Valid citation ≠ groundedness**: gate 3 checks cited ids ⊆ retrieved set, not that `answer` is entailed by the cited text. A poisoned or hallucinated answer citing a real retrieved chunk ships. (Implementer flagged in day5-unknowns.md "已知的未知 #3" and D3: groundedness is the human half; the code enforces only the necessary condition.) | `answer/engine.py` citation validation | claim-level cited spans that are exact substrings of cited chunks, or extractive answers; do not treat a valid id as groundedness |
| 2 | P1 | cross-validated ✅ | **Prompt-injection surface from metadata/graph**: `dm_title`, chunk text, graph titles/refs, and the question are interpolated raw; **graph facts sit OUTSIDE the spotlighting delimiter**, and a crafted `dm_title` can break the `<document … dm_title="…">` attribute. (Implementer disclosed the graph-outside-delimiter gap in D3 and the review brief.) | `answer/prompt.py` build_user | move graph facts inside the delimited zone; serialize evidence as JSON with escaped strings; injection regression tests for title/body/graph/question |
| 3 | P1 | cross-validated | **Malformed LLM JSON exits 1, not the `llm-contract` refusal**: `chat_json` raises `LLMError` on unparseable content, which the CLI maps to fail-closed exit 1 — but the spec/trace contract says a contract violation is a *refusal* (exit 3) with a written trace. Injected evidence saying "emit not-json" becomes a cheap denial path and writes no trace. | `llm/minimax.py`; `answer/engine.py`; `cli.py` | separate transport failure (exit 1) from model-contract failure (`refuse("llm-contract")`, exit 3, trace written) |
| 4 | P1 | cross-validated ✅ | **Evaluation overclaims** (heavy-node core): live suite is 3+2; `citation_coverage = covered/answered` excludes false refusals; tests require id intersection, not answer correctness; the merge-gate artifact says "human review pending". A system that refuses 1/16 and hallucinates-with-valid-citation can still show coverage 1.0. (Implementer flagged the threshold circularity and the weak reranker gate in D3; the external sharpens the metric-definition critique.) | `tests/test_day5_integration.py`; `tools/answer_sample_eval.py` | report end-to-end answerable success over ALL answerable, false-refusal rate, trap refusal over the full trap set, and entailment; don't ship "review pending" as the gate |
| 5 | P1 | cross-validated ✅ | **Threshold tuned on the same set the tests use, and rounded**: `round(min_answerable, 4)` can round *up*, so the very query that set the threshold can then score below it and be falsely refused; no holdout. | `tools/measure_refusal_threshold.py` | choose from unrounded scores (store rounded separately); validate on a holdout / adversarial trap set (Day 8) |
| 6 | P1 | external-only | **Threshold artifact is cwd-relative and unvalidated**: Python `json` parses `NaN`; `score < NaN` is always false ⇒ gate 1 silently disabled. A `day5-refusal-threshold.json` in the cwd is loaded. | `answer/engine.py` load_threshold | resolve from a trusted repo path; reject non-finite / out-of-range; bind to model revision + golden checksum |
| 7 | P1 | external + host | **Graph facts are trusted prompt input over an open, hardcoded-cred Neo4j**; `bm25` mode skips `verify_corpus` yet still reads graph facts. Anyone reaching `0.0.0.0:7474` with `neo4j/learnarken` can poison a title/ref that later enters a prompt. (Implementer disclosed hardcoded creds + 0.0.0.0 in the brief; overlaps the standing Neo4j-binding backlog item from Day 4.) | `graph/store.py`; `answer/engine.py` | bind Neo4j to loopback; creds from env; graph epoch/content-hash verification; don't inject graph facts in unverified `bm25` mode |
| 8 | P2 | external-only | **Manifest verifies chunk *ids*, not content**; index writes Vespa before graph sync + manifest, so a failed graph sync can leave new Vespa docs + stale graph facts + a matching-id manifest, and query proceeds. | `retrieval/__init__.py` index_package | content hashes + graph-sync metadata in the manifest; verify Vespa and graph against one index epoch |
| 9 | P2 | external-only | **Trace stores full prompt payload + raw model content** (question, corpus text, `<think>`) under `eval/traces/`; git-ignore is not secret hygiene — CI/debug bundles may collect it. | `answer/engine.py`; `answer/trace.py` | full-payload traces opt-in; default to hashes/snippets; redact secret patterns; `0700` dir |
| 10 | P3 | cross-validated ✅ | Paths assume source-checkout layout (`config.REPO_ROOT = parents[2]`, cwd-relative trace dir) — brittle if site-installed. (Implementer disclosed in the brief.) | `config.py`; `answer/trace.py` | explicit config path / platform dir / package resource |
| 11 | P3 | external-only | CLI `_sanitize` strips ASCII controls only; Unicode bidi overrides can still spoof a citation/path in the terminal. | `package.py` `_sanitize` | strip Unicode bidi controls in human-facing output |

### Key risks if merged as-is (external summary, host-concurred)

1. **Groundedness is asserted, not enforced** (#1): the headline promise
   ("every answer traceable") holds for the citation *pointer* but not for the
   *claim* — a valid-id hallucination ships. This is the heavy node's central
   finding and the reason the Day 5 "citation coverage 1.0" number must not be
   read as "1.0 correct".
2. **The injection surface is real even on synthetic data** (#2, #7): metadata
   and graph text reach the model outside the passive-data fence; Day 8 will
   attack exactly this.
3. **The refusal contract has a hole** (#3): a model-contract violation escapes
   as an error exit, not the documented refusal — the two-outcome guarantee is
   incomplete.

## Part 2: Adjudication (Yi Xin, 2026-07-16 — transcribed by the implementer
under instruction, per the Day 3/4 precedent; wording faithful to the ruling)

Rulings, finding by finding:

1. **#3 / #5 / #6 (fail-closed holes) — FIX NOW.** Low-risk, unambiguous:
   malformed/contract-violating LLM output must become `refuse("llm-contract")`
   with a written trace (exit 3), not a transport error (exit 1); the
   threshold loader rejects non-finite / out-of-range values and resolves
   from a trusted repo path; the threshold is chosen from unrounded scores
   (display-rounded stored separately) so the zero-false-refusal rule holds.
2. **#1 (groundedness) AND #2 (injection) — BOTH DONE TODAY.** #1: the answer
   contract now requires a verbatim `supporting_quote` per citation, validated
   as an exact (whitespace-normalized) substring of the cited chunk — a
   machine-checkable entailment *necessary condition*; a failure refuses.
   Full claim-level span alignment and semantic entailment remain Day 8's
   deeper work, but "valid id" is no longer accepted as groundedness. #2:
   graph facts move inside the spotlighting delimiter; all evidence is
   serialized as JSON with escaped strings (no raw pseudo-XML attributes);
   injection regression tests for title / body / graph / question.
3. **#4 (evaluation overclaim) — FIX THE METRIC DEFINITIONS.** Report
   end-to-end answerable success over ALL sampled answerable queries, the
   false-refusal rate, and trap refusal over the full trap set; citation
   coverage no longer excludes false refusals; README wording softened
   ("coverage ≠ correctness"). The human groundedness review stays a
   *human* step, no longer the *only* groundedness signal (the #1 span
   check is now the machine floor).
4. **#7 (Neo4j trust) — bind loopback + env credentials NOW.** Merge with the
   standing Day 4 backlog item; container rebound to `127.0.0.1`, credentials
   read from `.env` (`NEO4J_*`).
5. **Backlog (Day 6+): #8** (manifest content hashes / index epoch), **#9**
   (trace secret hygiene — opt-in full payload, redaction, `0700`), **#10**
   (site-install path robustness), **#11** (Unicode bidi stripping).

Number re-runs (threshold, sample eval) are Yi Xin's before merge.

### Convergence log (post-fix red-team passes)

- **Pass 1** (Codex, on the #1–#7 fix commit): #2/#3/#4/#5/#6/#7 **CLOSED**;
  **#1 NOT_CLOSED** — the `supporting_quote` check was bypassable: `""` and
  whitespace substring-match any chunk, 1-char/common quotes are trivial, and
  `setdefault` skipped validating a duplicate `chunk_id`'s second quote.
  Verdict NOT_CONVERGED. Fixed in `fb7e167`: every raw citation validated
  (id ∈ retrieved set + ≥12 normalized chars + verbatim containment), de-dup
  only after all pass; three regression tests added; live golden 5/5
  unaffected.
- **Pass 2** (on `fb7e167`): **NEW FINDINGS: none.** The reviewer holds #1
  NOT_CLOSED on one residual: a ≥12-char boilerplate span present in *every*
  retrieved chunk still substring-matches and could accompany an unsupported
  answer. This is the substring floor's inherent limit — verbatim containment
  is a *necessary, not sufficient* condition for entailment; no substring
  rule can certify that a quote semantically supports a claim. That gap is
  exactly what Part 2 ruling #2 assigned to Day 8 (semantic entailment /
  claim-level alignment). **Escalated to Yi Xin** as a scope decision, not a
  code defect: hold the substring floor + Day 8 for semantics, or add a
  cheap extra necessary-condition now (reject a quote that appears in *all*
  retrieved chunks — kills the specific boilerplate bypass without pretending
  to solve entailment).
  **Ruling (Yi Xin): add the cheap defense, semantics to Day 8.** Done: a
  quote present in every retrieved chunk is rejected as non-discriminating
  (regression-tested); live golden 5/5 unaffected. Semantic entailment
  (NLI / LLM-judge) remains the Day 8 adversarial-eval deliverable — the
  substring + boilerplate rules are the documented machine floor, not a
  groundedness proof.
- **Pass 3**: recorded below once complete.
