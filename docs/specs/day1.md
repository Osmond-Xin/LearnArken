# Day 1 SPEC — Skeleton, Samples & Project Constitution (v0.1.0)

> **Authorship note (INV-6)**: the decision layer below was authored by
> Yi Xin in the 2026-07-12 working session (dictated in Chinese); AI
> transcribed and translated it with content unchanged. The Interfaces
> section is AI-drafted.
> **Status: APPROVED by Yi Xin** — verbally in the working session ("开工吧",
> including the 8+7 sample sizing), recorded here 2026-07-13 after red-team
> finding #1 flagged the missing record (docs/reviews/day1.md).
> Discussion record: [docs/discussions/day1.md](../discussions/day1.md).

## Goal (one sentence) — [HUMAN]

Create the project: governance scaffolding, Python skeleton, synthetic sample
packages, and a minimal `inspect` CLI — committed to git and tagged `v0.1.0`.

## Key Decisions & Constraint References — [HUMAN]

**Background story** (now codified in [constitution §1](../constitution.md)):
an aviation MRO company's engineers search for maintenance procedures on-site,
laptop beside the aircraft — **latency and recall are the top-ranked
requirements**. Input material is the company's training manuals (S1000D-style
packages), which accumulate superseded versions; the data model must
distinguish and filter old versions.

Decisions made today:

1. **Fail-closed ingestion gate**: the system only *detects and reports*
   deviations from S1000D — no auto-processing, no inference, no
   summarization, no maintenance. Rejected documents get an error stating the
   deviation; a human decides. Only compliant documents enter the knowledge
   base. This guards against: superseded versions, non-compliant documents,
   and out-of-domain documents (e.g. ship maintenance) → **VIO-6 added**;
   VIO-1–5 confirmed as drafted (constitution §4 now CONFIRMED).
2. **BREX = basic Schematron only**: I am not yet deeply familiar with
   S1000D, so BREX gets the most basic implementation (default Schematron
   approach). Decision recorded today; implementation lands Day 2.
3. **DM metadata fields** (modeled Day 2): DMC, title, issueInfo, language,
   security classification, applicability, QA status — standard S1000D;
   **effectiveDate, expiryDate — project extensions, labeled non-standard**
   (they carry the expired-document scenario).
4. **DM content types** (modeled Day 2): descriptive, procedural (with
   steps), fault isolation, IPD, plus warnings/cautions and abnormal-handling
   sections.
5. **CLI capability split across days**: Day 1 = `inspect` (document counts +
   per-DM basics); Day 2 = full metadata model + SQL-SELECT-like queries
   (e.g. DMC count, earliest effective date, latest expiry date); Day 3 =
   chunk counts (chunks don't exist before the chunker).
6. Constitution rules in force today: INV-1 (synthetic samples only), INV-3
   (enumerated violations), INV-7 (honest layering), INV-8 (slippage rule).

The 3 tutorial concepts to verify during implementation *(from Yi Xin's
tutorial notes in docs/tutorials/learn-record.md, transcribed verbatim)*:

1. 多线程、GIL、multiprocess
2. 从文档抽取出来的中间模型如何评估设计好坏
3. 是否能够从结构上解决多线程的问题;是否多线程是必要的

## Interfaces — [AI-DRAFTED, pending review]

**Repository skeleton**

```text
pyproject.toml            # project metadata, ruff config, pytest config
src/learnarken/           # package source; CLI entrypoint `learnarken`
tests/                    # pytest suites (smoke tests today)
Makefile                  # make test, make lint
.github/workflows/ci.yml  # ruff check + pytest on push/PR
.pre-commit-config.yaml   # ruff + basic hygiene hooks
```

**CLI**

```text
learnarken inspect <package-dir> [--json]
```

- Human output: package name; counts by document kind (DM / PM / DML);
  a table of data modules: DMC | title | issue | language.
- `--json`: same content as structured JSON (sets the pattern Day 2's
  `validate` will follow).
- Exit codes: 0 = inspected OK; 2 = directory is not a package
  (missing or contains no recognizable S1000D-like files).
- Day 1 parses only what the table needs (dmCode, tech name/info name,
  issueInfo, language) directly from XML — the full Pydantic model is Day 2.

**Synthetic samples** (structure follows S1000D 4.x core element semantics:
`dmodule` → `identAndStatusSection`/`content`, `dmAddress`, `dmCode`,
`issueInfo`, `language`, `dmStatus` with `security`/`qualityAssurance`/
`applic`)

- `samples/package-a` (valid): 8 DMs — 2 descriptive, 3 procedural (with
  steps + warnings), 2 fault isolation, 1 IPD — plus 1 PM and 1 DML.
  Procedural DMs cross-reference each other and the IPD (gives Day 2's
  reference checks and Day 3's retrieval something real to work on).
- `samples/package-b` (invalid): 7 DMs + 1 PM + 1 DML; each of VIO-1 – VIO-6
  appears exactly once (one DM carries the ship-maintenance VIO-6), documented
  in a `samples/package-b/README.md` violation manifest.
- Both packages include the labeled extension fields (`effectiveDate`,
  `expiryDate`) with a comment marking them non-standard.

## Acceptance Criteria (checkable one by one) — [HUMAN]

- [ ] Governance docs committed: constitution, CLAUDE.md, redteam.md, three
      templates, discussions/day1.md, this SPEC
- [ ] `learnarken inspect samples/package-a` prints the package summary
      (counts + DM table); `--json` variant works
- [ ] package-a is valid; package-b contains exactly VIO-1 – VIO-6, each
      documented in its violation manifest
- [ ] Smoke tests for both packages pass; CI (ruff + pytest) green
- [ ] Everything committed to git: feature branch → PR → squash merge →
      tag `v0.1.0` with release notes

## Explicitly Out of Scope (today) — [HUMAN]

- **No implementation-detail / infrastructure decisions**: no vector-database
  selection, no AWS-or-not, no Docker-or-not — each is decided on the day
  that needs it
- No XSD or Schematron validation (Day 2)
- No metadata query engine / SQL-SELECT-like queries (Day 2)
- No chunking, no chunk counts, no retrieval, no knowledge-base storage
  design (Day 3+)

## Risks & Open Questions

**Accepted risks — [HUMAN] (stated by Yi Xin, 2026-07-12):**

- **R1 — No expert ground truth for S1000D compliance.** I am not familiar
  with S1000D, so I cannot personally perform true verification that the
  validator's judgment of "compliant" is correct.
- **R2 — Standard-premised pipeline may drift.** All knowledge-base admission
  and retrieval is premised on S1000D compliance; because of R1 this premise
  cannot be truly verified, which could propagate into overall drift and
  modeling failure downstream.
- **R3 — Accepted, with the real-world control named.** For a learning/demo
  project this error class is acceptable. In a real project there would be a
  second confirmation loop: business stakeholders and engineering management
  jointly estimating and confirming the S1000D document scope, standard
  coverage, content, and even volume. That loop is deliberately dropped here.
- **R4 — The scenario is simulated, not engineered.** "On-site" is assumed
  but concurrency is not considered and no retrieval-latency target (SLO) is
  defined — everything remains a simulation, not a real production tool.
- **R5 — No target environment, budget, or offline planning.** We have not
  specified what machine this runs on (2-core/4 GB? 4-core/8 GB? something
  else?), so all latency numbers and the runtime environment are in a
  learning state with no real engineering scenario behind them. There is no
  budget scenario either. And in the extreme on-site case a disconnected
  (offline) mode might be required — none of these scenarios are included in
  the current project.

**Open questions:**

- Sample sizing (8 + 7 DMs) is an AI proposal — Yi Xin confirms or adjusts at
  spec approval.
- The "3 tutorial concepts" slots are unfilled until the learning step is done.
- Day 2 will need a Schematron tooling choice (e.g. lxml's isoschematron) —
  record it in Day 2's spec, not today.
