# Day 3 Design Discussions — 2026-07-14

> Distilled by AI (Claude, the implementing assistant) from the 2026-07-14
> working session, **filed the same day**; pending Yi Xin's review. Format:
> question → options → decision → rationale. Decisions were made by Yi Xin
> unless noted.

## D1. Which chunking strategies, and when?

- **Context**: Yi Xin wants three strategies compared in this project:
  recursive, semantic, structure-aware. Semantic chunking needs an embedding
  model, which the execution plan introduces on Day 4.
- **Options**: (a) Day 3 = structure-aware (primary) + recursive (control),
  semantic joins the Day 4 ablation once embeddings exist; (b) pull a small
  embedding model into Day 3 and do all three at once (widens the day's
  scope, risks the two-calendar-day slip rule).
- **Decision**: (a) — semantic chunking moves to Day 4.
- **Rationale**: structure-aware is the natural fit for S1000D-like content
  (documents carry their own cut lines: steps, warnings, references);
  recursive serves as the control that lets the eval table *quantify* what
  structure-awareness is worth. Tutorial 02's lever ordering says
  analyzer/chunking is the highest-leverage fix — measure it first, cleanly,
  on BM25 alone.

## D2. Vector database selection (decided now, lands Day 4)

- **Context**: Yi Xin raised that ColBERT-class late-interaction models have
  special storage requirements (one vector per token, MaxSim query), so the
  store should be chosen *before* chunk/embedding/storage work, not after.
  The AI analysis agreed on the ordering and confirmed the constraint: most
  vector stores cannot serve multi-vector MaxSim at all.
- **Options**: Qdrant (execution plan's Day 4 default; multivector MaxSim
  supported; lightest ops), Vespa (late interaction as a first-class
  citizen; heaviest ops), pgvector / Chroma / FAISS (no ColBERT path,
  ruled out).
- **Decision**: **Vespa**, run via docker (docker already installed and
  running on the dev machine). Paper decision today; implementation is
  Day 4. ColBERT itself stays out of the slice (Planned) — the selection
  only keeps that road open.
- **Rationale** (Yi Xin, overriding the AI's Qdrant recommendation): choose
  the engine where the late-interaction path is native rather than an added
  feature; the operational weight is accepted, and docker is already
  available locally.
- **Consequence to record**: execution-plan.md Day 4 said
  "Qdrant (docker compose)" — amended to Vespa on 2026-07-14 by Yi Xin's
  instruction in the same session (spec day3 Q4 adjudication). Vespa also
  ships BM25/hybrid natively; whether Day 4 re-homes the BM25 baseline into
  Vespa or keeps it in-process is a Day 4 spec question.

## D3. Graph store for triples / graph-RAG

- **Context**: key information for the future graph does not require NLP
  extraction — Day 2's L3 validator already builds the reference graph, and
  DMC / applicability / warnings are structured model fields. So
  "extraction" here means deterministic serialization of the canonical
  model, not entity/relation mining from text.
- **Options**: RDFLib (in-process, SPARQL, the "minimal" option aligned with
  the Day 4 re-evaluation checkpoint), Kùzu (embedded property graph),
  Neo4j (industry standard, docker service).
- **Decision**: **Neo4j**, via docker. The *store* is decided now; *whether
  and when* a minimal graph query is pulled into the slice remains at the
  Day 4 re-evaluation checkpoint, as planned.
- **Rationale** (Yi Xin): standard industry choice; docker already running
  locally, so the ops objection to a served database does not bite.
- **Day 3 obligation**: chunks must not starve the future graph — carry
  `dmc`, outbound `dmRef`s, and ICN refs in chunk metadata so triples can be
  derived from the model at any later day.

## D4. Chunk metadata semantics: 紧急场合 / 排除场合

- **Question**: does "紧急场合" (urgency context) mean ① the chunk's content
  contains hazard warnings, or ② the task itself is an emergency/abnormal
  procedure?
- **Decision**: ① — **content contains danger warnings**. Modeled as hazard
  flags on the chunk (e.g. `has_warning` / `has_caution`), so retrieval can
  force-include or boost safety-critical chunks.
- **排除场合** (exclusion context) maps to the Day 2 applicability model:
  structured assertions (serial range, variant) on the chunk let queries
  filter out chunks inapplicable to a given model/variant. package-c is the
  designated test input for this.

## D5. Backlog: direct S1000D → graph-database mapping

- **Context**: real S1000D already defines structure and relationships;
  industry approaches exist that map S1000D XML directly into a graph
  database (ontology / property-graph mappings), skipping text chunking for
  the relational layer entirely. This project uses traditional RAG chunking
  because of scope and data-access limits (no real S1000D content, INV-1).
- **Decision**: record it, don't build it now. Two places: a Planned-tier
  line in the README Roadmap (added in the Day 3 PR), and an expanded
  paragraph in the Day 4 checkpoint ADR. Revisit if time remains late in
  the slice.

## D6. Basic testing for search and storage

- **Decision**: two layers.
  - **Search quality**: the execution plan's Day 3 golden set (30–50
    human-annotated query → relevant-chunk pairs; AI may only draft
    candidate questions) + `learnarken eval retrieval` reporting
    Recall@k / MRR / nDCG, fixed seed, versioned golden set.
  - **Storage sanity** (new, from this discussion): chunk counts reconcile
    against source DMs; chunk IDs are deterministic across re-runs;
    metadata round-trips intact; an applicability-exclusion filter test
    proves "exclude variant X" really excludes.

## D8. Embedding provider = MiniMax (forward decision for Day 4)

- **Context**: Yi Xin directed that embeddings use MiniMax's embedding API,
  configured like the FollowTheBig project
  (`/Users/osmond/Documents/project/FollowTheBig`, `.env` + client at
  `src/followthebig/utils/llm.py`). Recorded now so it is not lost; the call
  itself is Day 4 (Day 3 is BM25-only).
- **Decision**: MiniMax is the embedding provider. Env vars `MINIMAX_API_URL`
  / `MINIMAX_MODEL_NAME` / `MINIMAX_API_KEY` / `MINIMAX_API_PROXY_TOKEN`,
  secrets in local `.env` only (docs/local-services.md documents the shape,
  no values).
- **"Special implementation" to carry over**: the reference client is
  OpenAI-compatible **but adds a non-standard `X-Proxy-Token` header**
  (the proxy token) beside the Bearer key — a stock OpenAI SDK omits it.
- **Open item (Day 4)**: the reference client only does chat completions
  (`/chat/completions`), **no embedding endpoint** — the embedding call is
  new code. Endpoint shape (OpenAI-style `/embeddings` vs MiniMax-native
  `texts` + `type: db/query` + `GroupId`) must be verified against the live
  endpoint before Day 4 implementation. This partly reopens the Day 4 spec's
  "BGE or E5 embedding" line — that becomes MiniMax.

## D7. Process rule: same-day discussion memos

- **Context**: Day 2's discussion record was filed a day late; Yi Xin flagged
  the recurring omission again today and directed that the rule be made
  binding in the repo's AI operating rules, not just session memory.
- **Decision**: `CLAUDE.md` gains an explicit rule — every working
  discussion that produces decisions is distilled into
  `docs/discussions/dayN.md` the *same day*, in-session, as part of the
  day's deliverable checklist. This file is the first artifact filed under
  that rule.
