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

## D11. Length bias verified as real; LangChain refactor evaluated and not warranted

- **Context**: Yi Xin challenged the length-bias finding — is it a genuine
  model defect or a configuration mistake on our side? — and asked whether the
  project should adopt LangChain as its pipeline foundation, refactoring if
  needed, on the hypothesis that a settings problem caused the phenomenon.
  Directed a web-search verification.
- **Verification** (three independent checks, 2026-07-16):
  1. **Wire equivalence**: LangChain's `MiniMaxEmbeddings` builds the same
     request we do (`{model, type, texts}`, db/query split, Bearer). Replayed
     byte-for-byte: without `X-Proxy-Token` (stock LangChain) the proxy answers
     **403** — it cannot even connect; with the token, the returned vector
     equals ours at **cosine 1.000000**. A framework swap cannot change any
     vector.
  2. **Control model**: BGE-small-en-v1.5 locally, same texts, same cosine —
     repetition stays stable (0.848→0.857 vs embo-01's 0.758→0.576), no
     inversion, mean rank **2.00**/35 vs embo-01's 16.25. Texts and math are
     exonerated; the model is the variable.
  3. **Literature**: length bias in cosine-trained embedding retrieval is a
     documented failure-mode class (e.g. arXiv 2412.15241).
- **Verdict**: the defect is **real and provider-side** (with the honest caveat
  that "embo-01" = whatever the proxy serves under that name); it is not a
  settings problem, and the hypothesis motivating a LangChain refactor is
  disproven by measurement.
- **On LangChain as pipeline foundation** (AI analysis, decision remains open
  to Yi Xin): recommend **no refactor**. (a) It cannot fix the observed
  problem — wire-identical; (b) stock LangChain cannot authenticate to this
  proxy at all (no custom-header hook in `MiniMaxEmbeddings` short of
  subclassing); (c) the swap-point LangChain would provide already exists —
  `embedding/minimax.py` is one module behind one function, and the control
  experiment doubled as proof (fastembed slotted into the same cosine harness
  in ~20 lines); (d) the project's style rule is minimal dependencies, and the
  interview-value of "I measured my provider and understood the failure" is
  higher than "I used a framework".
- **Bonus**: the control experiment is de facto the "local model as ablation
  control row" from the pending decision (docs/notes, option 3) — BGE-small
  via fastembed (ONNX, no torch) measured mean rank 2.00 on the 4 probes.

## D12. LangChain is a learning goal, not a bug fix; local-model selection (pending)

- **Correction to D11's framing** (Yi Xin, 2026-07-16): the motive for
  LangChain is to **learn the framework through this project** — unrelated to
  the embedding defect. D11's "no refactor" verdict answered the wrong
  question (can LangChain fix the bug? no) and does not answer this one
  (should the project adopt LangChain as a learning vehicle?).
- **AI analysis of where LangChain teaches the most, mapped to our plan**:
  | LangChain primitive | Maps to | Note |
  | --- | --- | --- |
  | `Embeddings` interface | our `embedding/` module | wrap MiniMax client as a subclass (~20 lines); local models via `HuggingFaceEmbeddings` |
  | `BM25Retriever` | Day 3 BM25 | built on the same `rank_bm25`; takes `preprocess_func` — our identifier-preserving tokenizer plugs straight in |
  | `EnsembleRetriever` | Day 4 RRF fusion | its fusion algorithm IS reciprocal rank fusion |
  | `ContextualCompressionRetriever` + `CrossEncoderReranker` | Day 4 rerank layer | `HuggingFaceCrossEncoder` loads bge-reranker locally |
  | `VespaRetriever` (community) | our `vespa/store.py` | optional; pulls pyvespa — our thin store already gives the swap point |
  | LCEL / chains / citations | **Day 5 RAG** | the highest-value place to learn the framework |
- **Machine reality** (checked): Apple M5 Max, 64 GB — any local embedding
  model up to Qwen3-Embedding-8B (Q4 ≈ 5 GB) runs comfortably.
- **Local embedding candidates** (2026 landscape, web-verified):
  BGE-M3 (560M; dense 1024d + sparse lexical weights + ColBERT multi-vector
  from ONE model; 8k ctx; MIT; official pyvespa notebook — Vespa is the one
  engine that serves all three representations), bge-small/base-en-v1.5
  (33/109M; the control that already measured mean rank 2.00), nomic-embed-
  text-v1.5 (137M, MRL), Qwen3-Embedding 0.6B/8B (MTEB open-source leader,
  MRL, instruct-aware).
- **AI recommendation**: adopt LangChain for the remaining Day 4a retrieval
  plumbing (BM25Retriever + EnsembleRetriever + CrossEncoderReranker) where it
  replaces code not yet written, keep `embedding/` + `vespa/store.py` as thin
  adapters behind LangChain interfaces; pick **BGE-M3** as the local model —
  best Vespa fit and it pre-loads Day 4b (its sparse output reads the SPLADE
  gate, its multi-vector output reads the ColBERT gate, from one model).
- **Decisions pending Yi Xin**: (a) LangChain enters now (Day 4a remainder) or
  at Day 5; (b) which local model. Spec decision-layer amendment required
  either way.

## D13. Adjudication of D12 + LangChain retrofit audit of Days 1–3

- **Rulings** (Yi Xin, 2026-07-16): LangChain is adopted **now** as the
  system-default technology stack (learning goal); Days 1–3 are audited and
  upgraded to LangChain **where an equivalent exists**; architecture docs get
  a dedicated LangChain section. Dense bake-off runs MiniMax / BGE-M3 /
  **Qwen3-8B** (Yi Xin picked 8B for maximum effect after the size-vs-quality
  discussion), winner becomes default. Both workstreams in parallel.
- **Retrofit audit result**:
  | Day | Component | Verdict |
  | --- | --- | --- |
  | 1–2 | XML security parsing, canonical Pydantic model, four-layer validator | **No LangChain equivalent** — validation is not the framework's domain. Stays custom. |
  | 3 | recursive control chunker | **Upgraded**: LangChain `RecursiveCharacterTextSplitter` (800/100). Boundaries differ slightly → Day 3 recursive row re-measured. |
  | 3 | BM25 | **Upgraded**: LangChain `BM25Retriever` (same rank-bm25 underneath) with our identifier tokenizer as `preprocess_func`. Three red-team-hardened behaviors stay OURS on top (attribute-identifier indexing, token-overlap hit test vs negative IDF, scored results) — the framework has no hook for them. |
  | 3 | structure-aware chunker | Domain IP, no equivalent — stays. Chunks bridge to LC `Document` via one conversion module. |
  | 3 | semantic chunker | Algorithm identical to LC's `SemanticChunker` (percentile breakpoints); kept ours (40 lines) rather than adding the `langchain_experimental` grab-bag dep, now consuming the default LC `Embeddings` provider. |
  | 3 | eval harness (Recall/MRR/nDCG) | No LangChain equivalent. Stays. |
- **Risk recorded**: `langchain-community` (home of `BM25Retriever`) is
  **being sunset** (deprecation warning at import; maintainers point to
  standalone integration packages). Accepted for now — it wraps the same
  rank-bm25 we already depend on, and our domain layer means the retriever
  could be re-homed in an afternoon. Revisit if a standalone package appears.

## D14. Dense bake-off: Qwen3-8B wins and becomes the default

- **Method**: three providers behind one LangChain `Embeddings` interface,
  exact cosine in Python (no ANN confound), scored by the unchanged Day 3
  harness on eval/golden/day4.jsonl (82 queries; 32 human-reviewed subset
  reported separately), structure chunks of package-a+c (43).
- **Result** (docs/notes/day4-dense-bakeoff.md, reproduce:
  `uv run python tools/dense_bakeoff.py`):
  | Provider | R@5 | R@10 | MRR | nDCG@10 | R@5 (human-32) |
  | --- | --- | --- | --- | --- | --- |
  | MiniMax embo-01 | 0.500 | 0.679 | 0.359 | 0.430 | 0.463 |
  | BGE-M3 | 0.910 | 0.970 | 0.833 | 0.866 | 0.926 |
  | **Qwen3-8B** | **0.985** | **1.000** | **0.870** | **0.903** | **0.963** |
- **Consequences**: `DEFAULT_PROVIDER = "qwen3-8b"`; Vespa schema tensor
  1536 → 4096, redeployed and re-fed; end-to-end spot check — the query that
  ranked 31/35 under MiniMax now returns the correct chunk at #1 (0.7975),
  and a zero-overlap paraphrase ("which post comes off the power cell
  first?") hits the right warning+step at #1–2. MiniMax stays implemented as
  the ablation's contrast row; its length-bias finding stands as a Day 4
  artifact. BGE-M3 stays for Day 4b (sparse/ColBERT representations).
- **Bake-off caveats (for the red team)**: 50 of 82 queries carry AI-drafted
  anchors pending Yi Xin's review — the human-32 subset shows the same
  ordering, so the conclusion is stable across provenance; dense rows always
  return k hits, so no_answer/identifier_perturbation categories read 0 for
  all providers by construction and did not influence the ranking.
- **Vespa lesson recorded**: changing a field's tensor dimension is blocked by
  the engine's validation gate (`field-type-change`) — production data-loss
  protection. Dev-time bypass: `validation-overrides.xml` with an expiry date
  (checked in, expires 2026-07-23).

## D15. Ablation results: dense dominates at toy scale; the gates read differently than predicted

- **Numbers** (82 queries, structure chunks, `learnarken eval ablation`):
  bm25 R@5 0.821 / dense **0.985** / hybrid 0.910 / hybrid-rerank 0.970;
  zero-hit rate bm25 0.40, all dense-bearing modes 0.00; p50 <1 / 53 / 56 /
  214 ms. Per-category and the three honest footnotes (hybrid < dense; why
  rerank raising R@5 does not violate the pre-committed self-check; latency
  caveats) in docs/notes/day4-failure-cases.md.
- **The plan's predicted failure case inverted**: dense (Qwen3-8B) did NOT
  lose identifier lookups (0.857 vs BM25 0.714 R@5) — the textbook failure is
  scale/model-dependent. The *real* dense failure is **inability to refuse**:
  for the nonexistent `LA-29-4711-5`, BM25 correctly returns nothing, dense
  confidently returns the parts catalog. That asymmetry (zero-hit 0.40 vs
  0.00) is the documented reason the lexical arm stays.
- **Day 4b gate reading** (spec decision 8): the paraphrase gap the SPLADE
  gate watches is **closed by the new dense default** (paraphrase R@5: BM25
  0.33 → dense 1.00); identifier/fine-grained is not losing either. On these
  numbers **neither SPLADE nor ColBERT is justified — the gate stays shut**,
  pending Yi Xin's adjudication (and the red team's attack on the eval).
- **Chunking table completed** (Q5): semantic row R@5 0.815 / MRR 0.741 —
  structure-aware (0.926) still wins; retrieval ablation ran on structure, as
  pre-declared.

## D3. Day 4 interim report is the labeled fallback

- **Context**: the Day 4 report was generated this session via the `agy`
  fallback *before* the official-API path is unblocked.
- **Decision** (AI proposal, flagged for review): file it as
  `docs/research/day4-report.md` with an explicit "simulated, not official
  Deep Research" banner; replace or augment it once the official channel has
  a key. The unknowns scan (`day4-unknowns.md`) is built against this interim
  report + tutorials 03/04.
