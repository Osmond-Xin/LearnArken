# Day 1 Red-Team Review & Adjudication

## Part 1: Red-Team Findings (non-implementing model, read-only review)

- Review target: `feat/day1-skeleton` vs `main` (full diff, uv.lock excluded)
- Reviewing model: **Codex** (`codex exec --sandbox read-only` via
  adversarial-review plugin); implementer was Claude (Opus 4.8 session)
- Inputs: diff + docs/specs/day1.md + docs/constitution.md (INV-1..8)
- Cross-validation: host (Claude) ran an independent pass; tags below

| # | Grade | Finding | Location | Suggestion | Tag |
| --- | --- | --- | --- | --- | --- |
| 1 | P1 | Spec says interfaces "pending Yi Xin's final approval" but the branch implements them — approval state not recorded (INV-6) | docs/specs/day1.md header; cli.py | Record Yi Xin's approval (given verbally as "开工吧" in session) in the spec status line before merge | cross-validated |
| 2 | P1 | "Exactly once" violation semantics leak: DML re-lists the malformed `2X` code and the `SS200` code, so a Day 2 validator scanning all dmCodes could double-count VIO-4/VIO-6 (INV-3) | package-b DML lines 47-52, 65-70 vs README manifest | Define violation identity by carrier DM only (amend manifest rules), or restructure DML | external-only |
| 3 | P1 | XML parser unhardened: stdlib ElementTree accepts internal entity expansion (billion-laughs DoS); no size/count caps | package.py:10, 81-83 | Use defusedxml, add malicious-XML test; mandatory before Day 2 ingestion gate | external-only |
| 4 | P1 | README overclaims: "The system provides" validation/QA/repair — none implemented at v0.1.0 (INV-7) | README.md scenario section | Reword to planned-tense; Implemented list stays empty until artifacts exist | external-only |
| 5 | P1 | Tests only pin 3 of 6 VIO carriers; VIO-1/2/3 files could be deleted/mistyped silently (INV-3) | tests/test_inspect.py:53-60 | Add a test asserting the full carrier-file set matches the manifest | external-only |
| 6 | P2 | Malformed DM still exits 0: parse errors become table rows but CLI reports success | package.py:84-92; cli.py:46 | Non-zero exit (or explicit degraded status) when any DM has a parse error | cross-validated |
| 7 | P2 | Non-standard `learnarkenExtension` comment present in package-a files but missing in all package-b files (INV-7, spec §Interfaces) | package-b DM files | Add the labeling comment to package-b DMs | external-only |
| 8 | P2 | CI not locked: `uv run` without `--locked`; actions pinned by tag not SHA | ci.yml; pyproject ranges | `uv sync --locked` + `uv run --locked`; SHA-pin actions | external-only |
| 9 | P2 | Terminal injection: DM titles printed raw; ANSI control chars in a title could corrupt terminal/log output | package.py:100; cli.py:25-29 | Strip control characters in human output | external-only |
| 10 | P2 | `samples/README.md` stale: claims "no authored/synthetic XML" (now false), and contains absolute `file:///Users/...` links leaking the local username (INV-7; adjacent INV-1) | samples/README.md:9, 22-41 | Rewrite around package-a/b + attribution + kibook exclusion; relative links only | cross-validated (host also flagged the local-path leak) |

**Red-team verdict**: DO_NOT_MERGE (until #1 approval state, #2 manifest
exactness, #3 parser hardening, #4 README overclaims are resolved)

**Numbers reported by red team** (must be re-run by Yi Xin per INV-6):
- ruff check + format: pass
- package counts probed: package-a = 8 DM / 1 PM / 1 DML; package-b = 7 / 1 / 1
- (Codex could not run pytest in its read-only sandbox; host ran `uv run
  pytest`: 11 passed — re-run yourself with `make test`)

---

## Part 2: My Adjudication (human-written, non-delegable — INV-6)

> Rulings dictated by Yi Xin in the working session (2026-07-13, Chinese);
> transcribed by AI with content unchanged.

| # | Ruling | Rationale (one sentence) |
| --- | --- | --- |
| 1 | accept | Approval was given verbally but never recorded — record it. |
| 2 | accept | Fix by defining violation identity by carrier DM in the manifest rules. |
| 3 | accept | Harden the parser now; it becomes the ingestion gate on Day 2. |
| 4 | accept | INV-7 is my own rule; reword to planned tense. |
| 5 | accept | The manifest is the validator's exam — tests must pin all six carriers. |
| 6 | accept | Parse errors with exit 0 would mislead automation; add a distinct exit code. |
| 7 | accept | The spec requires the non-standard label comment in every file. |
| 8 | accept | Lock CI dependency resolution and pin actions. |
| 9 | accept | Cheap fix; strip control characters in human output. |
| 10 | accept | The stale claim is now false and the absolute paths leak a local username. |

**Design decision arising from this review** (Yi Xin): the review exposed an
implicit assumption — this project treats input documents as **non-malicious**.
Errors are misplaced, malformed, or outdated documents, not deliberate
poisoning by an adversary. For a learning system this assumption is
reasonable, and we lack the experience to enumerate poisoning defenses today.
Decision: do **not** build dedicated anti-poisoning validation; leave an
explicit **placeholder method** in the code to mark that the direction was
considered and where such checks would live. Recorded in constitution §2 and
docs/discussions/day1.md (D7).

**Number re-run record** (every number the red team reported, re-run by me):

- `make test` → **15 passed** (run by Yi Xin, 2026-07-13) — matches
- `learnarken inspect samples/package-a` → **DM 8 / PM 1 / DML 1** (run by
  Yi Xin, 2026-07-13) — matches red-team probe

**Final decision**: all 10 findings reworked and verified — **merge** and tag
`v0.1.0`.
