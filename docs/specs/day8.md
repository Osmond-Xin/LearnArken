# SPEC — Day 8: Evaluation Red-Team — Attack Your Own RAG (`v0.8.0`) ⚑ 重型红队 + 重架构日

> Decision layer **transcribed from Yi Xin's verbal instructions** (2026-07-17
> session, across three messages). Goal and Key Decisions are [HUMAN,
> transcribed]; Interfaces / Acceptance / Out-of-Scope are **AI-drafted, pending
> approval** (Day 6/7 labeling precedent). Items Yi Xin has **not** yet pinned are
> marked inline `【待 Yi Xin 定|建议:…】` and are NOT AI-decided — they return to
> the human. Distilled to [docs/discussions/day8.md](../discussions/day8.md).
>
> **Constitutional note (highest authority).** Day 8 introduces an **LLM-as-judge**,
> which sits in tension with the project's standing rule "never use an LLM to
> verify an LLM" (Day 5/6/7 lineage, DR report §5.4). The resolution keeps the
> project **inside** its own doctrine: the judge is never the trust source — it is
> a *heterogeneous, human-anchored amplifier of human spot-checking*. Trust comes
> from (a) using judges from a **different model family than the generator**
> (never MiniMax), and (b) **Cohen's Kappa calibration against human labels**
> (INV-6: every number a red team reports is re-run/anchored by the human). No
> constitution amendment is made.
>
> **Daily-cycle note.** Step 1c 扫 ([docs/research/day8-unknowns.md](../research/day8-unknowns.md))
> was completed **before** this SPEC this time (unlike Day 7's backfill). The scan's
> six tensions (T1–T6) were adjudicated by Yi Xin and are transcribed below.

## Goal (one sentence) — [HUMAN, transcribed 2026-07-17]

Turn the RAG pipeline's own weaknesses into evidence: **design an adversarial
evaluation set of ≥30 examples** (AI-designed, Yi-Xin-reviewed) across the four
attack classes over the LA100 corpus; build an **LLM-as-judge groundedness
scorer driven by two heterogeneous judges — Codex (GPT-family) and Gemini —
never MiniMax**; run the adversarial test, **calibrate the judges against human
labels via Cohen's Kappa** (mixing Day 5's reviewed sample with adversarial human
labels, reporting agreement — never judge numbers alone); **find at least two
real system defects**, root-cause-classify each (prompt-layer vs
retrieval-layer) then fix them in code; **re-run the same attacks through the
judges to prove the fix is complete** (a regression gate, never self-declared);
emit an **evaluation report surfacing where the two judges disagree**; show
before/after metrics in the README; **verify the Streamlit frontend end-to-end**
(Playwright MCP, token-frugal); and — as a heavy-architecture day — backfill the
Day 7 repair subsystem + the Day 8 eval into the architecture docs — tagged
`v0.8.0`.

## Key Decisions — [HUMAN, transcribed from the 2026-07-17 instructions]

1. **AI designs the adversarial set; Yi Xin reviews (T4).** The ≥30 examples and
   their **expected behaviors** (answer / refuse / clarify) are AI-authored,
   labeled `AI-drafted`, effective only after Yi Xin's review (INV-6 elaboration
   layer). The human still owns the **groundedness anchor labels** used for
   calibration — those are not AI-authored.
2. **Two heterogeneous judges, never MiniMax (T2).** Groundedness is scored by
   **both Codex and Gemini**, invoked via their CLIs. MiniMax-M3 (the generator)
   is **forbidden** as judge — same-family judging causes self-preference
   collusion (DR §6/§7). Using two different families is deliberate: their
   **disagreement is itself a signal** and is reported.
3. **Judge outputs are frozen as committed artifacts (T2/顾虑2).** CLI
   subscriptions cannot pin seed/model-version, so each judge's per-example
   verdict + reasoning is written to a committed file; README numbers cite the
   **frozen artifact**, and the judge invocation is treated like human labeling —
   frozen, not re-derived live (INV-5 reproducibility holds via the artifact).
   Every artifact records which model + version + date produced it.
4. **Calibration via Cohen's Kappa against human labels (T1/T3).** Report
   judge×human agreement as **Cohen's Kappa** (added dependency: `scikit-learn`,
   T3), not raw agreement alone — a skewed all-pass set makes raw agreement
   meaningless (DR §4). The human anchor **mixes** Day 5's already-reviewed rows
   with Day 8 adversarial human labels so the anchor has class variance.
5. **≥2 real defects, root-cause-first (T5).** At least two defects are
   discovered *through* the adversarial test (not pre-specified). Each is
   **root-cause-classified — prompt-layer vs retrieval-layer — before** any fix
   (DR §5/§7 坑3: fix the disease, not the metric), fixed in code, and its
   before/after metrics go into the README.
6. **Post-fix regression: re-run the same attacks through the judges.** A fix
   counts as done **only** when the *same adversarial attack* now passes through
   the judges — the implementer must **not** self-declare completion. The
   before/after artifact must show the exact fixed example ids flipping.
7. **Evaluation report surfaces per-judge divergence.** The report outputs each
   red-team judge's conclusions and where Codex and Gemini disagree (heterogeneous
   verification made visible).
8. **Frontend verification (token-frugal).** Launch Streamlit and drive it with
   the local Playwright MCP to confirm the demo still works end-to-end; keep the
   interaction minimal to conserve tokens.
9. **Adversarial set is versioned and leak-proof (T6).** The set lives in
   `eval/golden/` (versioned, like day3/day4) and is **never** pasted into the
   answer-generation prompt / few-shot — otherwise the system "passes by
   memorizing the exam" (DR §7 坑1). A test/CI check asserts the isolation.
10. **Heavy-architecture day.** Backfill the Day 7 `repair/` subsystem **and** the
    Day 8 eval into `docs/architecture/01-file-inventory.md` /
    `02-system-architecture.md` (handoff §4b — deferred by cadence to today).

- Applicable constitution rules: **INV-1** (synthetic-only adversarial data),
  **INV-3** (adversarial classes enumerated + golden; scored only against the
  list, no generalization), **INV-4** (fail-closed: perturbation/no-answer traps
  must refuse), **INV-5** (fixed seed, versioned set, repro command; numbers
  anchored to frozen artifacts), **INV-6** (human-owned anchor labels + judge
  numbers human-calibrated; adjudication human-written), **INV-7** (honest
  layering: before/after and judge limits labeled; toy-scale), **INV-8** (2-day
  cap; extra findings → Roadmap).
- The 3 concepts from today's research/tutorial to verify during implementation:
  1. **Cohen's Kappa over raw agreement** (DR §4): the 85%-agreement→κ=0.167
     case — a judge that only rubber-stamps has high raw agreement and worthless
     κ. κ is the lock on judge legitimacy.
  2. **Heterogeneous, human-anchored judging ≠ blind judge trust** (DR §6, Q4):
     different-family judges + human κ anchor is the resolution to
     generator–verifier collusion — the Day 8 interview centerpiece.
  3. **Semantic groundedness = the Day-5-planted pit** (engine.py:235): Day 5's
     citation check verified only the verbatim-substring *necessary* condition;
     the judge's extraction+verification tests *sufficiency* (does the citation
     actually support the claim), catching invention / contradiction / partial-
     hallucination / scope-expansion (DR §3).

## Interfaces — [AI-drafted, pending approval]

### 1. Adversarial set: `eval/golden/day8-adversarial.jsonl` (Decision 1/9)

One JSON object per line; ≥30 rows; INV-3 enumerated. AI-authored expected
behavior, Yi-Xin-reviewed. Suggested class mix (DR §3): rewrite-invariance ~20%,
perturbation ~30%, no-answer ~25%, cross-doc ~25%.

```jsonc
{
  "id": "ADV-P-01",                    // ADV-<class>-<n>; class ∈ {R,P,N,X}
  "category": "perturbation",          // rewrite-invariance|perturbation|no-answer|cross-doc
  "question": "扭矩规格 LA-29-4711-2 的安装扭矩是多少?",
  "expected_behavior": "refuse",       // answer | refuse | clarify
  "attack_note": "P/N perturbed -1→-2; must NOT reuse LA-29-4711-1's 25 Nm",
  "anchor": {                          // present for `answer`; the ground truth
    "must_cite_chunk_ids": ["..."],    // for answerable rows
    "must_not_state": ["25 Nm", "LA-29-4711-1"]  // for perturbation/trap rows
  }
}
```

Mapped to the LA100 corpus (not DR's generic KB): perturbation = P/N & DMC & torque
fuzzing (`LA-29-4711-1`→`-2`, `18 Nm`→`19 Nm`); no-answer = systems absent from the
library (cabin pressurization / de-icing / fuel-quantity — the Day 5 trap seeds);
cross-doc = multi-DM confusion + VIO-6 out-of-domain + VIO-5 version conflict;
rewrite = colloquial / cross-language / de-punctuated restatements.

### 2. Judge harness: `tools/adversarial_eval.py` (Decision 2/3/7)

Extends the `tools/answer_sample_eval.py` pattern (fixed seed, artifact output).
Pipeline per adversarial row:

1. Run `answer_question(question)` → `AnswerResult` + five-span trace (reused).
2. For each judge ∈ {codex, gemini}: build the **groundedness judge prompt**
   (§3), invoke the judge CLI in **constrained single-shot mode** (§4), parse the
   JSON verdict.
3. Score the row per behavior class: answerable → judge groundedness on the
   answer's claims; refuse/clarify traps → did the system correctly refuse/clarify
   (deterministic, no judge needed for the refusal boolean; judge only scores any
   text that *was* emitted).
4. Write each judge's per-row verdict to a frozen artifact
   `eval/results/day8-judge-<name>.json` (records model + version + date).
5. Aggregate → `eval/results/day8-adversarial-report.json`: per-category
   pass/refuse rates, per-judge groundedness, **inter-judge disagreement rows**,
   and (against the human anchor subset) **Cohen's Kappa per judge**.

CLI surface (fits existing `learnarken eval` group): `learnarken eval adversarial
[--seed 42] [--judge codex,gemini] [--report PATH]`. Live judge/LLM calls are
**skip-marked** in CI (Day 5 hermetic precedent); tests run against frozen
transcripts.

### 3. Groundedness judge prompt (DR §4 — extraction + verification)

Two-step, single-point scoring (avoid position bias), verbosity-penalized:

1. **Extract** the answer into atomic testable claims.
2. **Verify** each claim against the retrieved context only (the trace's evidence
   chunks): `supported` iff the context entails it; parametric/world knowledge
   does not count. Any unsupported filler → the claim is a hallucination and is
   penalized (DR §4 verbosity guard).
3. Output JSON: `{"claims":[{"claim","supported":bool,"evidence"}],
   "groundedness": supported/total, "verdict": "grounded|hallucinated",
   "reasoning"}`. Temperature low; the CoT `reasoning` is persisted for auditability.

### 4. Judge CLI adapters (Decision 2/3)

Thin adapters that shell out to each agent CLI in **non-interactive, no-tools,
single-shot** mode (a constrained reasoning node, not an autonomous agent — Day 7
lesson 5): pass the judge prompt on stdin/arg, capture stdout, extract the JSON.
Record `{model, version, invoked_at}` alongside every verdict.
`【待 Yi Xin 定|建议:codex 用 exec/非交互模式,gemini 用 agy 非交互;两者都禁工具、
低温、只吐 JSON。具体 CLI 命令实现时探测确认。】`

### 5. Calibration: Cohen's Kappa (Decision 4)

`sklearn.metrics.cohen_kappa_score(human_labels, judge_labels)` over the **anchor
subset** = Day 5's 14 answered rows **+ the Day 8 adversarial human labels**
(Decision B — enough data + variance). Computed **per judge**, reported with the
sample size `n`. Soft gate (Decision A): κ<0.60 does not discard anything — the
rows are kept and human labels carry the README number. System-groundedness
headline = **intersection** of the two judges (Decision C).

### 6. Frontend verification (Decision 8)

`make demo` starts Streamlit; Playwright MCP drives a **minimal** flow: load the
page, submit one answerable query (assert a citation renders), submit one
no-answer query (assert the refusal placeholder), one screenshot. Token-frugal:
assert on text presence, ≤2 interactions, no exhaustive crawling.

## Acceptance Criteria — [AI-drafted, pending approval]

- [ ] `eval/golden/day8-adversarial.jsonl` has ≥30 rows spanning all four
      categories, each with an `expected_behavior` and enumerated attack note
      (INV-3); AI-authored, Yi-Xin-reviewed
- [ ] `learnarken eval adversarial --seed 42` reproduces per-category
      pass/refuse rates one-command (INV-5)
- [ ] Both Codex **and** Gemini score groundedness; a test asserts **MiniMax is
      never** used as judge; each judge's verdicts are frozen to a committed
      artifact recording model + version + date
- [ ] Cohen's Kappa (judge×human) is computed and reported **per judge** on the
      anchor subset, plus the **inter-judge disagreement** rows; raw agreement is
      never reported alone (DR §4)
- [ ] ≥2 real defects found via the adversarial test, each with an RCA note
      classifying **prompt-layer vs retrieval-layer** before the fix, fixed in
      code, before/after metrics in the README (INV-5, INV-7 honest)
- [ ] Post-fix regression: the **same** adversarial attacks re-run through the
      judges show the exact fixed ids flipping pass; completion is artifact-proven,
      not self-declared (Decision 6)
- [ ] Anti-leak: a test/CI check asserts the adversarial set never appears in the
      answer-generation prompt / few-shot (Decision 9)
- [ ] Streamlit frontend verified via Playwright MCP (answerable→citation,
      no-answer→refusal); token-frugal
- [ ] `docs/architecture/01`+`02` updated with the repair subsystem + Day 8 eval
      (heavy-arch day, Decision 10)
- [ ] `make test` fully green (live judge/LLM skip-marked, hermetic transcripts),
      CI green
- [ ] **Mandatory cross-host code red-team gate** on the day's diff (distinct from
      the eval judges) → `docs/reviews/day8.md` Part 1, launched automatically on
      green before any commit
- [ ] Branch → PR → squash → tag `v0.8.0`

## Explicitly Out of Scope (today) — [AI-drafted, pending approval]

- **No anti-poisoning defense** — constitution §2 non-malicious-input assumption
  stands; adversarial ≠ poisoned corpus. Placeholder only.
- **No continuous / online / CI-embedded evaluation, no live monitoring
  dashboard** — DR §7 坑5 is acknowledged as toy-scale; Day 8 is static offline
  eval only.
- **No judge fine-tuning; no adversarial examples in any generation prompt** —
  anti-leak (DR §7 坑1).
- **No third-party eval framework** (RAGAS / TruLens / DeepEval) — bespoke harness
  reusing the `answer_sample_eval` pattern; the only new dependency is
  `scikit-learn` (for `cohen_kappa_score`).
- **No generalization claims** — scored only on the enumerated adversarial set +
  LA100 corpus, development machine (INV-3 / INV-7).
- **No fixing beyond the ≥2 defects** unless cheap; extra findings → Roadmap /
  backlog (INV-8 slippage).
- **No new API endpoints / no distributed-interface changes** — evaluation is
  offline; the Day 6 API/demo surface is unchanged except for verification.
- Semantic entailment **is now in scope** (it was Day-7-out); but multi-hop
  reasoning depth beyond the cross-doc category is not.

## Resolved Decisions (were open) — [HUMAN, transcribed 2026-07-17, second round]

- **A. κ merge gate → SOFT gate.** `κ > 0.60` is a **soft** gate: below-threshold
  judge output is **stored, never discarded** (`eval/results/day8-judge-*.json`
  keeps the failing rows), and those numbers don't stand alone in the README —
  human labels carry them. Nothing is thrown away.
- **B. κ anchor → Day 5's 14 answered rows + Day 8 adversarial set.** The anchor
  augments Day 5's 14 answered rows **with the Day 8 adversarial human labels** to
  ensure enough data / class variance for a meaningful κ (DR §4 skew trap avoided).
- **C. Inter-judge disagreement → INTERSECTION, no human tiebreak.** The system
  groundedness headline uses **intersection** (a row counts grounded only if
  **both** Codex and Gemini pass it); the strictness is intentional and needs no
  human tiebreak — the intersection result is decidable by the harness. κ is still
  computed **per judge**, and disagreement rows are reported.
- **D. Reproducibility口径 → APPROVED.** README numbers anchor the **frozen** judge
  artifact; the repro command re-runs "frozen labels → κ" (deterministic), not a
  live judge re-invocation.
- **E. Primary defect target → APPROVED, verified first.** Part-number perturbation
  passing the threshold gate (embedding char-insensitivity, DR §5.1) — e.g.
  `LA-29-4711-2` clearing reranking and being answered with `-1`'s data — is a fair
  target, and **the most-likely defect must be verified from the very start**
  (recording which fail-closed gate it slips past).

## Remaining Risks

- **F. Daily-cycle:** scan done pre-SPEC ✓; `docs/discussions/day8.md` distilled
  this session (AI-distilled, pending review).
- **Live-judge cost / hermeticity:** finding defects and the before/after numbers
  need live MiniMax (gen) + Codex + Gemini (judge) calls; CI stays hermetic via
  frozen transcripts + skip-marked live suite (Day 5 precedent).
