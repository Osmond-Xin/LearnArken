# Day 4 Design Discussions — 2026-07-15

> Distilled by AI (Claude, the implementing assistant) from the 2026-07-15
> working session, **filed the same day**; pending Yi Xin's review. Format:
> question → options → decision → rationale. Decisions were made by Yi Xin
> unless noted.

## D1. Learning workflow v2: 研→读→扫 (from Day 4 onward)

- **Context**: Yi Xin read Anthropic's "A Field Guide to Claude Fable:
  Finding Your Unknowns" and directed a learning-flow upgrade. The article's
  frame: outcomes are bottlenecked by unresolved unknowns; the four-quadrant
  model (known knowns / known unknowns / unknown knowns / unknown unknowns)
  plus practices — blind-spot pass, interviews, references, implementation
  plans, quizzes — make surfacing unknowns the core skill of agentic work.
- **Decision**: daily-cycle step 1 (学) becomes three sub-steps:
  1a **研** — a Chinese deep-research report on the day's domain (background,
  origins/development, current mainstream, future direction, best practices,
  must-master techniques and pitfalls) → `docs/research/dayN-report.md`;
  1b **读** — Yi Xin reads report + the day's tutorial;
  1c **扫** — the implementer produces an unknowns scan (blind-spot pass) +
  deep explanation of must-master points → `docs/research/dayN-unknowns.md`.
  Everything else in the daily cycle is unchanged.
- **Rationale**: mapping the article to learning a new domain — deep research
  compresses unknown unknowns into known territory up front; the scan then
  makes the remaining blind spots explicit before practice, instead of
  discovering them mid-implementation.
- **Recorded in**: CLAUDE.md (new mandatory rule), execution-plan.md (每日循环
  table + v2 note), docs/research/README.md, auto-memory.

## D2. Deep-research channel: official API, not `agy`, not `gemini` CLI

- **Context**: Yi Xin asked whether Gemini Deep Research can be driven via
  the `agy` command or needs the `gemini` command, and clarified mid-session
  that the requirement is the *real* Deep Research agent (multi-step
  autonomous exploration + synthesis), not single-pass web search + summary.
- **Verified findings (2026-07-15)**:
  - `gemini` CLI 0.36.0: auth is dead — Google discontinued Gemini Code
    Assist for individuals (IneligibleTierError, migration pointer to
    Antigravity). Not a channel.
  - `agy` (Antigravity CLI 1.1.2): works, has Gemini 3.5 Flash / 3.1 Pro and
    live web search (smoke-tested), but exposes **no Deep Research agent**
    (`agy agents` is empty).
  - Official channel exists: the Gemini **Interactions API** with agents
    `deep-research-preview-04-2026` / `deep-research-max-preview-04-2026`
    (April 2026 preview), via the google-genai Python SDK with background
    polling. Requires a **paid-tier** `GEMINI_API_KEY`; free-tier keys have
    no access. Sources: ai.google.dev/gemini-api/docs/deep-research,
    philschmid.de/deep-research-update.
- **Decision** (recorded by AI from the session's direction; channel ranking
  follows from Yi Xin's "use the real feature" instruction):
  primary = official Interactions API via `tools/deep_research.py`
  (blocked until a paid `GEMINI_API_KEY` is provisioned — open item), or
  manually running Deep Research in the Gemini app and archiving the report;
  fallback = `agy` + Gemini 3.1 Pro single-pass research, output labeled
  **simulated**.
- **Open item**: provision a paid-tier `GEMINI_API_KEY` (goes in local
  `.env`, never committed); first run of `tools/deep_research.py` doubles as
  its live verification.

## D4. Manual Gemini-app Deep Research becomes the primary channel

- **Context** (later the same day): Yi Xin decided to run Deep Research
  manually in the Gemini client — pasting a prepared prompt per day, then
  downloading the report into the repo for Claude to consume. This removes
  the paid-API-key blocker from the critical path (the Interactions API
  script remains as the automation option).
- **Decision**: AI maintains a self-contained Chinese prompt library for all
  ten days at `docs/tutorials/deep-research-prompts.md` (each prompt embeds
  reader persona + project context, since the Gemini app cannot see the
  repo). Reports land at `docs/research/dayN-report.md` with a source line
  (`Gemini App Deep Research + date`). Channel ranking updated in CLAUDE.md
  and docs/research/README.md: manual app > Interactions API > `agy`
  fallback (labeled simulated).
- **Rationale**: the real multi-step Deep Research agent is what's wanted;
  the app subscription already covers it, so the human-in-the-loop step
  costs one paste per day and no new key provisioning.

## D5. SPLADE / ColBERT: split into a Day 4b node, gated on evidence

- **Context**: Yi Xin's Day 4 direction included SPLADE ("to strengthen
  BM25") and ColBERT alongside MiniMax dense, hybrid+RRF, rerank and the
  ablation table. AI raised four objections before drafting the spec:
  1. **SPLADE does not strengthen BM25 on identifiers** — its weights live on
     a BERT wordpiece vocabulary (~30k), so a DMC is shredded into subword
     fragments and cannot be matched whole. SPLADE treats vocabulary
     mismatch, not identifiers; it is a third lexical path, never a
     replacement for the Day 3 identifier-preserving BM25.
  2. **Three records already put both out of slice** (execution-plan 切片外,
     README Roadmap *Planned*, discussions/day3 D2), and the project's own
     tutorial 04 §7 leverage ranking says they are立项-after-evidence items —
     shipping them before the ablation exists inverts that methodology.
  3. **Statistics**: 32 golden queries = 3.1pp per query; a 7-row ablation
     ranked on 1–2 query differences is noise plus multiple comparisons. The
     heavy red team (Day 4 is a ⚑ node whose Challenger attacks the eval
     method) would be right to reject it.
  4. **Feasibility is better than feared** (AI-verified): Vespa natively hosts
     both (SPLADE embedder since 8.321, ColBERT embedder), so no torch in the
     Python project — but we have never deployed *any* Vespa application
     package, and Day 4 already carries two unverified risks (MiniMax
     endpoint shape, Vespa schema deployment).
  Also noted: MiniMax serves dense embeddings and chat only — the "cost"
  rationale does not extend to SPLADE / ColBERT / reranker.
- **Options**: (a) split into Day 4a (4-row ablation) + Day 4b (SPLADE +
  ColBERT, gated on 4a's numbers); (b) all in Day 4, accepting INV-8 slippage
  and weak statistics; (c) ColBERT only; (d) SPLADE only.
- **Decision**: **(a)** — Day 4a ships the four-row ablation as `v0.4.0`;
  SPLADE and ColBERT move to a new **Day 4b** node whose justification is a
  *specific* gap exposed by 4a's per-category table (synonym queries still
  losing ⇒ SPLADE; identifier / fine-grained still losing ⇒ ColBERT).
- **Rationale** (Yi Xin): "用数字开门" — let the ablation decide. Keeps INV-8
  reachable, follows the project's own stated methodology, and makes "I
  decided against ColBERT with evidence" the interview story rather than "I
  stacked six techniques". No JD keyword is lost — only deferred by a day.
- **Consequences to record**: README Roadmap moves SPLADE/ColBERT from
  *Planned, indefinite* to "Day 4b, evidence-gated"; execution-plan.md gains
  the 4a/4b split. Whether Day 4b takes its own tag and shifts Day 5–10, or
  runs as a stretch node with no plan drift, is spec day4 Q7 (AI recommends
  the latter — the gate may legitimately stay shut).

## D6. Golden set expands to ~80 queries

- **Context**: the Day 3 set (32 queries: 27 answerable + 5 no-answer traps)
  was sized for a 2-row table. A 4-row ablation with a per-category breakdown
  needs enough queries *per category* for the category claims — and the
  per-category table is exactly what the Day 4b gate is read from, so its
  resolution is load-bearing, not cosmetic.
- **Options**: expand to ~80; keep 32 and publish confidence caveats; keep 32
  and cut ablation rows.
- **Decision**: **expand to ~80** (roughly 8–9 per category across identifier
  lookup, synonym/paraphrase, procedural, applicability-conditional,
  cross-reference, identifier perturbation, no-answer traps, …).
- **Rationale** (Yi Xin): the per-category attribution is the most persuasive
  part of the deliverable ("dense loses to BM25 on identifiers" must rest on
  a category, not an anecdote), and it is what gates Day 4b.
- **Red line unchanged**: AI drafts candidate queries and candidate anchors
  only (`eval/golden/day4.candidates.jsonl`, every line flagged
  `ai_suggested`); **Yi Xin selects and judges relevance** — never outsourced
  (execution-plan Day 3, eval/golden/README).

## D7. Day 4a spec adjudication — architecture: Vespa is a dense store, logic stays in Python

- **Context**: AI drafted docs/specs/day4.md with seven open questions; Yi Xin
  ruled on Q1–Q5 and Q7 in the same session.
- **Decisions** (transcribed):
  - **Q1** — approved *with an added step*: search the web docs first, then
    test with a small demo before implementing. Done in-session (see D8).
  - **Q3 — reranker runs in Python, not inside Vespa.** *Rationale (Yi Xin)*:
    hosting the reranker in the engine creates an architectural dependency and
    hurts portability/migratability.
  - **Q4 — BM25 stays in-process** (rank-bm25), same rationale applied
    consistently.
  - **Q5 — semantic chunking is IN** (honours D1's promise that semantic joins
    once embeddings exist). AI's scoping proposal — third row in the
    Day 3-style chunking table, retrieval ablation held at one fixed strategy
    to avoid a 12-cell cross-ablation — is flagged for confirmation.
  - **Q7 — Day 4b takes no separate tag**; Yi Xin continues into 4b after 4a,
    schedule unchanged, both under `v0.4.0`.
  - **Q6 (CI)** — re-opened: Yi Xin asked why tests cannot simply run in CI.
    AI wrote the explanation (fresh cloud VM, no `.env` by red-line design, no
    Vespa container) plus three options into the spec; ruling pending.
- **Consequence worth recording**: Q3 + Q4 together make **Vespa a dense
  vector store only** — BM25, RRF fusion and reranking all live in Python.
  Two good knock-on effects for Day 4a: the schema collapses to one embedding
  field plus filter attributes (no rank-profiles, no `global-phase`, no ONNX),
  a far smaller first Vespa deployment; and the "RRF must be in global-phase"
  worry evaporates because RRF is now Python fusing two rank lists.
- **Tension to resolve at Day 4b** (AI flag, no decision taken): Vespa was
  selected (day3 D2) *because* ColBERT late-interaction is native there — but
  "native" means the engine's `colbert-embedder` + a MaxSim rank expression,
  i.e. exactly the engine coupling Q3 rejects. Day 4b must either accept that
  coupling for ColBERT, or implement MaxSim in Python over multi-vectors
  stored in Vespa (feasible at toy scale) — in which case Vespa's
  ColBERT-nativeness buys nothing and the D2 selection rationale needs
  restating. Nobody had noticed this until the Q3/Q4 rulings made it visible.

## D8. MiniMax embedding endpoint — resolved by measurement, not by documents

- **Context**: per Q1's instruction (docs first, then a small demo), AI
  searched the MiniMax embedding docs and then probed the live endpoint.
- **Findings** (measured 2026-07-15; supersede the Deep Research report, whose
  sources for this were weak — Grokipedia / third-party repos):
  - shape is **MiniMax-native** `{model, texts, type}`, **not**
    OpenAI-compatible; response is a top-level `vectors` array; success is
    `base_resp.status_code == 0`;
  - model **`embo-01`**, dimension **1536** (report's number confirmed, but
    now on evidence); `MINIMAX_MODEL_NAME` is the *chat* model (`MiniMax-M3`)
    and must not be reused for embeddings;
  - both `Authorization: Bearer` **and** `X-Proxy-Token` are required;
    `GroupId` is **not** needed (the proxy handles it);
  - vectors are **L2-normalized** (|v| = 1.000) ⇒ Vespa
    `prenormalized-angular`, cosine ≡ inner product (spec Q2, settled);
  - **`type` is a genuine asymmetric-encoding switch**: same text at
    `type=db` vs `type=query` → **cosine 0.860**. Index with `db`, search with
    `query`; mixing is a silent recall loss.
- **Decision**: docs/local-services.md's open item is closed with these
  measured values; the client is written from the probe output, not from the
  report. The probe stays a throwaway (scratchpad), but its findings are now
  spec + local-services facts.
- **Method note worth keeping**: this is the day's clearest case for the
  learning-flow-v2 discipline — the deep-research report *asserted* 1536 dims
  from a weak source and said nothing definitive about `type`; one 30-line
  probe turned both into facts, and found the asymmetry switch that would
  otherwise have silently cost recall.

## D9. CI stays simple: local-green is the bar

- **Context**: AI presented three CI options (mock+fixtures / GitHub Secrets /
  Vespa service container) with a trade-off table for how Day 4's
  MiniMax-and-Vespa-dependent tests should run in CI.
- **Decision** (Yi Xin): **over-designed — reject the framing.** This is a
  **learning project**; CI/CD is deliberately simplified. It only has to run
  locally; **CI passes by default.**
- **Implementation**: tests needing MiniMax or Vespa are marked
  `@pytest.mark.integration` and skipped when the services are absent. CI keeps
  running the hermetic Day 1–3 tests and stays green. No GitHub Secrets, no
  mock/fixture layer, no Vespa in CI.
- **Consequence recorded honestly** (AI note, accepted into the spec): CI green
  no longer means "Day 4 is verified" — the local integration run is the
  verification. So Day 4's acceptance criterion reads "local integration run
  green" where Days 1–3 read "CI green", and the release notes state that the
  ablation numbers come from a local run. INV-5 is satisfied by the documented
  reproduction command + versioned golden set, not by CI executing it.
- **Method note**: worth remembering as a calibration signal — the AI defaulted
  to production-grade CI reasoning on a learning repo. "What is this project
  for" is a scoping input, not a detail.

## D10. Golden set expansion drafted — three findings surfaced by doing it

- **Context**: per D6, AI drafted candidate queries for the ~80-query set.
  50 candidates landed in `eval/golden/day4.candidates.jsonl` (all anchors
  validated against real `learnarken chunk` output; 10 deliberate zero-hit
  cases). Day 4's authoritative set = the existing 32 (reused, already judged)
  + whichever candidates Yi Xin accepts.
- **Biggest gap found**: the Day 3 set had **zero paraphrase queries** — its
  queries largely reuse the source's own words. That is precisely the category
  where dense retrieval earns its keep and the category that reads the SPLADE
  gate. 12 low-lexical-overlap paraphrases added (e.g. *"how far should the
  polished cylinder stick out of the undercarriage oleo?"* against source text
  *"Examine the main gear shock strut for … correct extension (visible chrome
  55-65 mm)"*).
- **Finding 1 — the whole IPD is one chunk.** All 7 existing identifier queries
  resolve to the same anchor (`/dmodule/content/illustratedPartsCatalog`), so
  `LA-29-4711-1` (pump) vs `LA-29-4711-9` (gasket) — one digit apart — are
  indistinguishable at chunk granularity. *Workaround*: build
  `identifier_perturbation` from **non-existent** near-misses where the right
  answer is zero hits; BM25 refuses correctly, dense is expected to return the
  IPD chunk anyway (a fake part number *looks like* a part number). That still
  satisfies the plan's "dense loses to BM25 on identifiers" requirement.
  *Open*: is IPD-as-one-chunk a chunking defect? Each `catalogSeqNumber` is a
  natural boundary, and a real IPD has hundreds of parts. AI recommends **not**
  fixing it in 4a (Day 3 scope; would move published numbers) — record it and
  let the ablation decide.
- **Finding 2 — applicability is metadata, not text.** The displayText lives in
  `dmStatus/applic` and is carried as chunk metadata, so *"which serial numbers
  use the lead-acid battery?"* cannot be answered by text retrieval at all. All
  applicability candidates were therefore grounded in content prose only.
  *Open*: concatenate applicability text into the indexed text? AI recommends
  no — keep it a filter, not a retrieval target (same trade-off already
  declined for DMC concatenation).
- **Finding 3 — the annotated Day 3 set has no `category` field** (the
  candidates file had one; the human-annotated file dropped it). The
  per-category table reads the Day 4b gate, so all ~82 need categories. AI
  proposed a categorization of the existing 32; **Yi Xin confirms on merge** —
  a miscategorized query mis-reads the gate.

## D3. Day 4 interim report is the labeled fallback

- **Context**: the Day 4 report was generated this session via the `agy`
  fallback *before* the official-API path is unblocked.
- **Decision** (AI proposal, flagged for review): file it as
  `docs/research/day4-report.md` with an explicit "simulated, not official
  Deep Research" banner; replace or augment it once the official channel has
  a key. The unknowns scan (`day4-unknowns.md`) is built against this interim
  report + tutorials 03/04.
