# SPEC — Day 5: RAG with Citations (`v0.5.0`) ⚑ heavy red team

> Decision layer transcribed from Yi Xin's instructions (2026-07-16 session);
> Interfaces / Acceptance / Out-of-Scope sections are **AI-drafted, pending
> approval**. Open questions Q1–Q4 below await adjudication before
> implementation starts.

## Goal (one sentence) — [HUMAN, transcribed]

Ship `learnarken query "<question>"`: grounded question answering over the
indexed corpus where every answer carries chunk ID + DMC + XPath (traceable
to source text), unanswerable questions get a fixed refusal placeholder
("I don't know" / "我不知道" / "没有在系统中找到答案" class), the answer LLM
is **MiniMax-M3**, and retrieval combines the Vespa vector store **with graph
queries** (graph sync included) — tagged `v0.5.0`.

## Key Decisions — [HUMAN, transcribed from the 2026-07-16 instructions]

1. **New CLI subcommand `query`** — single positional argument: the question
   text.
2. **Answer LLM is MiniMax-M3** (chat). Config channel: the four
   `MINIMAX_*` variables previously documented in docs/local-services.md
   (values available; the reference client pattern — Bearer +
   `X-Proxy-Token`, retry/backoff — is FollowTheBig's).
   *Recorded deviation*: execution-plan Day 5 said "Claude API 回答生成";
   this ruling supersedes it. *Recorded history*: MiniMax was removed from
   the **embedding** architecture (Day 4 Part 2 ruling 5); that ruling does
   not cover chat/generation, which is what M3 does here.
3. **Grounded answers, mandatory trace fields**: every answer must include
   chunk ID + DMC + XPath so it can be traced back to the original text.
4. **Fail-closed refusal**: when no answer is found in the system, reply
   with the generic placeholder — never fabricate (INV-4).
5. **Tests must include**: golden-set questions with their expected
   answers and chunk-ID verification, AND no-answer questions verified to
   produce the refusal placeholder.
6. **Graph sync + combined querying**: indexing also syncs the graph
   (Neo4j), and `query` combines Vespa vector retrieval with graph
   queries — not vector-only. (Scope note: this pulls the minimal graph
   slice forward from Day 9; amends ADR-0002 — see Q1.)
7. **After implementation: red-team review** (the automatic gate; Day 5 is
   a ⚑ heavy node per the execution plan).

## Open Questions — [adjudicated by Yi Xin, 2026-07-16 session]

- **Q1 — Graph integration shape: (a)+(b) approved** — index-time graph
  sync (DM-level nodes, DM→DM dmRefs edges, DM→ICN edges, idempotent
  upserts per INV-2) + **interface ③ context injection** (graph facts of
  retrieved DMs as a structured list in the prompt). Graph-neighbor
  retrieval expansion NOT taken; multi-hop tools stay at Day 7/9.
  ADR-0002 amended accordingly.
- **Q2 — Strict two-outcome refusal**: only "cited answer" or "placeholder
  refusal"; no graded low-confidence band. (The DR report's graceful-
  degradation alternative was considered and declined — INV-4 cleanliness
  and a smaller Day 8 attack surface.)
- **Q3 — Answer language: fixed English** (consistent with outward-facing
  artifacts; the evidence corpus is English synthetic XML, avoiding
  cross-lingual citation-alignment noise). Refusal placeholder is English.
- **Q4 — `query` runs on `hybrid-rerank`** (the reranker score doubles as
  the refusal-threshold signal), `--mode` override retained.

## Probe findings — [MEASURED against the live chat endpoint, 2026-07-16]

| | |
| --- | --- |
| Shape | **OpenAI-compatible** `/chat/completions` (`choices[0].message.content`) — unlike the retired embeddings endpoint, which was MiniMax-native |
| Success signal | HTTP 200 **and** `base_resp.status_code == 0` (both checked) |
| Auth | `Authorization: Bearer` **and** `X-Proxy-Token`, as documented |
| Reasoning | **M3 always emits a `<think>…</think>` prefix in `content`** — even at temperature 0 and with `response_format` set; there is no separate reasoning field (`message` keys: content, role). The client MUST strip it before parsing |
| Structured output | `response_format: {"type": "json_object"}` accepted; post-`</think>` content is clean parseable JSON (verified) |
| Usage | `usage.completion_tokens_details.reasoning_tokens` reported — recorded in traces |

## Interfaces — [AI-drafted, pending approval]

- `learnarken query "<question>" [--package … --k 5 --mode hybrid-rerank
  --json]` → human-readable answer with inline `[chunk_id]` citations and a
  source table (chunk_id, DMC, XPath); `--json` emits the full answer
  object. Exit codes: 0 answered, 3 refused (placeholder), 1 fail-closed
  error (services/LLM unavailable — refuse, never degrade to model-internal
  knowledge), 2 not a package.
- Answer object (Pydantic): `question, answer_text, refused: bool,
  citations: [{chunk_id, dmc, source_path}], graph_facts: […], trace_id,
  model, usage`. **DMC/XPath are backfilled from chunk metadata by the
  system, never echoed by the LLM** (citation-drift defense: the LLM only
  ever emits short chunk ids, validated ⊆ retrieved set; violation ⇒
  fail-closed refusal).
- Answer trace JSON per query (trace_id-named file): retrieval span (mode,
  candidates + scores), rerank span, LLM span (exact payload, model id,
  temperature), generation span (raw output, parsed citations), graph span
  (facts injected). Location: `eval/traces/` (git-ignored), format
  versioned.
- Prompt contract: system instructions (role, evidence-only, refusal code) /
  evidence zone (chunks wrapped in `<document id="…">` with random-delimiter
  spotlighting) / citation format contract (structured output:
  `is_answerable`, `answer`, `citations[]`).
- Refusal defense-in-depth: (1) reranker top-1 score below a **measured**
  threshold (from golden-set score distributions, recorded in an artifact)
  ⇒ short-circuit placeholder without calling the LLM; (2) LLM
  `is_answerable=false` ⇒ placeholder; (3) citation validation failure ⇒
  placeholder. All three logged in the trace with which gate fired.
- MiniMax-M3 client: probe the live chat endpoint with a small demo first
  (Day 4 Q1 precedent — the embeddings endpoint was *not* OpenAI-shaped;
  do not assume chat is). Env loading: repo-root `.env` only, `MINIMAX_*`
  allowlist, https-scheme check (red-team day4 #7's hardening applied from
  the start).

## Acceptance Criteria — [AI-drafted, pending approval]

- [ ] `learnarken query` end-to-end on the indexed corpus; answer carries
      chunk ID + DMC + XPath for every claim (decision 3)
- [ ] No-answer questions (golden set traps) return the placeholder; exit
      code distinguishes refusal from answer (decision 4)
- [ ] Graph sync: `learnarken index` populates Neo4j idempotently; `query`
      injects graph facts (decision 6, shape per Q1 ruling)
- [ ] Refusal threshold measured from golden-set score distributions,
      recorded as an artifact (INV-5) — not hand-picked
- [ ] Tests: golden-set questions → citation chunk-ids verified against
      golden relevant sets; no-answer questions → placeholder verified;
      citation-validation failure path tested (mocked LLM); live-LLM tests
      skip-marked (decision 5)
- [ ] Answer trace JSON per query, all five spans, reproducible location
- [ ] Citation coverage + groundedness mini-eval; **Yi Xin hand-checks 20
      samples** (execution-plan)
- [ ] Heavy red team on the answer path (⚑), findings → docs/reviews/day5.md
- [ ] Branch → PR → squash → tag `v0.5.0`

## Explicitly Out of Scope (today) — [AI-drafted, pending approval]

- No multi-hop graph agent tools (interface ① — Day 7/9); no community
  summaries / GraphRAG-style global answers
- No API server / web demo (Day 6)
- No streaming output; no conversation memory / multi-turn
- No prompt-injection *evaluation* (Day 8 attacks it; today only the cheap
  spotlighting defense is installed)
- No answer caching, no query rewriting / HyDE / multi-query
