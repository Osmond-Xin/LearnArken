# Day 5 — Design Discussions (distilled)

> AI-distilled from working sessions (Claude, implementer), human-reviewed.
> Same-day rule: every decision-producing discussion lands here in-session.

## D1. Day 5 opening rulings: query CLI, MiniMax-M3, mandatory citations, graph sync

- **Context**: Day 4 closed (v0.4.0, 2026-07-16); Yi Xin opened Day 5 in the
  same session with the decision layer, transcribed into docs/specs/day5.md.
- **Decisions** (transcribed):
  1. New `learnarken query "<question>"` CLI.
  2. Answer LLM = **MiniMax-M3** — supersedes the execution plan's "Claude
     API" line for Day 5. Config = the four `MINIMAX_*` vars (values on
     hand). Note the boundary: Day 4's adjudication removed MiniMax as an
     *embedding* provider; generation was not covered by that ruling.
  3. Every answer traceable: chunk ID + DMC + XPath, mandatory.
  4. Unanswerable ⇒ fixed refusal placeholder ("I don't know" 类), INV-4.
  5. Tests: golden questions with citation verification, AND no-answer
     questions asserted to hit the placeholder.
  6. **Graph sync + combined query**: indexing syncs Neo4j; `query`
     combines vector and graph — pulls the minimal graph slice forward
     from Day 9 (ADR-0002 to be amended per the Q1 ruling).
  7. Post-implementation review is the standing automatic gate (Day 5 is a
     ⚑ heavy node).
- **Process note**: 研 was already in the archive (all ten DR reports
  generated 2026-07-15); 扫 is docs/research/day5-unknowns.md; spec open
  questions Q1–Q4 put to Yi Xin before implementation, per role boundaries.

## D2. Q1–Q4 adjudicated: graph shape, strict refusal, English, hybrid-rerank

- **Rulings** (Yi Xin, same session, transcribed):
  - **Q1** — graph sync at index time (DM nodes, dmRef/ICN edges,
    idempotent) + **interface ③ context injection** in `query`; no
    graph-neighbor retrieval expansion; multi-hop tools stay Day 7/9.
    ADR-0002 amended: sync + injection land Day 5, the dependency-query
    class stays Day 9.
  - **Q2** — **strict two-outcome**: cited answer or placeholder refusal,
    nothing in between. The DR report's graded-degradation band was
    considered and declined (INV-4 cleanliness; smaller Day 8 surface).
  - **Q3** — answers fixed **English**, placeholder included.
  - **Q4** — `query` runs on **hybrid-rerank**; `--mode` override kept.
- **Implementation notes bound by these rulings**: the refusal threshold
  is measured from golden-set reranker-score distributions and recorded as
  an artifact (INV-5) — never hand-picked; Neo4j is accessed over its HTTP
  tx API behind a `graph/` abstraction (same pattern as `vespa/store.py`,
  no new driver dependency); the MiniMax-M3 chat endpoint is probed live
  before the client is written (Day 4 Q1 precedent — its embeddings
  endpoint was not OpenAI-shaped).

## D4. Heavy red team + adjudication: groundedness floor, injection fence, honest metrics

> AI-distilled, same session (2026-07-16); transcription of Yi Xin's
> finding-by-finding ruling in docs/reviews/day5.md Part 2; pending human
> review. Full findings: docs/reviews/day5.md Part 1 (Codex cross-host,
> verdict REVIEW_NEEDED, 11 findings; 4 pre-flagged by the implementer).

- **Central finding (cross-validated)**: "every answer traceable" held only
  for the citation *pointer* (cited id ⊆ retrieved set), not the *claim* — a
  valid-id hallucination could ship. The 20-sample coverage 1.0 was not
  "1.0 correct".
- **Rulings executed this session** (commit set below):
  - **#1 groundedness** — the answer contract now requires a verbatim
    `supporting_quote` per citation, validated as a whitespace/case-tolerant
    substring of the cited chunk. A machine-checkable entailment *necessary
    condition*; any quote not found in its chunk refuses. Live golden 5/5
    still pass and real answers now surface the quote, so M3 can meet the
    contract — but full semantic entailment stays Day 8.
  - **#2 injection** — all corpus/graph material is now escaped JSON inside
    the spotlighting delimiter (graph facts moved *inside*; no raw
    `dm_title="…"` attribute to break out of). Regression test: a title
    carrying `"></document><system>…` survives only as an escaped string
    value, nothing outside the fence.
  - **#3 contract hole** — a model-contract violation is now
    `LLMContractError` → `refuse("llm-contract")` (exit 3, trace written),
    distinct from transport `LLMError` (exit 1).
  - **#5/#6 threshold** — chosen from unrounded scores (display value stored
    separately); loader rejects non-finite / out-of-[0,1] values and resolves
    from the repo root, so a cwd `{"threshold": NaN}` can't disable gate 1.
  - **#4 honest metrics** — the sample eval now reports `answerable_success`
    (0.875), `false_refusal_rate` (0.125), `trap_refusal_rate` (1.0) over the
    FULL sampled sets; the old covered/answered ratio is kept but relabeled
    "when answered" so it isn't read as accuracy. README softened.
  - **#7 graph trust** — Neo4j rebound to `127.0.0.1`, credentials read from
    `.env` (`NEO4J_*`). (Merges the standing Day 4 Neo4j-binding backlog item.)
  - **Backlog (Day 6+)**: #8 (manifest content hashes / index epoch), #9
    (trace secret hygiene), #10 (site-install paths), #11 (Unicode bidi).
- **Lesson**: the heavy node paid off by attacking the *promise*, not the
  code — "traceable" quietly meant "pointer valid", and only a groundedness
  attack surfaced the gap between a valid citation and a supported claim.

## D3. Implementation findings: M3 wire quirks; the threshold gate is weak and its rule changed

> AI-distilled, same-session (2026-07-16); pending human review. The
> threshold-rule change below is an **AI-proposed elaboration decision**,
> flagged for Yi Xin's veto and offered to the red team as a target.

- **M3 wire facts (both measured live, now unit-tested)**: the chat endpoint
  is OpenAI-shaped (unlike the retired embeddings endpoint) but (a) content
  ALWAYS carries a `<think>…</think>` prefix — no separate reasoning field —
  and (b) on longer real prompts M3 wraps the JSON in a ```json fence *even
  with `response_format: json_object` set*. The short probe prompt did not
  trigger (b); the first real query did. Lesson repeated from Day 4: probe
  results are necessary, not sufficient — parse defensively.
- **The reranker-score refusal gate is weak at this scale** (artifact
  `eval/results/day5-refusal-threshold.json`): the distributions overlap
  hard — answerable min 0.0004 (a paraphrase query the cross-encoder
  underscores) vs no-answer max 0.6039 (identifier-perturbation traps are
  near-duplicates of real chunks). No threshold separates them.
- **Threshold rule changed after a real false refusal**: the initial
  min-error rule (threshold 0.0029) refused golden C101, an answerable
  paraphrase question. Changed to **zero-false-refusal** (threshold = min
  answerable top-1, refuse strictly below): gate-1 errors are unrecoverable
  short-circuits, while traps that slip through are still caught behind it —
  measured: the LLM gate refused 2/2 live traps; gate 1 now catches only
  1/15 traps and exists mainly as a cost/attack-surface guard. Honest
  caveat in the artifact: the rule is tuned on the measurement set; Day 8
  measures generalization.
- **Graph sync numbers**: 10 DM nodes, 10 edges (REFS + USES_ICN) from the
  43-chunk corpus; `facts()` feeds interface-③ context and the answer's
  graph block.
