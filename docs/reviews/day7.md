# Day 7 Red-Team Review & Adjudication

## Part 1: Red-Team Findings (non-implementing model, read-only review)

- Review target: `feat/day6` working tree, Day 7 self-healing repair agent —
  `src/learnarken/repair/` (`sandbox.py`, `apply.py`, `tools.py`, `agent.py`,
  `core.py`, `models.py`, `patch.py`, `config.py`, `prompt.py`), the
  `learnarken repair` CLI subcommand, `[tool.learnarken.repair]` in
  `pyproject.toml`, and `tests/test_day7_repair.py` / `test_day7_sandbox.py`.
  Spec: [docs/specs/day7.md](../specs/day7.md).
- Reviewing model: **Codex** (`codex exec --sandbox read-only`, cross-host via
  adversarial-review 0.5.0), reliability + security red team, 2026-07-17. The
  implementer (Claude) ran an independent host-side pass; tags: `[cross]` both
  caught it, `[external]` only Codex, `[host]` only the implementer.
- **External verdict (Codex): DO_NOT_MERGE** — "the nominal CLI path has a
  prompt, but the actual enforcement is not at the sandbox/write boundary."
- Threat-model note for the adjudicator: several findings assume an
  **adversarial input package** or a **direct/internal API caller** that
  bypasses the CLI. Constitution §2 records a *non-malicious input assumption*
  and §1.3 routes writes through the CLI's human gate — so part of adjudication
  is deciding which findings are in-scope for this slice vs. defense-in-depth
  to log as Planned. The implementer offers no accept/reject here (that is Part
  2, the human's).

| # | Grade | Tag | Finding | Location | Suggestion |
| --- | --- | --- | --- | --- | --- |
| 1 | P0/P1 | [cross] | **Sandbox Python does file I/O + network via *allowed* imports.** The AST denylist blocks `open`/`socket`, but `pathlib.Path.write_text()`/`read_text()` and `lxml.etree.parse(path_or_URL)` are reachable — so "no fs outside jail / no network" is not delivered. Exploit: `from pathlib import Path; Path('/tmp/pwned').write_text('x'); print(Path('/etc/passwd').read_text())`. | `sandbox.py:_assert_python_safe` / `config.py` allowlist | Drop `pathlib` from the allowlist; add `read_text`/`write_text`/`read_bytes`/`write_bytes`/`parse`/`write`/`unlink`/`open` etc. to forbidden attrs; or run real OS isolation. |
| 2 | P0/P1 | [external] | **Shell whitelist does not jail path/URL arguments.** Whitelisted `argv[0]` + an absolute/URL arg escapes: `cat /etc/passwd`, `grep root /etc/passwd`, `xmllint http://attacker/x.xml` (SSRF), `xmllint --output /tmp/pwn file.xml` (write). | `sandbox.py:_exec_shell` | Per-command argv schema: reject absolute paths, `..`, URLs, `--output`/recursive flags; resolve every file arg through `Sandbox.resolve`. |
| 3 | P1 | [external] | **Source symlinks are followed into the jail.** A package file `DMC-leak.xml -> ~/.env` is copied by `shutil.copy2` (follows links) into the jail, then `read_module` exposes the secret. | `sandbox.py:__init__` copy loop | `lstat`/`is_symlink` check; copy only regular files under the canonical package root. |
| 4 | P1 | [cross] | **Target-key binding is optional and LLM-controlled.** `propose_patch` trusts `args['target_key']`; if the LLM omits it, acceptance falls back to `bool(cleared)` — clearing *any* unrelated finding marks the patch accepted while the real target stays broken. | `tools.py:_propose_patch` / `agent.py` | Bind the target finding server-side (from the agent's loop context, not LLM args); reject missing/mismatched target. |
| 5 | P1 | [external] | **Patched file vs. reported file can diverge.** `propose_patch` verifies edits against `args['file']`, but `_run_apply_gate` groups edits under `patch.file` (= the finding's file). If they differ, apply writes to a different file than was verified. | `tools.py:_propose_patch`, `core.py:_run_apply_gate` | Enforce `args['file'] == finding.file` (patch only the finding's own file), or record and carry the actually-patched file. |
| 6 | P1 | [cross] | **Apply writes are not path-validated; the write primitive doesn't itself enforce the gate.** `verify_and_apply(pkg, {'../victim.xml': edits})` would read/write outside the package; and any direct importer bypasses the CLI's human gate. | `apply.py:verify_and_apply` / `_atomic_swap`; `core.py:107` | Validate each filename is a known top-level package `*.xml` (no separators); recompute risk-tier and require an approval token *inside* the write primitive. |
| 7 | P1 | [cross] | **Risk tier is trusted from `patch.risk_tier`.** The apply gate reads the serialized field rather than recomputing from `rule_id`; a forged/corrupted `ProposedPatch(rule_id='XREF-004', risk_tier=APPLY_ELIGIBLE)` would pass. | `core.py:_run_apply_gate`, `models.py:risk_tier_for` | Recompute `risk_tier_for(patch.rule_id)` at the apply boundary; never trust the stored tier. |
| 8 | P1 | [cross] | **`sandbox_mem_mb` is dead config; output capture is unbounded before slicing.** No `setrlimit`, so sandboxed Python can allocate/print GBs and OOM the host before the timeout fires. | `sandbox.py:_run`, `config.py` | `preexec_fn` setting `RLIMIT_AS`/`RLIMIT_CPU`/`RLIMIT_FSIZE`; bound stdout/stderr while reading; kill the process group. |
| 9 | P1 | [cross] | **Over-repair guard uses lossy set keys `rule@file@path`** (L3 findings have `path=''`), dropping line/severity/message and collapsing duplicates. A same-class second finding in one file makes a legit single fix look un-cleared; a mutated-in-place finding can hide from `introduced`. | `tools.py:finding_key`, `_propose_patch` | Multiset fingerprint incl. line + severity + message; require all non-target findings unchanged. |
| 10 | P1 | [external] | **TOCTOU between preview validation and swap.** Another process mutating the package after `after = _baseline_keys(preview)` but before `_atomic_swap` lands new findings despite the "zero new findings" proof. | `apply.py:verify_and_apply` → `_atomic_swap` | Lock the package dir; record digests/inodes at preview, recheck immediately before `os.replace`. |
| 11 | P1 | [external] | **Recovery trusts any `.bak`.** `recover_interrupted_apply` restores from any `*.bak` present — a dropped `DMC.xml.bak` overwrites active XML with no validation/gate. | `apply.py:recover_interrupted_apply` | Journal the files this process backed up; restore only those; `O_NOFOLLOW`/`lstat` against symlinks. |
| 12 | P1 | [external] | **Non-exec tools lack argument caps.** `search_corpus(k=10**9)` or a pathological XPath burns CPU/memory outside the sandbox timeout. | `tools.py:_search_corpus`, `_query_xml` | Clamp `k`; bound XPath length; run tool calls under the same watchdog. |
| 13 | P2 | [host] | **Token-budget breaker is a no-op when the LLM reports `total_tokens=0`** (some proxies / M3 stream mode); no global wall-clock budget. The iteration cap still bounds the loop. | `agent.py:repair_finding`, `minimax_llm` | Estimate tokens locally when usage is absent; add an optional wall-clock budget. |
| 14 | P2 | [external] | **Config accepts unbounded budgets** (`max_iterations=999999999`) — finite but operationally unbounded. | `config.py:load_repair_config` | Clamp to sane maxima. |
| 15 | P2 | [external] | **`Sandbox.diff()` reads `source/name` with no jail check** — a direct API caller could `diff('../secret.xml')`. | `sandbox.py:diff` | Reuse the jail filename validator for source-side paths too. |
| 16 | P3 | [host] | **Oversized files are copied into the jail before any size check** (loader's `MAX_FILE_BYTES` is enforced later by the validator), a minor disk-exhaustion vector. | `sandbox.py:__init__` | Skip/refuse files over the cap during the copy. |

### Cross-validation summary

- `[cross]` (both): #1, #4, #6, #7, #8, #9.
- `[external]` (Codex only): #2, #3, #5, #10, #11, #12, #14, #15.
- `[host]` (implementer only): #13, #16.
- Highest-severity taken on disagreement (Codex graded #1 P0; implementer P1 —
  recorded as P0/P1 pending adjudication).

### Implementer note on scope

The strongest concrete holes reachable **through the normal CLI + our own M3
loop** (not requiring an adversarial package or a bypassing caller) are #1
(pathlib/lxml I/O), #2 (shell arg jailing), #4 (target-key binding), #5
(file divergence), #8 (mem limit), and #9 (guard fingerprint). #3, #6(traversal
half), #10, #11, #15 assume adversarial input or a direct importer that §2's
non-malicious-input assumption partly excludes — the adjudicator decides
in-scope vs. Planned. No fixes have been applied; that follows adjudication.

## Part 2: Adjudication (transcribed from Yi Xin's instruction; human to verify)

> **Provenance**: this table is **transcribed** from Yi Xin's 2026-07-17 verbal
> instruction "修正红队指出的问题" (fix the problems the red team pointed out) —
> a blanket accept-and-fix. It is **not** AI-authored rationale (INV-6). Per
> INV-6 the human still **re-runs/verifies each claim before merge**; the
> "Fix" column records what the implementer changed, not a human sign-off.
> All fixes are applied on `feat/day6`; `make lint` + `make test` green (246
> passed / 8 skip, incl. 4 new hardening tests). Live-verified: sandbox now
> blocks pathlib import, `lxml.etree.parse` (file + URL), and `cat /etc/passwd`.

| # | Decision | Fix applied |
| --- | --- | --- |
| 1 | Accept & fixed | Dropped `pathlib`/`sys` from the import allow-list; added file/network methods (`read_text`/`write_text`/`parse`/`urlopen`/…) + `getattr` to the AST denylist — `sandbox.py`, `config.py`, `pyproject.toml`. |
| 2 | Accept & fixed | `_assert_shell_arg_safe`: every arg rejected if absolute / `..` / URL / non-safe flag; relative file args resolved through the jail — `sandbox.py:_exec_shell`. |
| 3 | Accept & fixed | Symlinked source files refused on copy; icn copied file-by-file skipping symlinks — `sandbox.py:__init__`. |
| 4 | Accept & fixed | Target key bound server-side on the sandbox by the agent; `propose_patch` requires the bound target cleared, ignores LLM-supplied `target_key` — `agent.py`, `tools.py`. |
| 5 | Accept & fixed | `propose_patch` rejects any patch whose file ≠ the finding's bound file — `tools.py`. |
| 6 | Accept & fixed | `verify_and_apply` jails every filename to a real, non-symlink top-level module (`_validated_targets`) — `apply.py`. |
| 7 | Accept & fixed | Apply gate recomputes `risk_tier_for(rule_id)` instead of trusting `patch.risk_tier` — `core.py:_run_apply_gate`. |
| 8 | Accept & fixed | `preexec_fn` sets `RLIMIT_AS`/`RLIMIT_CPU`/`RLIMIT_FSIZE`; `mem_mb` default raised to 1024 so limits don't break interpreter start — `sandbox.py:_set_limits`. |
| 9 | Accept & fixed | `finding_key` now includes line + severity + message; over-repair diff uses `Counter` multisets — `tools.py`. |
| 10 | Accept & fixed | `_atomic_swap` re-reads each active file and aborts (fail closed) if it changed from the preview-validated bytes — `apply.py`. |
| 11 | Accept & fixed | Recovery restores only backups named in a journal this process wrote; stray `.bak` ignored — `apply.py`. |
| 12 | Accept & fixed | `search_corpus` clamps `k≤20`; `query_xml`/`propose_patch` cap XPath length — `tools.py`. |
| 13 | Accept & fixed | `minimax_llm` estimates tokens (~4 chars/token) when the proxy reports none, and charges a contract-error step — `agent.py`. |
| 14 | Accept & fixed | `load_repair_config` clamps `max_iterations≤100`, `max_tokens≤500k`, `timeout≤60s`, `no_progress≤20` — `config.py`. |
| 15 | Accept & fixed | `Sandbox.diff` validates the source-side name via `_safe_basename` — `sandbox.py`. |
| 16 | Accept & fixed | Oversized files (`> MAX_FILE_BYTES`) skipped during the jail copy — `sandbox.py:__init__`. |
