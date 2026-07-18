# Day 6 — Design Discussions (distilled)

> AI-distilled from working sessions (Claude, implementer), human-reviewed.
> Same-day rule: every decision-producing discussion lands here in-session.

## D1. Day 6 opening rulings: demo shape, and the SSE × fail-closed adjudication

- **Context**: Day 5 closed (v0.5.0, 2026-07-17). The Day 6 unknowns scan
  (committed 6e0fea6) had flagged its #1 finding: SSE streaming and the
  citation-verification gate are in direct conflict — gate 3 can only run
  on the complete JSON, so any streamed token reaches the user unverified.
  It listed three exits: (a) no streaming, (b) progress-events only,
  (c) true streaming + post-hoc retraction — and noted (c) had been
  presumed unacceptable in the maintenance domain. The SPEC decision layer
  was blocked on this ruling.
- **Decisions** (Yi Xin, session start 2026-07-17, transcribed):
  1. Streamlit frontend as a **dumb client** — zero AI operations in the
     UI; everything over HTTP to a FastAPI backend.
  2. **FastAPI backend with SSE** for user experience.
  3. **Ruling on the conflict: exit (c)** — SSE streams, and the stream is
     itself recallable (SSE 也需要召回). When generation completes with no
     valid supporting citations, the case is a failure and is recalled: the
     frontend must explicitly tell the user content was generated but is
     void and withdrawn (有生成、但不作效、回撤). This supersedes the
     scan's lean toward (a).
  4. **Security in scope**: defend against malicious search input and
     malicious-code injection (query text and uploaded files); two agents
     to be launched against the result for review.
  5. **Upload → validation → explicit UI feedback**: success, failure,
     ingested (已入库) must each be visible interactions.
  6. **`make demo`** one-command bring-up.
- **INV-4 reconciliation** (implementer reading, recorded in the SPEC):
  the strict two-outcome contract binds the *final* outcome. The streamed
  text is labeled unverified while in flight; a failed verification ends in
  the standard refusal placeholder plus an explicit retraction event —
  never a silently kept degraded answer. The pre-verification window is a
  deliberate, visible property of the demo, not a leak.

## D2. Implementation-shaping findings (same session, implementer)

- **The LLM emits a JSON envelope, not prose** — `<think>…</think>` then
  `{"is_answerable": …, "answer": …, "citations": […]}`. Streaming the raw
  stream would show the user braces and think-text. Resolution: an
  incremental extractor that forwards only the `answer` string field's
  content; the prompt contract already fixes the key order
  (`is_answerable` → `answer` → `citations`), so answer text streams early.
- **Sync stack ⇒ sync routes**: `answer_question` and the MiniMax client
  are synchronous; FastAPI routes are declared `def` (threadpool), engine
  in a worker thread feeding the SSE generator via a queue — per the scan's
  已知的未知 2, no async refactor.
- **Per-request corpus verification kept** (scan 已知的未知 3): after an
  upload re-indexes, the next query's `verify_corpus` is exactly the
  freshness check; the demo corpus is small, correctness wins. No lifespan
  cache, so no invalidation policy needed today.
- **Upload "已入库" = the existing Day 4/5 path unchanged**:
  `analyze_package` → on clean, `index_package([a, c, uploads])` (re-embed,
  manifest rewrite, graph sync). Rejected or index-failed uploads are
  removed again — the uploads package never holds an unvalidated module,
  and there is no partial state (a mid-feed failure leaves a stale manifest
  that the next query's `verify_corpus` refuses on — the Day 4 mechanism,
  not a new one).
- **Graph facts for uploaded DMCs**: `index_package` runs `graph.sync`, so
  ingested uploads get DM nodes; a DMC absent from Neo4j yields zero rows
  from `facts()` (no error) — no new failure mode.
- **Known cwd trap acknowledged**: trace dir and `.vespa-manifest.json` are
  cwd-relative (backlog #10); `make demo` runs both processes from the repo
  root and the preflight asserts it. The backlog item itself stays open.
