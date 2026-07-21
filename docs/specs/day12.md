# SPEC — Day 12: Multimodal Ingest & QA (`v1.2.0`)

> Decision layer **AI-summarized from Yi Xin's session directives (2026-07-20)
> + the already-adjudicated Day 11–13 planning decision**
> ([docs/discussions/day11-13-planning.md](../discussions/day11-13-planning.md)
> Decision 2), **pending human review** — Yi Xin's instruction this session was
> "我给你信息，你来总结写，不是完全我写". Provenance is marked per item:
> `[HUMAN, transcribed]` = a Yi Xin ruling this session or an adjudicated
> planning decision; `[AI-drafted, pending approval]` = elaboration; `[OPEN —
> needs Yi Xin]` = a decision-layer point not yet ruled, drafted with the scan's
> proposed position for Yi Xin to confirm or overturn. Nothing in the decision
> layer is AI-invented; the open items are flagged, not silently defaulted.
>
> **Daily-cycle note.** Step 1 研→读→扫 is complete **before** this SPEC: 研
> ([day12-多模态 RAG 技术调研](../gemini-deepresearch/day12-%E5%A4%9A%E6%A8%A1%E6%80%81%20RAG%20%E6%8A%80%E6%9C%AF%E8%B0%83%E7%A0%94.md),
> archived), 扫 ([docs/research/day12-unknowns.md](../research/day12-unknowns.md),
> T1–T8), tutorial [15-multimodal-rag.md](../tutorials/15-multimodal-rag.md).
> The scan's 裁法 for T1/T2/T3/T6/T7 feed the elaboration layer; T4 (VLM
> provider) is resolved by the probe finding below; T5 (resolution) and T8
> (reporting) are pinned into Acceptance.
>
> **Probe finding — VLM channel (2026-07-20, this session, feeds Decision 1).**
> The stack's LLM is `MiniMax-M3` (text) via the proxy
> `mini.niagaradataanalyst.com/v1` ([minimax.py](../../src/learnarken/llm/minimax.py)).
> The proxy's `/v1/models` lists **only text models** (M2–M3), no named VL model.
> **But** a live probe showed the proxy **accepts the OpenAI multimodal
> `image_url` content format** and returns real vision output: a rendered image
> of the token `AR7429` was read back **byte-exact ("AR7429") on 2 of 3 runs**
> (the third returned empty) — a text-only prompt cannot produce that string, so
> the backend genuinely reads pixels. **Two behaviors matter for the design:**
> (i) **no new provider/key is required** — the existing proxy, already inside
> the `demo_guard` fence, is the vision channel (resolves T4 option (a));
> (ii) the channel is **unstable at temperature 0** — featureless images return
> "I don't see an image attached", and even readable images intermittently
> return empty. This validates the scan's "不知道自己不知道" red-team point and
> **forces a fail-closed + retry contract on every VLM call** (see Key
> Decision 1 and Interfaces §1). Probe artifacts are reproducible via the T5
> small-test-set harness.
>
> **Constitutional note.** INV-1 governs synthetic-only data (the ICN
> illustrations are **synthetic SVG**, never real S1000D graphics — the red line
> is unchanged by the new modality). INV-4 governs fail-closed (out-of-description
> questions ⇒ refuse; empty/"no image" VLM responses ⇒ refuse-or-retry, never a
> hallucinated description passed through). INV-5 governs determinism (the
> resolution constant and any threshold must have a measured provenance, not a
> guessed value). INV-7 governs the toy-scale honesty declaration (description
> quality measured on synthetic wireframes does **not** extrapolate to real
> scans — the "synthetic-data privilege" disclosure, scan T2). INV-8 governs
> slippage (the query-time second-look is additive to ingest-time describe; if
> the day overruns, second-look is the first slice cut back, ingest-describe is
> not — but note Yi Xin has ruled second-look **in scope this day**, see
> Decision 2).

## Goal (one sentence) — [HUMAN, transcribed from planning Decision 2 + 2026-07-20 directives]

Bring **synthetic ICN illustrations into the retrieval index** via
**describe-then-index** — a VLM produces a **controlled, schema-constrained
structured description** of each synthetic figure (temperature 0, structured
output, per-image independent call), cross-validated against the figure's
declared hotspot set and bound to the image by checksum — so that image content
becomes retrievable and **auditable through citations** alongside the existing
text corpus; **additionally implement query-time "second-look" as a multi-sample
consensus re-read** (multiple VLM calls on the actual image, accepted only when
the samples converge and agree with the deterministic anchors — because a single
read of the unreliable channel is not trusted); and **fail closed** — a question
that falls outside what the description/second-look can reliably support is
**refused, not guessed** — tagged `v1.2.0`.

## Key Decisions

1. **VLM provider = reuse the existing MiniMax proxy; no new key.**
   `[HUMAN, transcribed — Yi Xin "首先看 MiniMax 是否有我们需要的服务", resolved
   by the 2026-07-20 probe finding above.]` The vision channel is the existing
   `image_url`-capable proxy endpoint, already inside the `demo_guard` fence —
   planning Decision 2's "现有围栏" path (T4 option (a)). **Every VLM call is
   temperature 0, structured output, one image per call** (scan T4, DR 陷阱一).
   Because the channel is empirically **unstable** (probe finding), each call has
   a **fail-closed + bounded-retry contract** with **two distinct stop
   conditions**: (i) an empty / "no image" / schema-invalid response is retried
   up to a fixed cap (the flaky-channel case), and on exhaustion the figure is
   **marked undescribed** (ingest) or the answer **refuses** (query); (ii) a
   **subscription `429`** from upstream is the **terminal ceiling** — Yi Xin runs
   a **subscription (flat), not metered per-token**, so there is **no artificial
   per-call/per-request budget cap**; attempts continue freely until a `429`,
   which is then a clean **fail-closed stop** (mark-undescribed / refuse), never a
   fabricated description (INV-4). This replaces Day 10's token-budget rationale
   for the VLM path: the fence's job here is to turn a `429` into a fail-closed
   stop, not to impose a synthetic quota.

2. **Second-look = multi-sample consensus re-read (NOT a single call) — IS
   implemented this day.** `[HUMAN, transcribed — Yi Xin 2026-07-20, explicitly
   OVERRIDING the scan's Roadmap recommendation AND ruling that a single call is
   insufficient.]` At query time, when the ingest-time description does not
   confidently cover the question, the agent re-reads the **actual image scoped
   to that question** — but because the MiniMax channel is empirically unreliable
   (probe: `AR7429` dropped a char once, empty 1/3), **a single VLM read is not
   trusted**. Second-look issues **multiple independent VLM calls and accepts a
   reading only when the samples reach consensus**, cross-checked ("匹配合成")
   against the deterministic anchors (SVG `<text>` white-list + declared hotspot
   set, scan T2). The loop **samples until convergence** (agreement threshold met
   → early stop) **or** a divergence/no-consensus give-up, **or** upstream `429`
   (Decision 1 ii — subscription-bounded, no artificial per-call cap). **Only a
   converged, anchor-corroborated reading is returned; disagreement /
   non-convergence / `429` ⇒ G15 refuse** (Decision 7) — never one arbitrarily
   chosen read, never a fabrication. This is inference-time self-consistency: the
   "repeat-test an unreliable generator, report only the robust result" discipline
   (Day 8) applied to reading, not just evaluation.

3. **Image-text conflict: mechanical detection yes, semantic detection no; trap
   acceptance downgraded.** `[HUMAN position from planning Decision 2 + scan T1;
   trap-pass wording adopted below]` (a) **Mechanical conflict** — hotspot-number
   set diff between the VLM description and the XML-declared hotspots, computed
   deterministically at ingest; a mismatch **degrades that figure** (not silently
   accepted). (b) **Semantic conflict** (figure says A, prose says B) — **not
   auto-detected at toy scale**; the conflict-trap acceptance is **downgraded to
   "the system does not force-answer one side"** (refuse, or present both sources)
   rather than "detects the conflict". Claiming (b) is "conflict detection" would
   be a false EVIDENCE.md claim (scan T1 red line). **This downgrade is a
   decision-layer item, stated explicitly, not buried in elaboration.** Trap-pass
   rule (former [OPEN-C], **RULED — Yi Xin "按照你来" 2026-07-20**): *on a
   figure-vs-prose conflict trap, the answer is a pass iff the system refuses OR
   presents both sources without asserting one as correct; asserting either
   single source is a fail.*

4. **Minimum usable resolution is measured, not hardcoded.** `[HUMAN, transcribed
   — scan T5; INV-5's first multimodal application]` The render resolution
   constant is set from a **10-image small test set** (resolution × hotspot-read
   accuracy, plus the probe's instability rate). The chosen value is "the lowest
   tier where hotspot IDs read back complete", and the test data + the number's
   provenance go into notes — no pulled-from-air config constant.

5. **INV-1 red line unchanged: synthetic SVG illustrations only.** `[HUMAN,
   transcribed — planning Decision 2]` ICN figures are **self-authored synthetic
   SVG**, rasterized to PNG for the VLM; never real S1000D graphics, never copied
   from `samples/`. ASCII-only annotations (part/hotspot IDs already are) so
   rendering is font-independent and checksum-stable (scan T3); checksum is
   computed on the rasterized PNG.

6. **Describe-then-index (offline), maximum reuse; no CLIP/ColPali, no父子分块.**
   `[HUMAN, transcribed — planning Decision 2 + Yi Xin 2026-07-20 + scan T6]`
   An **offline** ingest pipeline: the VLM extracts a **controlled structured
   description** — **部件清单 (parts list), Hotspot 标号 (hotspot ids), 安全警告
   (safety warnings)** — as **Pydantic-schema-constrained JSON**, and the image
   file's **SHA-256** checksum binds the description to the exact image bytes.
   Each description is indexed **at chunk level into the Vespa vector store**
   (the existing dense index) as a new chunk `type="figure"`; when a question
   touches figure detail, RAG recalls the ICN description chunk and the LLM emits
   a **graph/figure citation of the form `[ICN-LA100-29-001-01, Hotspot 02]`**.
   The Day 5 refusal+trace, Day 2 L3 ICN existence check, Day 8 trap method, and
   Day 10 fence are all reused. CLIP global-pooling and ColPali page-level
   retrieval stay Planned (planning 理由; page-granularity conflicts with the
   chunk-precise citation red line). Parent-child chunking is Roadmap (scan T6).

7. **Visual fail-closed = new gate G15 (视觉超纲拒答闸).** `[HUMAN, transcribed —
   Yi Xin 2026-07-20; naming collision RULED "改成新的" → G15]` If a question
   asks for an **out-of-scope visual detail the description does not cover**, the
   system **must trigger a G15 refusal — never look-and-fabricate**. Reconciled
   with second-look (Decision 2): the order is **described-content → second-look
   on the real image → if still unsupported (or `429`/exhaustion), G15 refuse**.
   **Naming — RULED:** the interview "拦截塔" catalog already uses G4 for the
   **ingest-time four-layer L0–L3 validation** and runs through **G14
   (demo_guard 三闸)**; to avoid collision this Day 12 **answer-layer visual-
   refusal gate takes the next free number G15**, wired as refusal reason
   `figure-out-of-description`. (Tutorial 13's 拦截塔 catalog gains the G15 row.)

### Open items — status after the 2026-07-20 rulings

- **[OPEN-A] second-look budget → RULED (Yi Xin 2026-07-20)**: no artificial
  cap; retry/continue until upstream `429` (subscription-bounded). Folded into
  Decision 1(ii) / Decision 2.
- **[OPEN-B] figure count → RULED (Yi Xin 2026-07-20)**: **2–3** synthetic
  hotspot-bearing ICN SVGs.
- **Corpus/asset defaults 1–3 → "按你默认走" (Yi Xin 2026-07-20)** — folded into
  the elaboration layer, AI-drafted:
  - **(1) Hotspot authority = dual-write**: the SVG hand-draws numbered callouts
    (part-number markers); the DM XML declares the **canonical hotspot set** (via
    `<hotspot>` children of `<graphic>`) as the ground truth the mechanical diff
    validates against — keeping the check in the L3 cross-file-reference lineage.
    All synthetic (INV-1). No hotspot markup exists in the corpus today, so this
    is authored fresh.
  - **(2) Upgrade the existing ICN in place**: `ICN-LA100-29-001-01` (already a
    hydraulic-pump placeholder wired to
    `DMC-LA100-A-29-10-00-00A-941A-D` via `<graphic infoEntityIdent=…/>`, and the
    exact id in Yi Xin's citation example) gains hotspots + part numbers; **1–2
    more** ICNs are authored on other procedural DMs → 2–3 total.
    ≤3 keeps image chunks from swamping the 43-chunk pool (scan T6).
- **[OPEN-C] conflict-trap pass rule → RULED (Yi Xin "按照你来" 2026-07-20)**:
  adopted into Decision 3 (refuse-or-both, never force one side).

---

## Interfaces — [AI-drafted, pending approval]

### 1. `src/learnarken/multimodal/vlm.py` — VLM description client

- `describe_figure(png_bytes: bytes, declared_hotspots: set[str], *, question:
  str | None = None) -> FigureDescription` where `FigureDescription` is a
  **Pydantic-schema-constrained** model (Decision 6): `{summary, parts:
  list[Part], hotspots: list[Hotspot], safety_warnings: list[str], reads_text:
  list[str], refused: bool}` with `Part = {part_number, name}` (**部件清单**),
  `Hotspot = {id, label}` (**Hotspot 标号**), and `safety_warnings` (**安全警告**).
- Reuses the `minimax.py` transport (Bearer + `X-Proxy-Token`, `<think>` strip,
  `base_resp.status_code==0` success), extended to the **multimodal `content`
  array** (`[{type:text,...},{type:image_url,image_url:{url:data:image/png;base64,…}}]`).
- **Structured output**: `response_format` JSON object + an explicit schema in
  the prompt; **enum-closed** hotspot `id` candidates = the declared set, so the
  model cannot invent hotspot numbers (scan must-master #2; the enum is the
  first hallucination lever).
- **Fail-closed + two stop conditions (Decision 1)**: (i) empty / "no image" /
  schema-invalid ⇒ retry up to `VLM_MAX_RETRIES` (fixed, flaky-channel case);
  (ii) upstream HTTP **`429`** ⇒ **terminal ceiling, no retry** (subscription
  limit reached). On either terminal condition: ingest raises `VLMUnavailable`
  (figure marked undescribed) or query returns `refused=True` → G15 refuse.
  Temperature 0, one image per call.

### 2. `src/learnarken/multimodal/figures.py` — declarative ICN spec → SVG + PNG

- **Elaboration revision (2026-07-20): render via Pillow from a shared figure
  spec, not cairosvg.** cairosvg needs system `libcairo` (absent here) and only
  *mitigates* cross-env determinism (scan T3); **Pillow** is already available
  and deterministic (bundled bitmap font, no system fonts). A single declarative
  `FigureSpec` (shapes + hotspots[id,label,part_number] + safety_warnings +
  title) is the **source of truth**, emitting **both** the SVG (the DM-referenced
  S1000D artifact + `<text>` anchor source) **and** the PNG (`to_png`, Pillow,
  the VLM raster) — no SVG↔PNG divergence, byte-stable render, zero rasterizer
  system dep. `pillow` is added as an explicit project dependency (was transitive).
- `to_svg(spec) -> str`, `to_png(spec, *, scale) -> bytes`,
  `declared_hotspots(spec) -> set[str]`, `text_whitelist(spec) -> set[str]`.
  `scale` (the resolution knob, replacing `dpi`) is the **measured constant** from
  the T5 small test set (`eval/results/day12-resolution.json`, Decision 4).
- ASCII-only labels (scan T3); the committed PNG bytes are the SHA-256 bind key
  (determinism comes from committing canonical PNGs + Pillow stability, not from
  cross-env SVG rasterization — the honest T3 position).

### 3. `src/learnarken/multimodal/ingest.py` — describe-then-index + mechanical conflict

- For each synthetic ICN figure: render → **SHA-256 checksum** → `describe_figure`
  → **hotspot-set diff** (`description.hotspots` ids vs the **DM XML `<hotspot>`
  canonical set**, default 1(c); the SVG `<text>` white-list is a second
  corroborating anchor). Match ⇒ emit an **image-description chunk** indexed
  **at chunk level into
  the Vespa vector store** (`type="figure"`, metadata `{icn_id, sha256, hotspots,
  parts, safety_warnings, source_dm}`). **Mismatch ⇒ figure degraded** (chunk
  withheld or flagged; recorded in the manifest — Decision 3a).
- The figure chunk joins the **existing `learnarken index` → Vespa pipeline**
  (same ingest, INV-2 idempotent; manifest records the SHA-256 for drift/T7).
  The SHA-256 binds the indexed description to the exact image bytes (Decision 6).
- Also extract SVG `<text>` nodes deterministically (lxml) as a **free
  white-list anchor** cross-check (scan T2) — near-zero cost, second guard on
  the description's `reads_text`.

### 4. `src/learnarken/multimodal/second_look.py` — query-time targeted re-look

- `second_look(icn_id, question) -> ConsensusReading | Refusal`: loads the figure
  by `icn_id` and runs a **multi-sample consensus loop** (Decision 2), triggered
  **only when the ingest-time description does not cover the question** (the
  coverage check — a rule-based trigger: the question names a hotspot/part id or
  visual attribute absent from the retrieved description's fields, falling back
  to the answer layer's existing insufficiency signal; not always-on).
- **Consensus loop**: repeatedly call `describe_figure(png, hotspots,
  question=…)`; collect the per-call structured reads. Empty / "no image" /
  schema-invalid reads (flaky-channel case) **do not count toward consensus** but
  consume an attempt. **Accept a field only when it agrees across ≥ `VLM_CONSENSUS_K`
  successful reads** AND is corroborated by the deterministic anchors (SVG
  `<text>` white-list / declared hotspot set). Early-stop on agreement.
- **Stop conditions**: (i) consensus reached → return `ConsensusReading`
  (synthesized from the agreeing reads, with an `agreement` count for the trace);
  (ii) `VLM_MAX_SAMPLES` reached without consensus, or the reads **diverge**
  (no majority) → **G15 refuse**; (iii) upstream `429` → **G15 refuse**
  (Decision 1 ii). Never returns one arbitrarily chosen read.
- Fail-closed reason on every non-consensus path: `refuse("figure-out-of-description")`
  (Decision 7) — the visual info is treated as *not reliably obtained*, never
  guessed. `VLM_CONSENSUS_K` / `VLM_MAX_SAMPLES` are configured constants; their
  values are set from the T5 small-test-set instability rate (INV-5 provenance —
  the same data that fixes `dpi` also tells us how many samples convergence needs).

### 5. Citation / trace / machine-readable schema extension (scan T7)

- Figure citation string in answers: **`[ICN-LA100-29-001-01, Hotspot 02]`**
  (icn id + hotspot number) — Decision 6. Figure evidence in the answer trace =
  `{icn_id, sha256, hotspots_matched, second_look: bool}`; `EVIDENCE.md`,
  `llms.txt`, and citation rendering gain the `figure` evidence type. The
  "stranger locates any number in 5 min" (Day 9) bar holds for figures: **the
  figure's reproduction command** (re-render + re-describe + SHA-256 + diff) goes
  into `EVIDENCE.md` so the evidence chain does not break at the image.

### 6. Synthetic assets & evaluation

- Synthetic ICN SVGs (default 2): **upgrade the existing
  `samples/package-a/icn/ICN-LA100-29-001-01.svg`** with hotspot / part-number
  markers + author **1–2 more** on other procedural DMs → 2–3 total (Decision 5,
  default 2). Each DM's XML gains the `<hotspot>` canonical set (default 1);
  rasterized to PNG; ASCII annotations; declared hotspot ids match the DM XML.
- `eval/golden/day12-multimodal.jsonl` — **8–10** items, **three classes
  (~3 each)**: **图中有答案 (answer in the figure) / 文图冲突 (text-vs-figure
  conflict trap) / 图中无答案陷阱 (no-answer-in-figure trap)**. Human-labeled
  (which field answers, whether to refuse — the retrieval-eval red line does not
  change with modality, scan T8). Small-n reporting: **scores k/n, not
  percentages**; classes with n<3 italicized *indicative* (Day 4 precedent).
- `eval/results/day12-resolution.json` — the T5 10-image small test set:
  resolution × hotspot-read accuracy × instability rate; provenance of **both**
  the `dpi` constant (Decision 4) **and** the consensus constants
  `VLM_CONSENSUS_K` / `VLM_MAX_SAMPLES` (Decision 2 — how many samples
  convergence actually needs at the measured instability rate), INV-5.
- Old-golden full regression re-run (Day 4 harness) — image chunks must not
  drop existing text metrics; result reported either way (scan T6, honesty).

### 7. `tests/test_day12_*.py`

- VLM client: schema-valid parse, enum-closed hotspots reject invented ids,
  fail-closed on empty/"no image"/invalid (bounded retry) and on `429`
  (terminal, no retry) — mocked transport, no live VLM in CI. Live-VLM tests
  `skip` when the proxy is unreachable (mirroring the Neo4j/Vespa skip pattern).
- Render: deterministic PNG checksum for a fixed SVG+dpi; ASCII-label
  font-independence.
- Ingest: hotspot-match emits chunk; hotspot-mismatch degrades figure
  (Decision 3a); manifest records SHA-256.
- Second-look consensus: triggered only when description insufficient; **agreeing
  reads → consensus returned; diverging / empty reads → refuse (never one
  arbitrary read); `429` → refuse** (Decision 2); anchor corroboration enforced.
- Golden: schema validation; conflict-trap items assert the Decision 3 pass rule
  (refuse-or-both, never force one side).

## Acceptance Criteria — [AI-drafted, pending approval]

1. Synthetic ICN SVGs render to PNG deterministically (fixed checksum for a
   fixed SVG+dpi); INV-1 holds (no real graphics anywhere).
2. `describe_figure` returns **Pydantic-schema-constrained** structured output
   (parts list, hotspot ids, safety warnings) at temperature 0, **enum-closed**
   so it cannot invent hotspot ids, and **fails closed** on empty / "no image" /
   invalid (bounded retry) and on upstream **`429`** (terminal, no retry) —
   asserted with a mocked transport reproducing the probe's instability and a 429.
3. **Mechanical conflict detection**: a figure whose description hotspot set
   diverges from the XML-declared set is **degraded**, not indexed as clean
   (Decision 3a); asserted on a deliberately mismatched fixture.
4. Image-description chunks are indexed **at chunk level into Vespa** as
   `type="figure"` with `{icn_id, sha256, hotspots, parts, safety_warnings}`; a
   figure answer emits a citation of the form **`[ICN-LA100-29-001-01, Hotspot
   02]`** and its reproduction command (re-render + SHA-256 + re-describe + diff)
   is in `EVIDENCE.md`.
5. **Second-look = multi-sample consensus** runs end-to-end: triggered only when
   the ingest description is insufficient; issues **multiple VLM calls** and
   returns a reading **only on consensus + anchor corroboration**; **divergence /
   non-convergence / `429` ⇒ G15 refuse** (Decision 2). Asserted with a mocked
   transport where reads **agree** (→ consensus returned) and where reads
   **disagree / go empty** (→ refuse, never one arbitrary read).
6. **Visual fail-closed = G15**: a question asking for out-of-description
   visual detail that neither the description nor second-look can support is
   **refused** via `figure-out-of-description` (INV-4, Decision 7), asserted on
   the golden set.
7. **Conflict-trap acceptance**: on 文图冲突 traps, the system does not
   force-answer one side (refuses or presents both) — no claim of semantic
   conflict *detection* anywhere (Decision 3b, adopted pass rule).
8. **Resolution provenance (INV-5)**: the `dpi` constant is backed by
   `eval/results/day12-resolution.json` (the 10-image test set); no hardcoded
   magic number without a measured source.
9. **Old-golden no-regression**: adding figure chunks does not drop existing
   text-golden metrics below baseline; reported either way (scan T6).
10. Multimodal golden reported as **k/n scores** (not percentages), classes with
    n<3 marked *indicative*; the **synthetic-data-privilege disclosure** (INV-7,
    scan T2) is stated: description-quality numbers do not extrapolate to real
    scans.
11. `make test` + `make lint` green; existing 373-test suite unbroken.
12. Cross-host `coding-adversarial-review` on the day's diff → findings in
    `docs/reviews/day12.md` Part 1 (automatic gate, before proposing merge).

## Out-of-Scope — [AI-drafted, pending approval]

- **No new VLM provider / key** (Decision 1) — the existing proxy is the channel.
- **No CLIP / ColPali / visual embedding retrieval** (Decision 6; planning) —
  Roadmap; page-granularity conflicts with chunk-precise citation.
- **No parent-child chunking / late-interaction** (scan T6) — toy scale, Roadmap.
- **No automatic semantic-conflict detection** (Decision 3b) — mechanical
  hotspot-diff only; semantic conflict handled by not-force-answering.
- **No real / scanned graphics, no CGM, no `samples/` copying** (INV-1).
- **No changes to answer-layer refusal semantics** beyond wiring the new
  `figure-out-of-description` refusal reason and the second-look coverage check.
- **No description-drift event system** (scan must-master #4) — re-ingest via
  the same pipeline is the drift remedy at this scale (Roadmap for eventing).

## Verification (how to check) — [AI-drafted, pending approval]

```bash
make test && make lint                                    # 373 + day12 vlm/render/ingest/second-look/golden green
# resolution provenance (T5, INV-5): builds eval/results/day12-resolution.json
uv run python tools/day12_resolution.py                   # 10-image set: dpi × hotspot-read × instability
docker start learnarken-vespa learnarken-neo4j            # if not already up
learnarken index samples/package-a ...                    # text + figure chunks in one ingest (T7); manifest records checksums
learnarken eval multimodal --golden eval/golden/day12-multimodal.jsonl
# → k/n scores, three classes, conflict-trap pass = not-force-answer; old-golden regression re-run reported
# second-look: ask a figure-detail question the ingest description omits → re-look (bounded only by upstream 429), else G15 refuse
```

Then the automatic cross-host red-team gate on the diff →
`docs/reviews/day12.md` Part 1 → Yi Xin adjudicates (Part 2, human).
