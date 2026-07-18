# Day 6 Red-Team Review & Adjudication

## Part 1: Red-Team Findings (non-implementing models, read-only review)

- Review target: `HEAD...feat/day6` working tree (FastAPI backend
  `src/learnarken/api/app.py`: `/health`, `/upload`, `/query`; SSE streaming
  with retraction — `answer/stream.py` answer-field extractor, `engine.py`
  `on_event`, `llm/minimax.py` `chat_json_stream`; Streamlit dumb client
  `demo/streamlit_app.py`; `make demo` — `tools/run_demo.sh`,
  `tools/demo_preflight.py`; hermetic tests).
- Reviewing models (two agents, per the Day 6 decision-4 instruction to
  launch two review agents):
  1. **Codex** (`codex exec --sandbox read-only`, cross-host via
     adversarial-review 0.5.0) — reliability + security red team, 2026-07-17.
  2. **security-review skill** (host-run focused security pass) — 2026-07-17.
- Cross-validation: the implementer (Claude) ran an independent host-side
  pass and, before the review, had already found and **fixed live** one
  upload-bypass defect (a non-`DMC-` filename passed validation as a silent
  no-op and was reported `ingested`; now rejected server-side — see finding 7,
  fixed pre-review). Tags: `[cross-validated]` both caught it; `[external]`
  only the partner; `[host]` only the implementer. Adjudication (Part 2) is
  the human's.
- External verdict (Codex): **DO_NOT_MERGE** until the upload path is
  transactional, upload size is enforced before multipart parsing, and
  streamed partial answers are invalidated on all terminal failures.
- Security verdict (security-review): one Medium (CSRF corpus-poisoning);
  no High directly-exploitable access/RCE/authz finding in the new code.

| # | Grade | Tag | Finding | Location | Suggestion |
| --- | --- | --- | --- | --- | --- |
| 1 | P1 | external | **Upload is not transactional**: `write_bytes()` overwrites the active module *before* validation/index commit. A re-upload of an existing filename that then fails validation or indexing deletes the previously-valid module; a crash between write and validate leaves an unvalidated active file. Violates the stated "no partial state" contract. | `api/app.py:141-201` | validate + index in a staging package; swap into the active uploads dir only after both pass (atomic rename / versioned dir); add replacement-failure tests |
| 2 | P1 | external | **Size cap enforced after multipart is spooled**: `file.file.read(MAX+1)` runs only after python-multipart has parsed/spooled the whole body — the 2 MiB bound does not bound what reaches disk/temp first. | `api/app.py:133-135` | reject on `Content-Length` before parsing, or set a server/body limit; treat as reliability (DOS), not access |
| 3 | P1 | external | **Partial `token`s not invalidated on transport failure**: a mid-stream `LLMError` after tokens were emitted yields an `error` event but **no `retract`**. A non-Streamlit SSE client has no protocol signal to withdraw the already-shown text — the retraction contract (decision 3 / INV-4) holds only for gate refusals, not transport aborts. | `api/app.py:210-246`; `llm/minimax.py` `chat_json_stream` | track "tokens emitted"; on any terminal failure after tokens, emit `retract` before `error`, and assert the order in a test |
| 4 | P2 | external | **CSRF corpus-poisoning on `/upload`** (also the security pass's sole Medium): `multipart/form-data` is a CORS "simple request" — a site the operator visits while `make demo` runs can POST an attacker-authored, validation-passing `DMC-*.xml`; the browser can't read the response but the write+index side effect completes, poisoning local answers. Loopback binding is not a defense against the operator's own browser. Directly the "malicious insertion" threat decision 4 names. | `api/app.py:124`; `docs/specs/day6.md:119-127` | require a random demo token (custom header ⇒ forces preflight) or an `Origin`/`Host` allowlist on state-changing routes |
| 5 | P2 | external | **Query reads the uploads dir with no read/write coordination against an in-flight upload**: `_query_packages()` can select a just-written module mid-validate/reindex; the query then chunks a file the upload may still reject, or trips `verify_corpus` against a half-written manifest. `_upload_lock` serializes uploads against each other but not against queries. | `api/app.py:82-89, 141-186, 219-225` | stage uploads + an atomic "active corpus" pointer, or guard corpus selection and upload commit with one rw-lock |
| 6 | P2 | external | **`make demo` readiness loop has no failure exit**: after 60 unreachable `/health` attempts it falls through and starts Streamlit against a dead backend — violates the fail-closed one-command-demo promise. | `tools/run_demo.sh:15-27` | track success; exit non-zero after the timeout |
| 7 | P1 | host (fixed pre-review) | **Scanner-ignored upload reported `ingested`**: the package scanner only recognizes `DMC-/PMC-/DML-*.xml`; a differently-named `.xml` passed `analyze_package` as a zero-file no-op (`error_count == 0`) and was reported ingested though never validated or indexed. Found live 2026-07-17. | `api/app.py` upload | **fixed**: `_SAFE_NAME` now requires a `DMC-` prefix, and the handler rejects any upload whose basename is not among `package.data_modules` (fail closed). Regression tests added (`test_non_dmc_name_rejected`, `test_scanner_ignored_file_rejected`) |
| 8 | P3 | external | **Fail-closed classification is exception-*name* string matching incl. broad `ValueError`**: unrelated programmer `ValueError`s get surfaced as sanitized "service" errors (503/error event), hiding bugs and possibly leaking internal path/message text. | `api/app.py:55-64, 236-243` | catch concrete exception classes; scope `ValueError` to the known validation/index call sites |
| 9 | P3 | external | **Streamlit assumes JSON bodies / valid SSE JSON**: a backend 500 HTML page or malformed SSE line raises in `.json()` / `json.loads()` and crashes the dumb client instead of a fail-closed UI. Client-side only. | `demo/streamlit_app.py` health + query | wrap `.json()` / `json.loads()` with a fallback display |
| 10 | P3 | external | **Dependency ranges are broad** (`fastapi`, `uvicorn`, `python-multipart`, `streamlit`), though `uv.lock` pins actual installs. | `pyproject.toml`; `uv.lock` | keep CI on `uv sync --locked`; document that the demo is lockfile-based (matches Day 4 #13 precedent) |

### Cross-validation notes

- Findings 1–3 are Codex's **BLOCKERS** and the basis for `DO_NOT_MERGE`.
  They are reliability/contract-integrity issues (transactional upload,
  retraction completeness), not access-control vulnerabilities; the
  security pass concurred they are not RCE/authz.
- Finding 4 is the **one point both reviewers raise** (Codex P2 + the
  security pass's sole Medium): browser-to-loopback CSRF, in scope of
  decision 4's "malicious insertion." Highest-confidence security item.
- Finding 7 was already fixed by the implementer before the review ran and
  is recorded here for provenance, not as an open item.
- The security pass explicitly **cleared**: upload path traversal (`.name`
  + `DMC-` regex fullmatch), Streamlit XSS (escaped rendering, no
  `unsafe_allow_html`), XXE (existing defusedxml, no new parser), secrets
  in logs (key/token never logged), and error-message data exposure
  (sanitized type+message allowlist; opaque "internal error" otherwise).

### Key risks if merged as-is (external summary, host-concurred)

1. **Upload is not atomic** (#1): a failed re-upload can destroy a
   previously-valid module and desynchronize files vs. Vespa vs. manifest —
   the very "partial state" the fail-closed design promises never to leave.
2. **Retraction is incomplete** (#3): the SSE contract's headline property
   (streamed text is always either confirmed or explicitly withdrawn) holds
   for gate refusals but not for transport aborts, leaking unverified text
   to non-Streamlit clients with no withdrawal signal.
3. **Corpus poisoning via CSRF** (#4): a drive-by page can insert
   attacker-authored "verified" source into the local corpus while the demo
   runs — decision 4's stated threat, unmitigated by loopback binding.

### Implementer fix log (2026-07-17, provenance only — not adjudication)

At Yi Xin's instruction ("红队的检查结果全部都修，同时自己也 review 一下")
the implementer applied fixes for every finding and ran an independent review
pass. This log records *what changed*; whether each change is the right call
is Part 2's (the human's). All 222 tests green + lint clean after the fixes;
the transactional-upload and CSRF paths were re-verified live end-to-end.

| # | Fix applied | New tests |
| --- | --- | --- |
| 1 | `_staged_commit`: validate + index a same-basename *staging* copy; swap into the active dir atomically (`os.replace` dance + startup `_recover_interrupted_swap`) only after both pass; `try/finally` guarantees staging cleanup on any path | `test_failed_replacement_preserves_prior_valid_module` + live: valid ingest → broken re-upload rejected → prior module still answers "12 Nm" |
| 2 | `Content-Length` pre-check rejects >2 MiB + slack before python-multipart spools; post-read cap retained | `test_oversize_content_length_rejected_pre_parse` |
| 3 | SSE generator tracks `tokens_emitted`; a terminal transport failure after tokens emits `retract` (`gate:transport`) before `error` | `test_mid_stream_transport_failure_retracts_before_error`, `test_service_failure_is_error_event` (no-token case asserts no retract) |
| 4 | `_guard_csrf` on `/upload` + `/query`: a present `Origin`/`Referer` must be loopback, else 403; server-side clients (no Origin) pass | `TestCsrf` (foreign→403, loopback→200, none→through) |
| 5 | Substance resolved by staging (active only ever holds committed files); `_corpus_lock` covers the swap window; a query racing the swap can at worst fail closed | covered by #1 tests + documented in `05-api-and-demo §3/§7` |
| 6 | `run_demo.sh` tracks readiness; exits non-zero after 60 s if `/health` never healthy — never starts the frontend against a dead backend | manual (shell) |
| 8 | Every fail-closed branch (`/upload`, `/query`) now logs the exception; classification kept as string-name parity with the CLI's INV-4 mapping (concrete-class switch would diverge and `EmbeddingError` has no class) | `test_unexpected_failure_is_opaque` (opaque message retained) |
| 9 | `safe_json` helper wraps every `.json()` / `json.loads()` in the frontend (health, query error body, SSE data); degrades instead of crashing | frontend (dumb client) |
| 10 | Confirmed CI already runs `uv sync --locked` + `uv run --locked` throughout; documented as the lockfile-is-truth stance in `03-config-and-services §2` and `04 §4.7` | — |
| 7 | (was already fixed pre-review — see table above) | `test_non_dmc_name_rejected`, `test_scanner_ignored_file_rejected` |

Implementer self-review also added a `try/finally` staging-cleanup guard (beyond
the red-team list): an unexpected validator/index exception must not leak the
staging dir. No other new issues surfaced; retract-non-duplication, think-block
splitting across deltas, swap atomicity, and the CSRF no-Origin allowance were
each walked and hold.

## Part 2: Adjudication (Yi Xin — pending)

Accept all suggested revisions.
