# LearnArken Constitution — Background & Invariants

> This file is the **highest authority** in this project: any daily SPEC, any AI
> implementation, and any adjudication of a red-team finding yields to this file
> on conflict. Changing this file requires a dedicated commit with the rationale
> in the commit message.
>
> Red-team reviews should cite rule IDs (e.g. `INV-2`) when reporting violations.

## 1. Business Scenario (What This Project Simulates)

**Scenario**: an aviation MRO (maintenance, repair & overhaul) company equips
its maintenance engineers for on-site work. The defining picture: an engineer
stands beside an aircraft, laptop open, looking for the correct maintenance
procedure right now. Two requirements therefore outrank everything else in
every design decision: **latency** (answers in seconds, not minutes) and
**recall** (the relevant procedure must not be missed). Benchmarks in this
project always report both.

The source material is the company's **training manuals**, delivered as
S1000D-style data packages. Because manuals accumulate superseded issues over
time, the data model must distinguish and filter document versions
(issueInfo / issueDate, plus labeled project extensions for
effective/expiry dates — see §2).

The system provides:

1. **Fail-closed ingestion gate** — every document is validated against
   S1000D structure and basic BREX rules (implemented as Schematron) before
   it may enter the knowledge base. Outdated issues, non-compliant documents,
   and out-of-domain content (e.g. ship-maintenance modules mixed into an
   aircraft library) are **rejected with a report stating the deviation from
   S1000D** — the system never auto-corrects, summarizes, or infers at
   ingestion. A human decides what happens to rejected documents; only
   compliant documents enter the knowledge base.
2. **Retrieval & QA** — "What preparation is required before replacing this
   part?" Answers must carry source citations; if nothing is found, say so —
   never fabricate (wrong answers in a maintenance domain cause safety
   incidents).
3. **Assisted repair** — for validation findings, the system proposes fixes
   for human approval; it never silently modifies data.

**This project is a toy-scale, educational implementation of that scenario**,
not an enterprise S1000D suite. Every simplification must be honestly labeled
(see INV-7).

## 2. Simulation Boundaries (What Is Simulated, and How Far)

| Dimension | Reality | This project's simulation | Shortcuts NOT allowed |
| --- | --- | --- | --- |
| Data | Real S1000D CSDB, thousands of data modules | Self-authored synthetic XML packages, tens of modules | Structure must follow S1000D 4.x core element semantics (dmodule/dmAddress/content, …); no invented private formats |
| Errors | Errors in real data are unknown | Violations in package-b are **deliberately injected, known, enumerated** | Every violation class is listed and numbered; validator/repair-agent scores are claimed against this list only — no generalization claims |
| Scale | Distributed deployment, multi-node indexes | Single-machine multithreading/multiprocessing | See INV-2: interfaces must be designed as if truly distributed |
| Standards | S1000D + iSpec 2200 + S2000M, etc. | S1000D-like only; the others are proprietary and untouched | README explains why other standards are absent (see samples/README.md) |

**Known accepted limitations** (stated in Day 1 SPEC, 2026-07-12; see
`docs/specs/day1.md` Risks for the full statements):

- **No expert ground truth**: the author is not an S1000D practitioner, so
  "compliant" as judged by this project's validator has no expert
  verification; a standard-premised pipeline built on it may drift. In a real
  project this is controlled by a business/engineering second-confirmation
  loop on document scope, standard coverage, and volume — deliberately
  dropped in this demo.
- **Non-malicious input assumption**: input documents are assumed to be
  erroneous at worst (misplaced, malformed, outdated) — **not deliberately
  poisoned by an adversary**. Dedicated anti-poisoning validation is out of
  scope (insufficient experience to enumerate the defenses today); the code
  keeps an explicit placeholder marking where such checks would live. Parser
  hardening against accidental/format-level hazards (entity expansion, etc.)
  IS in scope. (Decided during Day 1 red-team adjudication, 2026-07-13.)
- **No production engineering targets**: the on-site scenario is assumed
  without concurrency modeling, a defined retrieval-latency SLO, a target
  hardware profile (e.g. 2-core/4 GB vs 4-core/8 GB), a budget scenario, or
  an offline/disconnected mode (plausible in the extreme on-site case). All
  latency numbers describe the development machine only. This remains a
  simulation, not a production tool (see INV-7).

## 3. Invariants (INV, enforced project-wide)

### INV-1 Data Red Line

The public repository may only contain: (a) synthetic XML authored for this
project; (b) third-party files whose license clearly permits redistribution
(e.g. the Apache-2.0 Amplexor templates, with attribution). The
kibook/s1kd-tools-doc files carry no license and **never enter the repo**
(already blocked by .gitignore). Same for `.env`, credentials, and personal
job-search documents.

### INV-2 Distributed-Interface Constraint

Distribution is simulated on a single machine, but **all interfaces are
designed as for a real distributed system**:

- Sharding/routing goes through an abstraction layer (shard router); callers
  never know the shard count;
- Cross-"node" communication never uses single-machine shortcuts (shared
  memory, global variables) — only explicit messages/interfaces;
- Writes are idempotent; index updates have visibility semantics (when does a
  write become queryable) and support rollback;
- Consistency behavior is tested (update → visibility → rollback).

Rationale: this is what connects a toy project to real engineering competence.
An implementation violating this rule fails even if functionally correct.

### INV-3 Enumerated Error Injection

Every violation class injected into package-b must: have an ID, a description,
and an entry in `samples/README` (or a dedicated list); from Day 2 on, each
class has at least one golden test pair (one passing case + one violating
case). A validator "happening to report an unregistered error" is forbidden —
it means either the list or the validator is wrong.

### INV-4 Fail-Closed Refusal

In the QA pipeline, when retrieved evidence is insufficient to support an
answer, the system must explicitly refuse — never let the LLM fill the gap.
Every answer either carries verifiable citations or is an explicit refusal;
there is no third state.

### INV-5 Reproducibility

Every number appearing in the README must have: a fixed random seed, a
versioned golden set, and a copy-pasteable reproduction command. Numbers that
cannot be reproduced do not enter the README.

### INV-6 Human-Owned Evidence Chain

The evidence chain follows a layered authorship model, honestly labeled:

- **SPEC decision layer** — goal, acceptance criteria, out-of-scope, and key
  decisions in `docs/specs/` — is written by me personally. The **elaboration
  layer** (interface details, formats) may be AI-drafted, must be labeled
  `AI-drafted`, and takes effect only after my review.
- **Adjudication records** (second half of `docs/reviews/`) and **learning
  journals** (`docs/journal/`) are written by me personally; AI does not
  ghostwrite.
- **Design discussions** are distilled into `docs/discussions/` (question →
  options → decision → rationale). Distillation may be AI-performed, is labeled
  as such, and is reviewed by me.

Red teams read but never write code; every number a red team reports is re-run
by me before merge.

### INV-7 Honest Layering

Outward claims (README, resume) may only assert capabilities that have code +
tests + a demonstrable artifact. The roadmap keeps three fixed layers:
Implemented / Toy-scale / Planned — never blurred.

### INV-8 Slippage Rule

A daily node may occupy at most 2 calendar days; at the deadline, cut scope,
close, and tag. Whatever is cut goes to the Roadmap. The overall plan does not
drift.

## 4. package-b Violation Classes (CONFIRMED — Day 1 SPEC, 2026-07-12)

> Status: **confirmed** in `docs/specs/day1.md`; governed by INV-3.

| ID | Violation class | Example |
| --- | --- | --- |
| VIO-1 | Broken DMC reference | dmRef points to a data module absent from the package |
| VIO-2 | Broken ICN/illustration reference | infoEntityIdent points to a nonexistent illustration |
| VIO-3 | BREX business-rule violation | Hazardous procedural step lacks a preceding warning/caution |
| VIO-4 | Illegal DMC coding | SNS segment inconsistent with content type / malformed code |
| VIO-5 | Issue-info inconsistency | issueInfo conflicts with the version registered in the DML |
| VIO-6 | Out-of-domain document | A legally coded ship-maintenance data module mixed into the aircraft library |
| VIO-7 | Circular reference chain | Data modules whose dmRefs form a cycle (A → B → A); warning severity — S1000D does not forbid reference cycles, but they matter for knowledge-graph traversal *(added by Day 2 SPEC adjudication, 2026-07-13)* |
| VIO-8 | Dangling DML registration | The DML registers a data module that does not exist in the package; carrier is the DML file itself *(added by Day 2 red-team adjudication, 2026-07-14 — finding #1)* |
