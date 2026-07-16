# Day 4 Red-Team Review & Adjudication

## Part 1: Red-Team Findings (non-implementing model, read-only review)

- Review target: branch `feat/day4` vs `feat/day3` (commits `35b84db..b414fa4`;
  Day 4a: MiniMax client, LangChain stack adoption, Vespa dense store,
  semantic chunking, hybrid RRF + rerank, dense bake-off, mode ablation,
  golden-set expansion)
- Reviewing model: **Codex** (`codex exec --sandbox read-only`, cross-host via
  adversarial-review 0.5.0), 2026-07-16
- Inputs: full `src/ tools/ tests/ pyproject.toml` diff + heavy-red-team focus
  brief (attack the evaluation method itself), with the D16 self-review
  findings disclosed up front
- Cross-validation: the implementer (Claude) ran an independent host-side pass
  **before** reading the external output. Two host-side findings were verified
  and already fixed pre-review (dependency upper bounds → commit `b414fa4`;
  Qwen3 query-prompt applied → non-finding, cos 0.857 ≠ 1). Tags record who
  caught what; ✅ = the implementer verified the specific claim by experiment
  or against the raw eval JSON before filing. Adjudication and any number
  re-runs remain the human's (Part 2).
- Verdict from the external reviewer: **DO_NOT_MERGE** — "until the evaluation
  tables are regenerated from a manifest-verified corpus, AI-drafted anchors
  are demoted or human-reviewed, and Vespa-backed retrieval is package-scoped."

| # | Grade | Tag | Finding | Location | Suggestion |
| --- | --- | --- | --- | --- | --- |
| 1 | P0 | external-only ✅ | **Impossible metric row in the README**: hybrid-rerank shows `R@5 0.99 > R@10 0.97`, which the evaluator cannot produce (Recall@k is monotonic by construction). Verified against the raw eval JSON: the true post-fix row is `0.9851 / 0.9851 / MRR 0.8507 / nDCG 0.8835` — the implementer hand-edited only the R@5 cell when applying the document-hygiene re-run and left R@10 stale. A transcription error in the published table, not an evaluator bug — but it is exactly the class of error that discredits a benchmark README | `README.md` ablation table; `docs/notes/day4-failure-cases.md` | regenerate every published table from the eval JSON artifact (no hand-edited cells); add an invariant check `Recall@k₂ ≥ Recall@k₁` to report generation |
| 2 | P0 | external-only | **"82-query" ranking claims are mislabeled**: no-answer rows are excluded from Recall/MRR/nDCG (denominator = answerable only), so the real n is **67** (all) / **27** (human-reviewed) — the README headline says 82. Adding 100 more no-answer traps would leave dense "Recall" untouched while safety worsened | `retrieval/evaluate.py` denominator; `README.md` bake-off + ablation intros | label ranking metrics `answerable n=67` / `human-reviewed answerable n=27`; publish no-answer accuracy as a separate, primary safety metric |
| 3 | P0 | cross-validated | **AI-drafted anchors used as primary benchmark evidence**: 50 of 82 rows are implementer-drafted (`relevance_reviewed: false`), several `notes` fields encode *expected system behavior* ("dense is expected to return the IPD chunk…"). Provenance contamination: the same class of model that drafted the paraphrases is being measured — LLM-phrased paraphrases plausibly favor LLM-based embedders, inflating the dense-vs-BM25 gap and the Day 4b gate reading. Host-side raised the same drafting-bias concern independently | `eval/golden/day4.jsonl` rows 33+; `README.md` tables; D15 gate reading | demote the 50 rows to exploratory until blind human adjudication; primary claims from the reviewed-27 subset (or a held-out set) only |
| 4 | P0 | cross-validated (severity ↑ external) | **Vespa corpus identity is unverified**: the ablation's only guard is a document-*count* equality; a stale, mixed, or poisoned index with the same count passes and the rows silently compare different corpora. Self-review D16 had this at "accepted risk"; the external correctly escalates: benchmark claims rest on it | `retrieval/__init__.py` `run_ablation` count check; `vespa/store.py` `feed` | index manifest (package ids, chunk ids, source digests, provider + model revision, schema dim, commit) written at feed time and verified at eval time; stage-then-mark-ready feeding |
| 5 | P1 | cross-validated | **Vespa-backed search ignores the `<package>` argument** (whole-index retrieval): Day 5 RAG would cite chunks from another package. Known from D16 (help-text disclosure only); external adds the concrete Day 5 citation-grounding scenario | `vespa/store.py` `search`; `cli.py` search | add a package/corpus attribute + engine-side filter; fail closed on out-of-scope hits |
| 6 | P1 | external-only | **Hybrid silently loses BM25's zero-hit guard**: standalone BM25 applies the token-overlap hit test (Day 3 red-team #1), but the raw `BM25Retriever` handed to `EnsembleRetriever` does not — for an unknown part number the BM25 arm contributes arbitrary top-k docs, so hybrid returns confident results and the README's "the lexical arm keeps refusal behavior" claim is **false for hybrid/rerank modes** (their zero-hit rate is 0.00 in the published table — consistent with the bug) | `hybrid.py` `bm25_retriever`; README footnote | apply the same overlap filter inside the retriever subclass before fusion; add hybrid no-answer tests |
| 7 | P1 | external-only | **`.env` loading enables config poisoning / key exfiltration**: `Path.cwd()/.env` wins over repo-root — running any `learnarken` command from an untrusted directory sends the Bearer key + proxy token to an attacker-controlled `MINIMAX_API_URL` | `config.py` `load_env` candidates | load repo-root `.env` only (or explicit `--env-file`); allowlist `MINIMAX_*` keys; validate URL scheme/host; redact response bodies in errors |
| 8 | P1 | external-only | **Vespa ports exposed unauthenticated by default**: `-p 8080:8080 -p 19071:19071` binds 0.0.0.0; any LAN process can query, poison, or `clear()` the index | `docs/local-services.md` run commands; `vespa/store.py` `clear` | document/bind `127.0.0.1:8080:8080`; treat the store as writable-by-anyone until then |
| 9 | P1 | cross-validated | **YQL is string-built**: `strategy` (and `top_k`) interpolated into the query; CLI `choices` masks it today, but Day 5/6 API callers may pass user input straight through | `vespa/store.py` `search` | validate strategy against `STRATEGIES`, clamp `top_k`, prefer parameterized inputs |
| 10 | P1 | cross-validated (partially fixed pre-review) | **Supply chain under-pinned for benchmark claims**: dependency upper bounds were missing (fixed in `b414fa4` after the host-side pass); still open: HF models (`Qwen3-Embedding-8B`, `bge-m3`, `bge-reranker-v2-m3`) are loaded by name with **no revision pin**, so upstream weight updates silently move published numbers (INV-5) | `embedding/providers.py`; `hybrid.py` | pin `revision=` SHAs; record model SHAs in eval artifacts; reproduce with `uv run --locked` |
| 11 | P1 | external-only ✅ | **Stale public API in `embedding/__init__`**: still exports `DIMENSION = 1536` (MiniMax) and a docstring naming MiniMax as default, while the actual default is Qwen3-8B @ 4096 (Vespa schema agrees). Day 5 code importing `DIMENSION` builds a wrong vector contract | `embedding/__init__.py` | remove the constant or make it provider-aware (`DIMENSIONS[DEFAULT_PROVIDER]`) |
| 12 | P2 | external-only ✅ | **Claimed integration tests don't exist**: `test_day4_retrieval.py` docstring references `test_day4_integration.py`, which was never written — Vespa deploy/feed/search, model loading and rerank execution have zero automated coverage (Q6 ruling made local runs the bar, but there is no runnable local integration suite either) | `tests/` | add skip-marked integration tests (`vespa.is_up()` guard) so the local bar is executable, not manual |
| 13 | P2 | cross-validated | **Ablation re-runs expensive searches** (timing pass + overall + per-category): query-vector caching mitigates the dense arm, but rerank/BM25 passes still repeat; slow and thermally noisy on 8B + reranker | `retrieval/__init__.py` `run_ablation` | run each mode/query once; cache ranked ids + timing; derive all metrics from the cache |
| 14 | P2 | cross-validated | **Applicability (排除场合) is post-retrieval for Vespa modes**: an inapplicable chunk can occupy rank k while the applicable answer sits at k+1 and is lost after filtering — the schema stores applic attributes but no engine-side predicate uses them | `retrieval/__init__.py` `search_package`; `chunk.sd` | push the filter into the YQL predicate, or overfetch with a tested bound |
| 15 | P2 | cross-validated | **Per-category table cells lack n**: `identifier_perturbation` shows Recall@5 = 1.0 from a single answerable query; bake-off note doc carries the same cell — misleading without the denominator | `docs/notes/day4-dense-bakeoff.md`; ablation per-category output | print `n` per cell; suppress or gray cells with n < 3 |
| 16 | P3 | external-only | Docs hand-maintained tables drift from artifacts (same root cause as #1) | `docs/notes/*` | generate doc tables from the JSON artifacts |
| 17 | P3 | cross-validated | `--seed` remains cosmetic on a deterministic pipeline (D16 finding 4, template inherited from Day 3 #11) | `cli.py` | drop, or label "metadata only" in output |

### Key risks if merged as-is (external summary, host-concurred)

1. **Published numbers are not currently defensible**: one table row is
   arithmetically impossible (#1), headline n is overstated (#2), and the
   majority of the qrels are unreviewed drafts from the system's own
   implementer (#3). The Day 4b gate (D15) is being read off exactly these
   numbers.
2. **The refusal story is half false**: BM25-alone refuses; hybrid/rerank —
   the modes the architecture actually recommends — do not (#6).
3. **Day 5 grounding hazard**: package-scope leakage (#5) becomes wrong-source
   citations the moment answers carry references.

## Part 2: Adjudication (Yi Xin, 2026-07-16 — transcribed by the implementer
under instruction, per the Day 3 precedent; wording faithful to the ruling)

1. **Finding #3 (AI-drafted anchors) — RESOLVED by completing the review.**
   Yi Xin reviewed all 50 candidate anchors (and edited the golden set in the
   process — post-review numbers drifted slightly, confirming real review).
   `relevance_reviewed: true` on all 82; the implementer additionally flipped
   `category_reviewed` on the original 32 as within the ruling's scope —
   flagged here for veto.
2. **Finding #4 (corpus identity) — ACCEPT the manifest scheme.** Implemented:
   `learnarken index` writes `.vespa-manifest.json` (packages, strategy,
   provider, dimension, chunk ids); `run_ablation` verifies manifest AND the
   engine's actual document-id set (visit API) against the local corpus —
   fail closed on any mismatch.
3. **Findings #1/#2/#6 — re-issue the tables.** Done: tables are now generated
   only by `tools/gen_benchmark_tables.py` from the committed eval artifact
   (`eval/results/day4-ablation.json`), with a built-in Recall-monotonicity
   refusal (#1) and answerable-n labeling (#2). The #6 fusion guard was fixed
   first (GuardedBM25Retriever + regression test), then everything re-run on
   the reviewed golden set.
4. **Number re-runs — done by Yi Xin** ("第四项已经跑完").
5. **Additional ruling: remove MiniMax from the architecture; Qwen3-8B (the
   measured best) is the sole dense provider.** Implemented: client + config
   loader deleted (which also eliminates finding #7's cwd-`.env` attack
   surface), provider registry reduced to bge-m3/qwen3-8b, stale
   `DIMENSION=1536` export fixed (#11), local-services.md section retired,
   historical row reproducible at commit `b414fa4`;
   `tools/probe_length_bias.py` made self-contained so the length-bias
   evidence stays runnable.

**Adjudicated earlier in-session** (pre-review, host-side): dependency upper
bounds (#10, first half) fixed in `b414fa4`.

**Remaining findings not yet explicitly adjudicated** — carried to the Day 4b
/ Day 5 backlog for ruling: #5 (package-scoped Vespa retrieval — flagged as a
Day 5 grounding prerequisite), #8 (Vespa port binding), #9 (YQL
parameterization), #10 second half (HF model revision pinning), #12
(integration test suite), #13 (ablation re-runs searches), #14 (applicability
push-down), #15 (per-category n labels — partially addressed by the generator
note), #16, #17.
