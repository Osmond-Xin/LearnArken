# Day 2 Red-Team Review & Adjudication

## Part 1: Red-Team Findings (non-implementing model, read-only review)

- Review target: branch `day2-model-validator` vs `main` (PR #2)
- Reviewing model: **Codex** (`codex exec --sandbox read-only`, cross-host via
  adversarial-review 0.5.0), 2026-07-14
- Inputs: full Day 2 source (models/loader/validation/cli) + day-2 SPEC +
  constitution
- Cross-validation: the implementer (Claude) ran an independent host-side
  pass **before** reading Codex's output; tags below record who caught what.
  Findings tagged `[host-only]` come from the implementer's self-review and
  are honestly labeled as such — they are supplements, not Codex findings.
- ✅ = reproduced/verified by a concrete experiment before filing (command or
  scenario noted); unverified claims carry the partner's reasoning only.

| # | Grade | Tag | Finding | Location | Suggestion |
| --- | --- | --- | --- | --- | --- |
| 1 | P1 | external-only | DML registrations are never checked for target existence, and XREF-003 skips entries whose DM or issueInfo is missing — a DML registering a nonexistent DM validates clean (fail-open at the ingestion gate, INV-4). NB: fixing this adds a finding class, which under INV-3 needs a VIO entry or explicit scope-out | engine.py `_crossfile_findings` XREF-003 block | add DML target-resolution check (new VIO class or Day 3 scope decision) |
| 2 | P1 | external-only | Duplicate DMCs silently overwrite in `dm_index()` — two files claiming the same DMC collapse to one; refs resolve ambiguously and one module vanishes from Day 3 chunking/KG. Directly undercuts the superseded-versions story (constitution §1) | models.py `dm_index`, engine.py dm_files | emit a duplicate-identity error before graph checks |
| 3 | P1 | cross-validated | Module-level cached `XMLSchema` + post-hoc `error_log` read is not thread-safe; concurrent validations can interleave logs → a bad file can slip through with `schema_ok=False` but no recorded finding (fail-open). Single-threaded CLI is safe **today**; Day 6 FastAPI is the blast radius | engine.py `_get_schema` / L1 block | per-call schema instance, or lock around validate+copy(error_log) |
| 4 | P1 | external-only | No resource limits: files are parsed twice in full, no cap on file size / file count / ref count. A 500 MB well-formed XML exhausts CPU/RAM before findings. Constitution §2 assumes non-malicious inputs, but parser-hardening for format-level hazards is explicitly in scope | loader.py `parse_file`, engine.py file loop | byte/count caps that fail closed with a resource finding |
| 5 | P1 | external-only | BREX-001 accepts *any* warning/caution anywhere in the procedure, not a *preceding* or hazard-specific one — an unrelated caution in a later step suppresses a missing accumulator-discharge warning. The SPEC labels the rule a toy heuristic, but the manifest wording promises "preceding warning" semantics | rules.py `_check_hazard_warning` | enforce preceding/local semantics, or align manifest+SPEC wording to the weaker rule |
| 6 | P2 | external-only ✅ | Bare DTD passes the defusedxml gate (`forbid_dtd` defaults to False; entities/external are blocked but a plain `<!DOCTYPE …>` is accepted) — policy says "no DTD", implementation diverges. Verified: DOCTYPE file parses through `parse_file` | loader.py `SafeET.parse(path)` | `SafeET.parse(path, forbid_dtd=True)` |
| 7 | P2 | external-only ✅ | Cycle finding prints the sorted SCC joined as a chain, fabricating edges: real cycle a→c→b→a is reported "a → b → c → a" where edge a→b does not exist. Verified with a 3-node cycle | engine.py XREF-005 message | report as "cycle component {members}" or reconstruct an actual path |
| 8 | P2 | cross-validated | Malformed dates (`issueDate`, extension dates) silently become `None`; BREX-005 then skips — invalid data passes with no finding and Day 3 sees "unknown" instead of "invalid" | loader.py `_iso_date`/`_issue_date`, rules.py BREX-005 | surface unparseable dates as findings |
| 9 | P2 | host-only ✅ | A DM file that fails L1 *and* cannot be modeled (e.g. no dmCode) drops out of the L3 node set, so every file referencing it gets a spurious XREF-001 cascade — deviates from the SPEC's "L1-failed file remains a graph node". Verified: 2-file package yields SCHEMA-001 + XREF-001 | engine.py model-building `except ValueError` | derive the node key from the filename when the model cannot be built |
| 10 | P2 | cross-validated | Human-output sanitization gaps: package path in `validate` header, error strings, and the `dm` stderr "available:" DMC list are printed unsanitized (filenames/dir names are the realistic escape-code vector; XML 1.0 blocks raw control chars in attributes) | cli.py `_render_validation_human`, `_cmd_dm` | route every human-output field through `_sanitize` |
| 11 | P2 | cross-validated | `load_package()` silently skips unparseable files (docstring warns, but nothing at the call site enforces it) — Day 3 chunker could index an incomplete package unknowingly | loader.py `load_package` | return diagnostics or make tolerance opt-in and noisy |
| 12 | P3 | host-only | Model building catches only `ValueError`; any unexpected exception (e.g. pydantic ValidationError on pathological input) aborts the whole package run instead of becoming a per-file finding | engine.py model-building block | broaden the catch, convert to finding |
| 13 | P3 | external-only | Runtime deps declare lower bounds only; `uv.lock` + CI `--locked` mitigate, but unlocked installs can drift parser behavior | pyproject.toml | document locked-install requirement; consider upper bounds |
| 14 | P3 | host-only | TOCTOU between the defusedxml gate and the lxml re-parse (file swapped between parses bypasses the gate) — theoretical under the non-malicious-input assumption | loader.py `parse_file` | parse bytes once into memory, feed both parsers |

Numbers Codex reported (re-run required by the human per protocol):
`package-b` = 6 errors + 1 warning = 7 findings, mapping 1:1 to VIO-1..7;
CLI exits 0 (package-a) / 1 (package-b) / 2 (not a package); 46 tests green
(Codex could not run pytest in its sandbox; count is from the implementer).

**Red-team verdict (Codex): DO_NOT_MERGE** — until the P1 fail-open paths
are fixed or explicitly scoped out by adjudication. Host note for the
adjudicator: findings 3/4 presume concurrency or resource-adversarial inputs
that constitution §2 partially scopes out for today; findings 1/2 are
in-scope correctness fail-opens; findings 6/7/9 are cheap, verified fixes.

---

## Part 2: My Adjudication (human-written, non-delegable — INV-6)

| # | Ruling | Rationale (one sentence) |
| --- | --- | --- |
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 6 | | |
| 7 | | |
| 8 | | |
| 9 | | |
| 10 | | |
| 11 | | |
| 12 | | |
| 13 | | |
| 14 | | |

**Number re-run record** (every number the red team reported, re-run by me):

- `uv run learnarken validate samples/package-b --json` → ___ errors / ___ warnings → matches / mismatch
- `uv run learnarken validate samples/package-a` → exit ___ → matches / mismatch
- `make test` → ___ passed → matches / mismatch

**Final decision**: merge / rework (scope: …)
