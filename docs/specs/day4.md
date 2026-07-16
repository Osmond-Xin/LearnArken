# Day 4a SPEC — Dense Retrieval, Hybrid RRF, Rerank & Ablation (v0.4.0)

> **Authorship note (INV-6)**: the decision layer below was dictated by Yi Xin
> in the 2026-07-15 working session (in Chinese); AI transcribed and
> translated it with content unchanged. Full option analysis and the two
> adjudicated scope calls are in docs/discussions/day4.md (D5, D6). The
> Interfaces / Acceptance / Out-of-Scope sections are AI-drafted.
> **Status: Q1–Q5 + Q7 adjudicated by Yi Xin 2026-07-15 (transcribed below);
> Q6 (CI) re-opened pending his ruling.** Q1/Q2 were additionally settled
> *empirically* by a live probe — see "Probe findings" below.

## Goal (one sentence) — [HUMAN, transcribed]

Embed the Day 3 chunks with MiniMax, store and search them in Vespa, fuse the
dense path with the existing BM25 path via RRF, add a cross-encoder rerank
layer, and prove the whole thing with a four-row ablation table scored against
an expanded human-annotated golden set — tagged `v0.4.0`.

## Key Decisions — [HUMAN, transcribed from the 2026-07-15 session]

1. **MiniMax is the default embedding model — for the dense path only.**
   Rationale: an existing MiniMax subscription, so cost favours it over
   alternatives. Recorded limit (AI-verified, accepted): MiniMax serves dense
   embeddings and chat **only** — it does **not** serve SPLADE, ColBERT, or a
   reranker. Those models, when they arrive, come from elsewhere; "MiniMax as
   default" does not extend to them.
2. **Identifier protection (tokenizer protection) stays a first-class
   requirement.** The Day 3 identifier-preserving tokenizer is not replaced by
   anything on Day 4; it must survive into the Vespa schema (DMC / part-number
   fields matched whole, never shredded on `-`).
3. **Structure-aware chunking is the retrieval unit.** Day 3 delivered it and
   its eval table justified it; Day 4a builds on it, and does not re-litigate
   chunking.
4. **Hybrid retrieval with RRF fusion** (BM25 + dense).
5. **A rerank layer is required** — this is the point of the day, not an
   optional extra.
6. **An ablation table is the day's headline deliverable.**
7. **Golden set testing, expanded to ~80 queries.** The 32-query set cannot
   carry multi-row ablation conclusions (1 query = 3.1 percentage points).
   AI drafts candidate queries and candidate anchors **only**; Yi Xin selects
   and judges relevance — the retrieval-eval red line, unchanged from Day 3.
8. **SPLADE and ColBERT move to a new Day 4b node, gated on evidence.**
   Yi Xin's ruling (2026-07-15), overriding the session's initial proposal to
   include them today. Day 4a's ablation must first expose a *specific* gap;
   that gap is Day 4b's justification:
   - synonym/paraphrase queries still losing ⇒ SPLADE is warranted;
   - identifier / fine-grained queries still losing ⇒ ColBERT is warranted.
   Rationale: this is the project's own methodology (tutorial 04 §7 leverage
   ranking — *"消融表先证明现有上限不够，再立项"*), it keeps INV-8 (two
   calendar days per node) reachable, and "I decided against ColBERT with
   evidence" is a stronger interview story than "I stacked six techniques".
   The three prior records that put SPLADE/ColBERT out of slice
   (execution-plan 切片外, README Roadmap *Planned*, discussions/day3 D2) are
   amended from "Planned, indefinite" to "Day 4b, evidence-gated" — see Q7.
9. **AI-verified technical correction, accepted into the decision record**:
   SPLADE does **not** strengthen BM25 on identifiers. SPLADE weights sit on
   a BERT wordpiece vocabulary (~30k), so `DMC-LA100-A-29-10-00-00A-520A-A`
   is shredded into subword fragments and cannot be matched whole. SPLADE
   treats vocabulary mismatch (synonyms), not identifiers. It is therefore a
   *third lexical path* beside raw BM25, never a replacement for it — which
   is why decision 2 holds regardless of what Day 4b adds.

## Probe findings — [MEASURED against the live endpoint, 2026-07-15]

Q1 directed: search the docs first, then test with a small demo. Both done;
the probe answered Q1 and Q2 empirically. **These supersede the Deep Research
report's claims** (whose sources were weak) and close the
docs/local-services.md open item.

| Question | Measured answer |
| --- | --- |
| Endpoint shape | **MiniMax-native**, not OpenAI-compatible: `POST {base}/embeddings` with body `{model, texts: [...], type: "db"\|"query"}` |
| Response shape | top-level **`vectors`** array (not `data[].embedding`); success = `base_resp.status_code == 0` |
| Model | **`embo-01`** works (the chat model `MiniMax-M3` from `MINIMAX_MODEL_NAME` is a different thing — embeddings need their own model name) |
| Dimension | **1536** → Vespa `tensor<float>(x[1536])` |
| Auth | `Authorization: Bearer` **+ `X-Proxy-Token`** (both required; our base URL is a proxy) |
| `GroupId` | **not needed** — the proxy handles it (no such env var exists, and calls succeed without it) |
| **Q2: normalization** | **L2 norm = 1.000000 → pre-normalized** ⇒ Vespa `distance-metric: prenormalized-angular`, and cosine ≡ inner product |
| **Asymmetric encoding** | **CONFIRMED**: same text, `type=db` vs `type=query` → **cosine = 0.860** (not 1.0). `type` is a real asymmetric-encoding switch. Index with `db`, search with `query`; mixing them is a silent recall loss with no error. |

## Interfaces — [AI-DRAFTED, revised after the 2026-07-15 adjudication]

> **Architectural consequence of Q3 + Q4** (reranker in Python, BM25
> in-process): **Vespa is used only as a dense vector store**
> (`nearestNeighbor`). BM25, RRF fusion, and reranking all live in Python.
> This is Yi Xin's portability principle applied consistently — no retrieval
> logic is pushed into the engine, so the engine stays swappable. Two knock-on
> effects, both good for today: the Vespa schema collapses to "one embedding
> field + filter attributes" (no rank-profiles, no `global-phase`, no ONNX),
> which is a much smaller first Vespa deployment; and the earlier
> "RRF must live in `global-phase`" concern evaporates — RRF is Python code
> now, fusing two rank lists.

### Module layout

```text
src/learnarken/
  embedding/
    __init__.py     # embed(texts, mode: "db"|"query") -> list[Vector]
    minimax.py      # MiniMax client: Bearer + X-Proxy-Token, retry/backoff,
                    # native {texts, type} shape, `vectors` response
  chunking/
    semantic.py     # NEW (Q5): embedding-based boundary detection
  vespa/
    app/            # Vespa application package (checked in, deployable)
      services.xml
      schemas/chunk.sd
    store.py        # deploy + feed + nearestNeighbor query (idempotent, INV-2)
  retrieval/
    bm25.py         # (Day 3, unchanged — stays in-process per Q4)
    dense.py        # dense search via vespa/store.py
    hybrid.py       # RRF fusion (Python) + rerank orchestration
    rerank.py       # NEW (Q3): cross-encoder in Python
    evaluate.py     # (Day 3, extended: ablation modes + per-category breakdown)
eval/
  golden/day4.jsonl            # expanded human annotations (~80)
  golden/day4.candidates.jsonl # AI-drafted candidates (NOT authoritative)
docs/notes/day4-failure-cases.md  # dense-loses-to-BM25 analysis (plan requirement)
```

### Vespa schema — dense store only (dims/metric now MEASURED, not assumed)

```text
schema chunk {
  document chunk {
    field chunk_id type string { indexing: summary | attribute }
    field dmc type string {
      indexing: summary | attribute
      match: word            # decision 2: never shredded on '-'
    }
    field text type string { indexing: summary }   # returned, not indexed:
                                                   # BM25 is in-process (Q4)
    field embedding type tensor<float>(x[1536]) {  # measured: embo-01 → 1536
      indexing: attribute | index
      attribute { distance-metric: prenormalized-angular }  # measured: |v| = 1.0
    }
    # Day 3 metadata as attributes for filtering: applicability assertions,
    # hazard flags, graph hooks (dmRefs / ICN refs)
  }
  rank-profile dense { first-phase { expression: closeness(field, embedding) } }
}
```

- **No BM25 field, no rank-profile fusion, no ONNX** — consequence of Q3/Q4.
  Vespa's job is `nearestNeighbor` + attribute filtering, nothing else.
- **Feed is idempotent (INV-2)**: document id = Day 3's deterministic
  `chunk_id`, so re-feeding is an upsert; sharding stays behind
  `vespa/store.py`; no shared-memory shortcuts.
- **Exact vs approximate search** (AI proposal, needs a nod): at a few hundred
  chunks, run `nearestNeighbor` with `approximate: false` for the ablation, so
  the dense row is *exact* and the BM25-vs-dense comparison carries no ANN
  approximation confound. HNSW is then demonstrated separately as a documented
  recall-vs-exact check (learning goal + honest INV-7 note that HNSW's value
  cannot be shown at toy scale).

### CLI (extends the Day 1–3 tree; conventions inherited)

```text
learnarken index <package-dir> [--strategy structure] [--vespa-url URL] [--json]
learnarken search <package-dir> "<query>"
        [--mode bm25|dense|hybrid|hybrid-rerank]   # default: hybrid-rerank
        [-k N] [--applies-to KEY=VALUE ...] [--json]
learnarken eval ablation [--golden PATH] [--modes ...] [--seed N] [--json]
```

- `search --mode bm25` keeps the Day 3 in-process path working with no Vespa
  and no network (pending Q4).
- **Fail-closed (INV-4)**: if the MiniMax call fails or Vespa is unreachable,
  a dense/hybrid/rerank query **refuses with a clear error** — it never
  silently degrades to BM25 and reports the result as hybrid. Degradation, if
  wanted, must be explicit (`--fallback bm25`).

### Ablation table (the day's headline)

| Mode | Recall@5 | Recall@10 | MRR | nDCG@10 | p50 latency |
| --- | --- | --- | --- | --- | --- |
| bm25 (Day 3 baseline) | | | | | |
| dense (MiniMax) | | | | | |
| hybrid (BM25 + dense, RRF k=60) | | | | | |
| hybrid + rerank | | | | | |

Plus a **per-category breakdown** — this is what the expanded golden set buys,
and where the Day 4b gate is read:

| Mode | identifier | synonym/paraphrase | procedural | applicability | no-answer |
| --- | --- | --- | --- | --- | --- |

- Latency column carries an honest note: at this corpus size p50 is dominated
  by the MiniMax API round-trip, not by ANN vs brute force (INV-7).
- Metric roles are fixed in advance (red-team self-check): rerank must move
  **nDCG/MRR**, not Recall — a rerank row that raises Recall means the
  experiment is wired wrong (rerank generates no new candidates).

## Acceptance Criteria — [AI-assembled from execution-plan Day 4 + the
2026-07-15 decisions; pending approval]

- [ ] MiniMax embedding client works against the live endpoint: native
      `{texts, type}` shape, `vectors` response, `base_resp.status_code`
      checked, `X-Proxy-Token` sent, retry/backoff — and **`type=db` on index,
      `type=query` on search** (the measured asymmetry; a test asserts the two
      vectors differ)
- [ ] Vespa application package deploys from the repo; `learnarken index`
      feeds package-a + package-c chunks; re-feeding is idempotent
- [ ] Semantic chunking implemented (Q5); chunking table gains its third row
- [ ] Identifier queries still resolve exactly through the Vespa path
      (decision 2 regression: a DMC query returns its DM and not numeric
      look-alikes)
- [ ] All four modes runnable via `learnarken search --mode …`
- [ ] Golden set expanded to ~80 queries, human-annotated, versioned
- [ ] `learnarken eval ablation` reproducible (fixed seed, versioned golden
      set); four-row table + per-category breakdown generated
- [ ] Failure-case analysis written: ≥1 concrete identifier/part-number query
      where dense loses to BM25 → `docs/notes/day4-failure-cases.md`
- [ ] Ablation numbers survive the **heavy red team** (Producer → Challenger →
      Reviser until no new P0/P1); Challenger attacks the eval method itself
      (leakage? seed? sample size? multiple comparisons?)
- [ ] Yi Xin re-runs the red team's numbers personally (iron rule)
- [ ] Ablation table into README; **local integration run green** (Q6: CI is
      simplified — it runs the hermetic tests only and passes by default, so
      the verification bar for Day 4 is the local run); branch → PR → squash →
      tag `v0.4.0`, release notes carrying the numbers and stating they come
      from a local run
- [ ] Day 4b gate read from the per-category table and recorded (which of
      SPLADE / ColBERT is justified by which gap — or neither); Day 4b then
      continues under the same `v0.4.0` tag (Q7), subject to the INV-8 ceiling
- [ ] Day 4 re-evaluation checkpoint executed (execution-plan 🔁): minimal
      RDF/SPARQL graph query pulled back into the slice or kept Planned →
      decision + rationale into an ADR

## Explicitly Out of Scope (today) — [AI-DRAFTED, pending approval]

- **No SPLADE, no ColBERT** — Day 4b, evidence-gated (decision 8)
- **No answer generation, no LLM calls in the pipeline** (Day 5)
- No index persistence beyond Vespa itself; no BM25 re-homing into Vespa
  unless Q4 says so
- No Neo4j / triple export — still gated on the re-evaluation checkpoint
- No k1/b tuning (Day 3 established it as low-leverage; revisit only if the
  ablation says so)
- No query routing / classifier, no HyDE, no multi-query expansion
- No production latency claims — corpus is toy-scale (INV-7)

## Adjudicated decisions on Q1–Q7 — [HUMAN, transcribed from Yi Xin's
2026-07-15 reply]

1. **Q1 — approved, with an added step.** Search the web docs first, then test
   the embedding with a small demo before implementing. *Done in-session*: the
   docs search established the MiniMax-native shape; the probe then measured
   it live (see "Probe findings"). The client is written from the probe's
   output, not from the report.
2. **Q2 — settled by measurement.** Vectors are pre-normalized (|v| = 1.000),
   so `prenormalized-angular` it is, and cosine ≡ inner product.
3. **Q3 — (b), reranker in Python.** *Rationale (Yi Xin)*: hosting the
   reranker inside Vespa creates an architectural dependency on the engine and
   hurts portability/migratability. Keep it in the application layer.
4. **Q4 — (a), BM25 stays in-process.** Same rationale as Q3, applied
   consistently: retrieval logic stays in Python; Vespa is a dense vector
   store only.
   - *AI note on the objection I raised*: the "two engines" confound is
     narrower than I framed it. Vespa's own BM25 is now out of the picture
     entirely, so the ablation compares BM25(our tokenizer) against
     dense(MiniMax) over an identical chunk set — genuinely algorithm vs
     algorithm. The one residual confound is exact (rank-bm25) vs approximate
     (HNSW) candidate generation, which the `approximate: false` proposal
     above removes at this corpus size.
5. **Q5 — semantic chunking is IN, scoped per the AI recommendation**
   (approved 2026-07-15). Concretely:
   - `chunking/semantic.py` adds a third strategy; the **chunking table**
     becomes BM25-only × {structure, recursive, semantic}, directly comparable
     to Day 3's numbers;
   - the **retrieval-path ablation stays at one fixed chunking strategy** — no
     3 × 4 cross-ablation (12 cells would reopen the statistics problem D6
     just fixed);
   - **order**: run the chunking table first, then run the retrieval ablation
     on **whichever strategy wins it**, and state that choice explicitly in
     the README.
6. **Q6 — CI is simplified: local-green is the bar.** *Ruling (Yi Xin)*: the
   AI's three-option analysis was over-designed for what this is. This is a
   **learning project**; CI/CD is deliberately simplified. It only has to run
   locally — **CI passes by default**.
   *Implementation (minimal, no new infrastructure)*: tests that need MiniMax
   or Vespa are marked `@pytest.mark.integration` and skipped when the
   services are absent, so CI keeps running the existing hermetic Day 1–3
   tests and stays green. No GitHub Secrets, no mock/fixture layer, no Vespa
   service container.
   *One honest bookkeeping consequence*: CI green no longer means "Day 4 is
   verified" — the verification is the **local integration run**. So the Day 4
   acceptance criteria say "local integration run green" where earlier days
   said "CI green", and the release notes record that the ablation numbers
   come from a local run (INV-5 is satisfied by the documented reproduction
   command + versioned golden set, which is how any project with a paid API
   dependency does it).
7. **Q7 — Day 4b takes no separate tag.** Yi Xin will continue into Day 4b
   after Day 4a completes, keeping the overall schedule. *Consequence*: `v0.4.0`
   covers both; Day 5–10 do not shift; README Roadmap moves SPLADE/ColBERT
   from *Planned* to "Day 4b, evidence-gated"; execution-plan.md gains the
   4a/4b split (edits pending approval).
   - *AI note (INV-8 guard)*: if 4a + 4b together exceed the two-calendar-day
     ceiling, INV-8 says cut and ship — tag `v0.4.0` with 4a's four-row
     ablation and push 4b's unfinished part to the Roadmap, rather than let
     the tag slip.

## Golden set — location and findings from drafting the candidates
[AI-DRAFTED 2026-07-15; three findings need Yi Xin's ruling]

**Location** (the answer to "把 golden set 的位置给我"):

| File | What it is | Who owns it |
| --- | --- | --- |
| `eval/golden/day3.jsonl` | the existing **32 human-annotated** queries — reused as-is, not re-annotated | Yi Xin (done) |
| **`eval/golden/day4.candidates.jsonl`** | **50 new AI-drafted candidates** — every line `"ai_suggested": true`; anchors are *suggestions, not judgments* | AI drafts · **Yi Xin judges** |
| `eval/golden/day4.jsonl` | the Day 4 authoritative set = the 32 + whichever of the 50 Yi Xin accepts (~82) | **Yi Xin only** (red line) |

All 50 candidate anchors were validated against real chunker output
(`learnarken chunk` on package-a + package-c): every non-empty anchor points at
a chunk that actually exists. 10 of the 50 are deliberate zero-hit cases.

Proposed distribution after merge (~82):

| Category | Day 3 | new | total | why it matters |
| --- | --- | --- | --- | --- |
| paraphrase | **0** | 12 | 12 | **the gap** — reads the SPLADE/dense gate |
| procedural | 8 | 4 | 12 | |
| warning | 5 | 4 | 9 | |
| fault_isolation | 3 | 5 | 8 | |
| identifier_perturbation | 1 | 7 | 8 | **reads the ColBERT/BM25 gate** |
| no_answer | 5 | 3 | 8 | refusal / zero-hit |
| identifier | 5 | 2 | 7 | |
| descriptive | 2 | 5 | 7 | |
| applicability | 2 | 4 | 6 | |
| cross_reference | 1 | 4 | 5 | |

### Finding 1 — the whole IPD is ONE chunk, so part-number discrimination is untestable

All 7 existing identifier queries (Q007–Q010, Q019, Q024, Q029) resolve to the
*same* anchor: `/dmodule/content/illustratedPartsCatalog`. The structure-aware
chunker emits one `ipd` chunk per DM, so `LA-29-4711-1` (pump) and
`LA-29-4711-9` (gasket) — one digit apart — live in the same chunk and cannot
be told apart at chunk granularity.

*Workaround used in the candidates*: the `identifier_perturbation` category is
built from **non-existent** near-misses (`LA-29-4711-5`, `ICN-…-001-02`, info
code `942`) where the correct answer is **zero hits**. This still delivers the
execution plan's required "dense loses to BM25 on identifiers" case — BM25 with
the Day 3 tokenizer returns nothing (correct refusal) while dense is expected
to return the IPD chunk at high similarity, because a fake part number *looks
like* a part number. Arguably a sharper demo than intra-IPD ranking.

***Question for Yi Xin***: is IPD-as-one-chunk a chunking defect? Each
`catalogSeqNumber` is a natural structural boundary — exactly what
structure-aware chunking exists to find — and a real IPD has hundreds of parts,
where one chunk would be absurd. But fixing it is Day 3 scope and would move
Day 3's published numbers. *AI recommendation:* **do not fix it in Day 4a**;
record it as a finding and let the ablation's identifier row decide whether it
earns a Day 4b/Roadmap item. (Scope discipline: the SPEC doesn't say to do it.)

### Finding 2 — applicability lives in metadata, not in chunk text

The applicability displayText (e.g. *"LA100, serial numbers 0001–0050
(lead-acid battery installation)"*) sits in `dmStatus/applic`, which the
chunker carries as **chunk metadata**, not chunk `text`. So *"which serial
numbers use the lead-acid battery?"* is unanswerable by text retrieval — no
chunk's text contains it.

*Handled in the candidates*: all 4 new `applicability` candidates are grounded
in **content text** only (the variant-B / friction-collar prose, which really
is in the para). ***Question***: should applicability displayText be
concatenated into the indexed text? It would make metadata questions
answerable, but it changes what gets embedded and perturbs the Day 3 baseline —
the same trade-off already declined for "concatenate DMC into chunk text"
(docs/research/day4-unknowns.md §4.6). *AI recommendation:* no — keep
applicability a **filter**, not a retrieval target.

### Finding 3 — the existing 32 carry no `category` field

`day3.candidates.jsonl` had `category`; the annotated `day3.jsonl` dropped it.
The per-category table — the thing that reads the Day 4b gate — needs all ~82
categorized. AI's proposed categorization of the existing 32 is the "Day 3"
column above; ***it needs Yi Xin's confirmation*** on merge, since a
miscategorized query mis-reads the gate.

## The 3 tutorial concepts to verify during implementation — [HUMAN picks;
AI candidates below from docs/research/day4-unknowns.md §6]

*Candidates, pending Yi Xin's selection:*

### Candidate 1. Asymmetric encoding (`type: db` vs `type: query`) — now MEASURED

- **Means**: many instruction-tuned embedding APIs encode indexed documents
  and user queries differently; MiniMax expresses this as `type="db"` vs
  `type="query"`. **Measured on our endpoint: the same text under the two
  modes gives cosine 0.860, not 1.0 — the switch is real.** Getting it wrong
  does not error; it silently degrades recall.
- **Verify during implementation**: a unit test asserts `embed(x, "db") !=
  embed(x, "query")`; an integration check asserts the index path uses `db`
  and the search path uses `query`. Worth keeping as a concept even though the
  fact is settled — the *lesson* is that a 30-line probe converted a weak
  documentation claim into a measured constraint.

### Candidate 2. RRF as rank-based voting, and why not weighted sums

- **Means** (tutorial 04 §4): BM25 is unbounded, cosine is [-1,1] — the
  scales are incommensurable, so `0.7*dense + 0.3*bm25` is a category error.
  RRF uses only ranks: `Σ 1/(60+rank)`; k=60 is the 2009 paper's empirical
  constant and is not a tuning knob.
- **Verify**: hand-work a tiny two-path, three-document example, compute RRF
  by hand, assert the implementation matches. Note that after the Q3/Q4
  rulings our RRF is **Python fusing two rank lists** — the "RRF must live in
  Vespa's `global-phase`" rule still holds for engine-internal fusion, it
  simply no longer applies to our architecture.

### Candidate 3. Stage-to-metric correspondence in the ablation

- **Means**: the four rows are one pipeline's switch combinations, not four
  parallel systems. Recall@k judges the recall stage ("is the fish in the
  net"); nDCG/MRR judge the ranking stage ("is it at the top").
- **Verify**: read the ablation with the pre-committed rule — rerank must move
  nDCG/MRR while leaving Recall flat. If rerank raises Recall, the experiment
  is wired wrong. This rule is the first line of defence when the heavy red
  team attacks the eval method.
