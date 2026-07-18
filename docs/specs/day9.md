# SPEC — Day 9: Evidence Chain & Machine Readability (`v0.9.0`)

> Decision layer **transcribed from Yi Xin's verbal instructions** (2026-07-18
> session) plus three rulings given via the day's clarifying questions. Goal and
> Key Decisions are [HUMAN, transcribed]; Interfaces / Acceptance / Out-of-Scope /
> Verification are **AI-drafted, pending approval** (Day 6/7/8 labeling
> precedent). Nothing in the decision layer is AI-invented — the three
> constraint-sensitive tensions (T1 INV-1 resume boundary, T3 graph slice, T2
> evidence drift) were **ruled by Yi Xin** before drafting; their rulings are
> transcribed verbatim in Key Decisions. Distilled to
> [docs/discussions/day9.md](../discussions/day9.md).
>
> **Daily-cycle note.** Step 1c 扫 ([docs/research/day9-unknowns.md](../research/day9-unknowns.md))
> was completed **before** this SPEC. Its six tensions (T1–T6) fed the clarifying
> questions; T1/T2/T3 were adjudicated (see Key Decisions), T4 is folded into the
> graph scope, T5 (AGENTS.md) is resolved as out-of-scope, T6 (acceptance) is
> pinned by the Goal below.
>
> **Constitutional note.** Day 9 is almost entirely a **documentation /
> indexing** day — it does not build new capability, it makes the capability
> already in the repo **machine-verifiable**. The single code deliverable is the
> dependency-graph impact query (ADR-0002, pulled to today). INV-1 governs the
> EVIDENCE.md resume boundary (Decision 1); INV-5 governs number reproducibility
> (Decision 3); INV-8 governs graph-slice slippage (Decision 2).

## Goal (one sentence) — [HUMAN, transcribed 2026-07-18]

Make the repository **machine-verifiable to a hiring-side AI agent**: author a
root **`llms.txt`** repo map, a **`docs/EVIDENCE.md`** claim→evidence matrix, and
a **`docs/AI-COLLABORATION.md`** AI-first-workflow writeup (explicitly using the
term *adversarial validation* and distinguishing it from its traditional ML
sense); add a **minimal Neo4j dependency-graph impact query** (extract S1000D
inter-module `dmRef` relations into Neo4j, answer "if DM X is superseded, which
procedures are affected?" as a **parallel Graph-RAG interface option**); review
the `specs/reviews/journal` directories for gaps; such that a **stranger AI agent
— concretely MiniMax, invoked via the `minimax` CLI (`minimax code`) or the
project's MiniMax config — reading only `llms.txt` + `EVIDENCE.md` can locate the
reproduction command for any benchmark number within 5 minutes** — tagged
`v0.9.0`.

## Key Decisions — [HUMAN, transcribed from the 2026-07-18 instructions + rulings]

1. **EVIDENCE.md keeps resume text out of the public repo (T1 ruling: "公开放
   抽象能力声明,简历留私档指回").** The public `docs/EVIDENCE.md` lists only
   **abstracted capability claims → repo evidence** — no verbatim resume numbers
   or phrasing. Resume lines map onto those public anchors from the
   **non-committed `resume-master/`** private doc (INV-1: personal job-search
   documents never enter the repo). The hiring-side agent verifies against the
   public matrix; the resume side points inward, never outward. This satisfies
   execution-plan's "简历行" requirement without a red-line breach.

2. **Graph impact query: standalone CLI, bounded depth, cycle-safe, parallel
   option (T3 ruling: "独立 CLI + 限深 + 环去重 + 并联选型").** The impact query is
   a **standalone CLI command** (`learnarken graph impact <DMC>`), a reverse
   `dmRef` traversal answering "who depends on X" with **bounded depth**
   (`REFS*1..N`, N configurable) and **visited-node de-duplication** so
   package-b's deliberately-injected VIO-7 cycles cannot loop. It **fails closed**
   when Neo4j is unreachable (INV-4). It is wired as **one parallel Graph-RAG
   interface option** (tutorial 06 §9 interface ①-direction) — **not** merged into
   the main answer pipeline. Toy-scale, but the interface is designed
   as-if-distributed (INV-2: bounded, de-duplicated, idempotent read). Per
   ADR-0002 + INV-8, if the day overruns this slice is the first item cut back to
   a documented design sketch.

3. **Evidence drift is guarded by an automated test (T2 ruling: "加 pytest:死链 +
   数字一致性").** A lightweight `pytest` asserts that (a) every repo path
   referenced by `EVIDENCE.md` / `llms.txt` **exists** (no dead links, DR pitfall
   #2) and (b) key numbers asserted in `EVIDENCE.md` **match their source
   artifacts** (e.g. κ against `eval/results/day8-kappa.json`; DR pitfall #3 —
   claim-vs-source drift reads as dishonesty under machine audit). This is INV-5
   made continuously enforceable, so Day 10's directory reshuffle cannot silently
   break the evidence chain.

4. **EVIDENCE.md numbers come only from current-`main` frozen artifacts.** Never
   cite a superseded number from a historical handoff (Day 8 retracted its own
   `0.917→0.979` README figure — handoff §3). The single source of truth for each
   number is the committed artifact under `eval/results/` or `eval/golden/`.

5. **AGENTS.md stays out of scope (T5 resolved).** The DR frames `agents.md` as
   the "agent behaviour constitution"; that role is already played by `CLAUDE.md`
   + `docs/constitution.md`. execution-plan §Day 9 does **not** list an
   `AGENTS.md`; adding one is scope creep. `AI-COLLABORATION.md` and `llms.txt`
   instead **document that `CLAUDE.md` serves the agents.md role** — we have its
   substance, name it rather than duplicate it.

6. **Acceptance is measured with MiniMax as the stranger agent (T6).** The
   5-minute-locate criterion is verified by actually driving MiniMax (via the
   `minimax` CLI or the project's MiniMax config) over `llms.txt` + `EVIDENCE.md`
   and checking it can name the reproduction command for a sampled benchmark
   number. MiniMax is the generator elsewhere (Day 8) but here it only *reads
   docs* — no self-judging tension.

7. **Review sweep is corrective, not creative.** The `specs/reviews/journal`
   gap-review only fixes provenance/label/dead-link gaps and files Day 8 backlog
   into the Roadmap. AI **never** touches `docs/journal/` content (INV-6); the
   Day 8 journal header placeholder (`Day N — <date>`) is **flagged for Yi Xin**,
   not edited by AI.

---

## Interfaces — [AI-drafted, pending approval]

### 1. `docs/EVIDENCE.md` — claim → evidence matrix

Machine-first, indexed by outward claim. Columns:

| Column | Meaning |
| --- | --- |
| Claim | Abstracted capability statement (no resume verbatim, Decision 1) |
| Category | DR evidence tier → project honesty layer (below) |
| Number(s) | The benchmark figure(s), copied from the frozen artifact only |
| Evidence | Repo path(s): golden set / result JSON / trace / ablation table |
| Reproduce | Copy-pasteable command (INV-5) |
| Layer | `Implemented` / `Toy-scale` / `Planned` (INV-7) |

DR tier → project layer mapping (stated once at the top of the file):

- **Public fact** → stable, externally checkable (tag, version) → `Implemented`.
- **Disclosure** → number tied to a specific golden set + result JSON + commit →
  `Implemented` / `Toy-scale`.
- **Derived logic** → number produced by a repro script over a frozen dataset →
  `Toy-scale`.
- **Hypothesis** → design-only, no artifact → `Planned` (explicitly labelled).

Rows to include (non-exhaustive, drawn from current `main`):
- Retrieval ablation (Recall@k / nDCG / zero-hit) → `README` retrieval table,
  `eval/golden/`, repro command.
- Embedding-provider comparison (Qwen3-8B vs BGE-M3 vs MiniMax remote).
- End-to-end RAG mode table incl. p50 latency.
- Day 8 κ calibration (Codex 0.737 / agy 0.667) → `eval/results/day8-kappa.json`,
  `tools/adversarial_eval.py --kappa-only`.
- Day 8 X-01 aggregation-defect determinism (3/3→0/3) + judge groundedness
  (0.53→0.63) → `docs/notes/day8-defects.md`, frozen artifacts.

A top-of-file **"Start here" block** tells a reading agent: how the matrix is
organised, that every number links to a frozen artifact, and how to run any
reproduce command — this is what makes the 5-minute-locate acceptance pass.

### 2. `docs/AI-COLLABORATION.md` — AI-first workflow writeup

Sections:
1. **The daily seven-step cycle** (learn → spec(human) → implement(AI) →
   red-team(independent model) → adjudicate(human) → verify → journal(human)),
   pointing at real examples in the repo.
2. **Worked examples** — a real SPEC decision layer (`docs/specs/`), a real
   red-team Part 1 + human adjudication Part 2 (`docs/reviews/`), the three
   understanding gates (spec authorship / finding adjudication / number re-run).
3. **What must be human** — checklist: SPEC decision layer, adjudication,
   journal, number re-run (INV-6); why these are the *unforgeable human output*
   (DR §"不可伪造的人类产出").
4. **Adversarial validation — term card (explicit, per execution-plan).** State
   both senses: **traditional ML** = offline classifier detecting train/test
   **distribution shift**; **governed-AI (2025–26)** = *cognitive/executive
   separation* defence architecture (model proposes, runtime holds the
   authorization boundary; graduated determinism). Map the project's three-layer
   practice: critic-attacks-answer (Day 5) / attack-the-evaluation (Day 8) /
   red-team-attacks-code (daily cross-host review). Note the resume uses the
   governed-AI sense (private doc).
5. **CLAUDE.md as the agents.md-role file** (Decision 5).
6. **Supply-chain transparency** — `Co-Authored-By` on every AI commit is already
   practice (`git log --grep`), per DR §"激进透明度".

### 3. root `llms.txt` — AnswerDotAI standard

Structure per the standard: `# H1 project name` → `> blockquote` one-sentence
summary → optional prose → `## H2` sections of `[file](path): description` links
→ `## Optional` (droppable-under-context-pressure) section. Constraints:
- **Dry declarative sentences, no marketing** (DR pitfall #1).
- **Relative repo paths** (this is a repo, not a website — labelled honestly as a
  repo-adapted variant, INV-7); reading agent uses the filesystem.
- Link the **canonical English `README.md`** as primary; `README.zh-CN.md` goes
  under `## Optional` to avoid bilingual context bloat (DR pitfall #4).
- Point explicitly at `EVIDENCE.md` as the "how to reproduce any number" entry.

### 4. `learnarken graph impact <DMC>` — dependency impact query

- New function in `src/learnarken/graph/store.py`:
  `impact(dmc: str, depth: int = 3) -> ImpactResult` — reverse `dmRef` traversal
  returning affected DMs with their hop distance, fail-closed on `GraphError`
  (INV-4). **Implemented as a per-hop breadth-first walk** (one single-hop query
  per level, excluding already-visited nodes) rather than a variable-length
  `REFS*` pattern — cycle-safe by construction (VIO-7) and, crucially, it never
  enumerates whole paths, so a dense/cyclic graph cannot explode into a DoS
  (day9 red-team #1). Depth and a result cap (`MAX_IMPACT_RESULTS`) bound the
  work. Existence is split into `exists_in_corpus` (indexed module, carries a
  package) vs `exists_as_reference` (any graph node, incl. dangling refs — #6).
- New CLI subcommand `graph impact` wired into the existing CLI; prints the
  affected-procedure list (or an explicit refusal if Neo4j is down / DM unknown).
- Documented in `llms.txt` / `EVIDENCE.md` / tutorial cross-ref as Graph-RAG
  interface ①-direction, **parallel** to retrieval (not in the answer pipeline).

### 5. `tests/test_day9_evidence.py` — drift guard (Decision 3)

- **Dead-link test**: parse every `[text](path)` in `EVIDENCE.md` + `llms.txt`;
  assert each repo-relative path exists.
- **Number-consistency test**: for a curated set of key numbers asserted in
  `EVIDENCE.md`, assert equality against the source artifact (e.g. κ vs
  `eval/results/day8-kappa.json`).
- Plus graph-impact unit tests (cycle-safety on a VIO-7 fixture, depth bound,
  fail-closed when Neo4j down — the live-Neo4j path may `skip` when the container
  is absent, mirroring existing graph tests).

## Acceptance Criteria — [AI-drafted, pending approval]

1. `llms.txt`, `docs/EVIDENCE.md`, `docs/AI-COLLABORATION.md` exist, correctly
   structured, marketing-free, honestly layered.
2. **5-minute-locate**: MiniMax (via `minimax` CLI / project config), reading only
   `llms.txt` + `EVIDENCE.md`, names the correct reproduction command for a
   sampled benchmark number. Recorded as evidence.
3. `learnarken graph impact <DMC>` returns the correct affected-DM set on the
   synthetic corpus, is cycle-safe on a VIO-7 fixture, respects the depth bound,
   and fails closed when Neo4j is unreachable.
4. `tests/test_day9_evidence.py` green: no dead links, no number drift.
5. `make test` + `make lint` green; existing 268+9 suite unbroken.
6. The `specs/reviews/journal` sweep is filed; Day 8 backlog is in the Roadmap;
   the Day 8 journal header issue is flagged to Yi Xin (not AI-edited).
7. Cross-host `coding-adversarial-review` run on the day's diff, findings written
   to `docs/reviews/day9.md` Part 1 (automatic gate, before proposing merge).

## Out-of-Scope — [AI-drafted, pending approval]

- **No `AGENTS.md` file** (Decision 5) — CLAUDE.md's role is documented, not
  duplicated.
- **No version/issue-semantics graph** — "superseded" here is **structural**
  (`dmRef` impact), not issueInfo version modelling (that is a new geosphere,
  beyond ADR-0002 "minimal"; T4).
- **Graph impact query does not enter the answer/agent pipeline** — parallel
  interface option only (Decision 2).
- **No full RDF/SPARQL knowledge-graph platform** (ADR-0002 boundary).
- **No template-injection number pipeline** — hand-authored numbers guarded by
  the drift test, not generated at build time (Decision 3, toy-scale honest).
- **AI does not write/edit `docs/journal/`** (INV-6); no adjudication drafting.
- **No resume text in the public repo** (INV-1; Decision 1).

## Verification (how to check) — [AI-drafted, pending approval]

```bash
make test && make lint                          # 268+9 + day9 evidence/graph tests green
uv run pytest tests/test_day9_evidence.py -q    # dead-link + number-drift guard
learnarken graph impact <DMC>                   # impact query on synthetic corpus (Neo4j up)
# 5-min-locate acceptance: drive MiniMax over llms.txt + EVIDENCE.md, record result
```

Then the automatic cross-host red-team gate on the diff → `docs/reviews/day9.md`
Part 1 → Yi Xin adjudicates (Part 2, human).
