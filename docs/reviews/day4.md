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

## Part 1b: Red-team findings on the closeout diff (2026-07-16, second pass)

- Review target: the closeout fixes themselves — `4922b64..ee9d713` (rulings
  #5/#8/#9/#10/#12/#13/#14/#15/#16/#17 applied, tests, regenerated artifacts)
- Reviewing model: **Codex** (`codex exec --sandbox read-only`, cross-host via
  adversarial-review 0.5.0); host (Claude) ran an independent pass before
  reading the external output. External verdict: **REVIEW_NEEDED** — "do not
  treat package scoping as closed until basename collision / stale-index
  leakage is fixed."
- Adjudication: Yi Xin's, below the table is intentionally left blank.

| # | Grade | Tag | Finding | Location | Suggestion |
| --- | --- | --- | --- | --- | --- |
| C1 | P0 | external-only | **Package scope leaks on basename collision**: scope identity is `Path(package_dir).name`, so `/tenant-a/manual` and `/tenant-b/manual` share the id `manual`; a search over one can return the other's chunks and the fail-closed check passes | `retrieval/__init__.py` `search_package`/`index_package`; `store.py` post-check | unique package ids; reject duplicate basenames at indexing; additionally reject returned chunk_ids not in the local package's chunk-id set |
| C2 | P1 | cross-validated | **`search_package` never verifies corpus identity** (only the ablation does): stale engine contents under the same basename can be cited by Day 5 | `retrieval/__init__.py` `search_package` | verify returned ids ⊆ local chunk ids, or per-package manifest check before retrieval |
| C3 | P1 | cross-validated (severity ↑ external) | **Overfetch bound breaks silently at >400 chunks**: `fetch_k = len(chunks)` is clamped by `MAX_TOP_K=400`, so the "full-corpus, provably lossless" claim only holds ≤400 | `store.py` clamp; `retrieval/__init__.py` comment | fail closed when `context and len(chunks) > MAX_TOP_K` (or raise cap with tests) |
| C4 | P1 | cross-validated | **README can still drift**: the MiniMax historical row is generator-hard-coded (not artifact-owned) and nothing *enforces* README == rendered artifacts (no `--check` mode/test) | `tools/gen_benchmark_tables.py` | historical row into an artifact with provenance; add `--check` + a test comparing rendered blocks to README |
| C5 | P2 | external-only | `approximate` interpolated into YQL without a runtime bool check (type-confusion injection for Python callers) | `store.py` `search` | `isinstance(approximate, bool)` before interpolation |
| C6 | P2 | external-only | Ablation cache keyed by query *text*, not `query_id` — duplicate texts collapse audit identity | `retrieval/__init__.py` `run_ablation` | assert query-text uniqueness before caching (or key by id) |
| C7 | P2 | external-only | `dense_bakeoff` only *warns* on unresolved anchors — can publish numbers from a known-invalid golden/corpus pairing | `tools/dense_bakeoff.py` | raise, matching `run_eval`/`run_ablation` |
| C8 | P2 | external-only | Integration suite silently skips when Vespa is down — a "green" run may exercise none of the live path (tension with Q6's local-bar ruling, by design today) | `tests/test_day4_integration.py` | a required target where skips fail (e.g. `make test-integration`) |
| C9 | P3 | host-only | Vespa container image is an unpinned `latest` tag while models are SHA-pinned — INV-5 covers only half the stack | `docs/local-services.md` | pin image digest |
| C10 | P3 | external + host (variant) | `tools/probe_length_bias.py` posts secrets to an env-controlled URL (historical evidence tool); `chunk_id` is path-interpolated into document URLs (safe for hash ids, unvalidated in general) | `tools/probe_length_bias.py`; `store.py` `feed`/`delete` | label non-benchmark evidence + allowlist host; validate chunk_id charset |
| C11 | P3 | external-only | Generator uses `assert` for artifact consistency — stripped under `python -O` | `tools/gen_benchmark_tables.py` | explicit `raise SystemExit` |

Host-side notes for adjudication: C1's exploit needs two same-named package
dirs (today's corpus has none — `package-a`/`package-c`); C6 was considered
host-side and initially dismissed (identical text ⇒ identical deterministic
results), the external's audit-identity argument is the stronger reading;
C8 is partially Q6-by-design. Numbers: unchanged by this diff (verified
against the regenerated artifact); Yi Xin's personal re-run still pending.

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

**Remaining findings adjudicated at closeout (Yi Xin, 2026-07-16 closeout
session — transcribed by the implementer under instruction, per the Day 3
precedent; see docs/discussions/day4.md D18):**

6. **Fix ALL nine remaining findings before merge** (the implementer's
   fix-five/backlog-four recommendation was overruled). Implemented, all
   tests green (134 passed + heavy smoke suite):
   - **#5** — `package` attribute in the Vespa schema (fed as the package
     directory basename), engine-side YQL filter, and a fail-closed
     post-check: an out-of-scope hit raises instead of being returned.
     CLI `search` Vespa modes are now scoped to `<package>`.
   - **#8** — container recreated with `-p 127.0.0.1:8080:8080
     -p 127.0.0.1:19071:19071`; docs/local-services.md updated with the
     rationale (no auth ⇒ loopback only). Corpus re-deployed and re-fed.
   - **#9** — YQL inputs validated before interpolation: strategy against
     the chunking registry, package names against `^[A-Za-z0-9._-]+$`,
     `top_k` clamped to [1, 400].
   - **#10 (second half)** — all three HF models pinned by commit SHA
     (`REVISIONS` / `RERANKER_REVISION`), recorded in the corpus manifest
     and every eval artifact; `verify_corpus` fails closed on a revision
     mismatch.
   - **#12** — `tests/test_day4_integration.py`: skip-marked on
     `vespa.is_up()` (feed/search/scope/delete round-trip with cleanup);
     model-loading + rerank smoke gated on `LEARNARKEN_HEAVY_TESTS=1`.
     Hermetic closeout tests in `tests/test_day4_closeout.py`.
   - **#13** — `run_ablation` runs each mode × query exactly once; overall,
     per-category and latency all derive from the cached ranking.
   - **#14** — with an 排除场合 context, Vespa modes overfetch the full
     corpus (exact bound at toy scale) before post-filtering, so an
     inapplicable chunk can no longer evict the applicable answer;
     regression-tested.
   - **#15 (tail)** — per-category table headers carry `(n=…)`; cells with
     n<3 render italic via the generator.
   - **#16** — tables are now rewritten *in place* between
     `<!-- BEGIN gen:… -->` markers in README by
     `tools/gen_benchmark_tables.py`, from `day4-ablation.json` +
     `day4-bakeoff.json` (dense_bakeoff now writes an artifact); the
     historical MiniMax row lives in the generator with provenance.
   - **#17** — `--seed` labeled "metadata only" in help and output.
7. **Day 4b gate: stays SHUT** — no learning-value override; ADR-0001
   (includes the pre-ruled Python-side-MaxSim position from D7 should the
   gate ever open).
8. **Day 4 review point: minimal RDF/SPARQL dependency-graph query pulled
   into Day 9** — ADR-0002; execution-plan Day 9 updated.

Numbers re-run after the fixes: ranking metrics unchanged from the Part-2
re-issue (bm25 0.83 / dense 0.99 / hybrid 0.93 / hybrid-rerank 0.99 R@5);
red-team-reported numbers remain subject to Yi Xin's own re-run before merge.

9. **Part 1b (second pass) ruling: fix C1–C7 and C11 now; C8/C9/C10 to the
   backlog** (Yi Xin, 2026-07-16, same closeout session). Implemented, 140
   tests green:
   - **C1/C2** — `index_package` rejects colliding package basenames; the
     Vespa-backed `search_package` fail-closes when any returned chunk_id is
     not in the local package corpus (kills both the basename-collision leak
     and the stale-index citation path).
   - **C3** — 排除场合 filtering fail-closes when the full-corpus overfetch
     would exceed the engine cap `MAX_TOP_K` (no silently incomplete filter).
   - **C4** — historical MiniMax row moved into
     `eval/results/day4-bakeoff-historical.json` (provenance included);
     generator gains `--check`, and a test runs it so README↔artifact drift
     fails the suite.
   - **C5** — `approximate` must be a runtime `bool` before YQL interpolation.
   - **C6** — `run_ablation` rejects duplicate golden query texts.
   - **C7** — `dense_bakeoff` fails closed on unresolved anchors.
   - **C11** — generator consistency check is an explicit raise, not `assert`.
   - **Backlog (Day 5+)**: C8 (required integration target where skips fail —
     couples to the CI strategy discussion), C9 (pin the Vespa image digest),
     C10 (probe-tool labeling + chunk_id charset validation).
