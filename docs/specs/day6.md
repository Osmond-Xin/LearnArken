# SPEC — Day 6: Upload + Q&A Demo (FastAPI + Streamlit, `v0.6.0`)

> Decision layer transcribed from Yi Xin's verbal instructions (2026-07-17
> session start); Interfaces / Acceptance / Out-of-Scope sections are
> **AI-drafted, pending approval**. The transcription resolves the open
> conflict flagged in `docs/research/day6-unknowns.md` §已知的未知 1
> (SSE streaming vs fail-closed) — see decision 3.

## Goal (one sentence) — [HUMAN, transcribed 2026-07-17]

Ship a local demo — Streamlit frontend + FastAPI backend — that supports
document upload (validated, with explicit success / failure / ingested
feedback in the UI) and interactive grounded Q&A over the corpus, started
with a single `make demo`, using SSE for responsiveness **with a retraction
protocol** when a fully generated answer fails citation verification —
tagged `v0.6.0`.

## Key Decisions — [HUMAN, transcribed from the 2026-07-17 instructions]

1. **Streamlit is a dumb client** (哑客户端): it performs no AI operations
   of any kind; every substantive computation goes over HTTP to the local
   FastAPI backend.
2. **Backend is FastAPI**, exposing upload and Q&A for the demo.
3. **SSE with retraction (召回)** — the ruling on unknowns-scan conflict 1:
   the answer streams over SSE for user experience, **and the stream itself
   is subject to recall**. When generation completes and the result carries
   no valid supporting citations, the case is judged a failure and is
   *recalled*: the frontend must visibly tell the user that content was
   generated but is void and has been retracted (有生成、但不作效、回撤).
   *Recorded deviation*: the unknowns scan had marked post-hoc retraction
   "unacceptable in the maintenance domain" and leaned to non-streaming;
   this human ruling supersedes that lean for the demo. INV-4's strict
   two-outcome contract applies to the **final** outcome: streamed text is
   explicitly labeled unverified until confirmed, and a retracted stream
   ends in the standard refusal — never a degraded answer.
4. **Security hardening is in scope**: guard against malicious search input
   and attempts to inject malicious code (via query text or uploaded
   documents). Two review agents are to be launched against the result
   (implemented as the mandatory cross-host adversarial review plus a
   dedicated security review — two non-implementing agents).
5. **Upload runs the existing validation**, and the frontend must show the
   outcome interactively: validation success, validation failure (with
   findings), ingested into the corpus (已入库), and the failure states.
6. **`make demo` one-command bring-up** of backend + frontend.

## Interfaces — [AI-drafted, pending approval]

### Backend (`learnarken.api`, served by uvicorn on `127.0.0.1:8100`)

- `GET /health` → `{status, services: {vespa, neo4j, minimax_config,
  threshold_artifact}}` — each probed fail-closed; used by the `make demo`
  preflight and the frontend banner.
- `POST /upload` (multipart, field `file`) → upload one data-module XML into
  the runtime package `var/uploads/package-upload/` (git-ignored), then:
  1. envelope checks (reject early, HTTP 4xx): extension `.xml`, size ≤ 2 MiB,
     sanitized basename (`[A-Za-z0-9._-]`, no path components), UTF-8
     decodable;
  2. `analyze_package()` over the uploads package (the Day 2 four-layer
     validator; defusedxml already guards XXE/billion-laughs);
  3. **error findings ⇒ `status: "rejected"`** — the file is removed again
     (the uploads package must never hold a module that failed validation)
     and the findings are returned for display;
  4. clean ⇒ `index_package([package-a, package-c, package-upload])` —
     re-embed + re-feed + manifest rewrite + graph sync, reusing the Day 4/5
     path unchanged; success ⇒ `status: "ingested"` (已入库) with chunk
     count; Vespa/embedding failure ⇒ the file is removed and
     `status: "index_failed"` (fail closed, HTTP 503) — no partial state
     the next query would trip over.
  Re-uploading the same filename replaces the module (idempotent write,
  INV-2).
- `POST /query` (JSON `{question}`, Pydantic `min_length=3`,
  `max_length=500`) → `text/event-stream`. Event protocol (each `event:` +
  `data:` JSON):
  - `status` — `{stage: retrieval | rerank | generating}` progress beats;
  - `token` — `{text}`: incremental **answer-field** text (never the raw
    `<think>`/JSON envelope), extracted from the LLM stream before any
    citation check runs — this is the deliberate pre-verification window;
  - `retract` — `{gate, message}`: generation happened but a fail-closed
    gate (`llm`, `llm-contract`, `citation-validation`) voided it; the
    client must withdraw all streamed tokens;
  - `result` — the full `AnswerResult` (answered or refusal placeholder);
    threshold-gate refusals arrive here with no prior tokens (nothing to
    retract — the LLM was never called);
  - `error` — `{message}`: fail-closed transport/service failure, sanitized;
  - `done` — terminal beat.
  Routes are **sync `def`** (Starlette threadpool) because the whole answer
  stack is synchronous — an `async def` route would block the event loop
  (unknowns scan §已知的未知 2); the engine runs in a worker thread feeding
  a queue the SSE generator drains.
- Corpus freshness stays per-request: `answer_question` re-chunks and
  `verify_corpus` re-verifies on every query (models themselves are
  process-cached). After an upload this is exactly what makes the new
  module immediately queryable and keeps the manifest check honest; the
  demo corpus is small enough that correctness wins over latency.
- LLM streaming: `chat_json_stream()` in `llm/minimax.py` (OpenAI-style
  `stream: true` SSE deltas — to be live-probed first, Day 5 precedent). If
  the probe shows the proxy cannot stream, fallback is pseudo-streaming:
  the completed answer text is chunked to the client **before** citation
  validation runs — the retraction window stays real; the limitation is
  recorded here and in the discussion memo.

### Frontend (`demo/streamlit_app.py` — dumb client)

- Talks only to `http://127.0.0.1:8100` with `requests`; **imports nothing
  from `learnarken`** (logic-drift guard, enforced by a test).
- Upload pane: file uploader → `/upload`; renders the four outcomes
  distinctly (validated+ingested ✅ / validation failure with findings ❌ /
  envelope rejection ⚠️ / index failure 🚫) — decision 5.
- Q&A pane: question box → SSE; streamed tokens render into a placeholder
  visibly labeled **“生成中 — 未经引用确证”**; on `retract` the placeholder
  is cleared and replaced by a prominent notice that generated content was
  withdrawn (decision 3); on `result` the verified answer + citation table
  (chunk_id, DMC, XPath, quote) replaces the stream. History in
  `st.session_state`.
- Model output is rendered **escaped** (`st.text`/code blocks, never
  `unsafe_allow_html`) — an uploaded document cannot smuggle HTML/JS into
  the operator's browser.

### Security envelope (decision 4, demo scope)

- Bind `127.0.0.1` only (both servers); no auth/rate-limit — not public.
- Query input: Pydantic length bounds; the question already goes outside
  the evidence fence (Day 5 spotlighting), corpus text stays inside it.
- Upload input: envelope checks above + defusedxml + four-layer validation;
  filename fully re-derived server-side (no client path reaches the fs).
- All operator-facing strings pass the existing `_sanitize` control-char
  strip; error events never echo raw exception internals beyond type+message.

### `make demo`

- Preflight (fail closed, actionable messages, no stack traces): repo-root
  cwd, `.env` present, threshold artifact present, Vespa + Neo4j reachable;
  any miss prints the fix command and aborts.
- Then: uvicorn (single worker — local models are per-process resident,
  unknowns scan §已知的未知 4) + Streamlit, both bound to localhost,
  Ctrl-C stops both.
- New deps with INV-2 upper bounds: `fastapi`, `uvicorn`, `python-multipart`
  (main), `streamlit` (demo group).

## Acceptance Criteria — [AI-drafted, pending approval]

- [ ] `make demo` from a clean checkout (services running) brings up both
      processes; preflight fails closed with actionable messages otherwise
- [ ] Upload of a valid synthetic module → UI shows validated + ingested;
      the module is immediately queryable (citations can point at it)
- [ ] Upload of a module with violations (package-b style) → UI shows the
      findings; the file does not enter the corpus
- [ ] Q&A happy path: tokens stream with the unverified label, then the
      cited answer with chunk ID + DMC + XPath renders
- [ ] Retraction path: a generation that fails citation validation streams,
      then is visibly withdrawn and ends as the standard refusal (INV-4
      final-outcome preserved); threshold refusals show no stream at all
- [ ] Frontend imports nothing from `learnarken` (test-enforced)
- [ ] API tests (TestClient, engine/LLM mocked — no live services in CI):
      upload reject/ingest/index-fail paths; SSE event order for answer,
      retract, threshold-refusal, and error cases; input-bound rejections
- [ ] Extractor unit tests: answer-field streaming across think block,
      split escapes, and absent answer key
- [ ] Red-team gate: cross-host adversarial review + security review (two
      agents) → docs/reviews/day6.md Part 1
- [ ] Branch → PR → squash → tag `v0.6.0`

## Explicitly Out of Scope (today) — [AI-drafted, pending approval]

- No public deployment concerns: auth, JWT, rate limiting, CORS beyond
  localhost, budget circuit breakers (unknowns scan §未知的已知 2)
- No multi-turn memory / conversation state server-side; no answer caching
  or lifespan corpus cache (per-request verification is the ruling above)
- No `GET /traces/{id}` or any trace-exposure endpoint (observation surface
  stays local — unknowns scan §未知的未知)
- No async refactor of the answer stack; no multi-worker serving
- No changes to the Day 5 gates, thresholds, or prompt contract
- Backlog #8 (manifest content-hash / index epoch) noted as adjacent but
  **not** pulled in
