# Day 1 Design Discussions — 2026-07-12

> Distilled by AI (Claude, the implementing assistant) from the live working
> session; reviewed and approved by Yi Xin. Format: question → options →
> decision → rationale. Decisions were made by Yi Xin unless noted.

## D1. Should we adopt a spec framework (GitHub Spec Kit / Superpowers)?

- **Options**: (a) adopt Spec Kit's `/specify → /plan → /tasks` pipeline;
  (b) adopt the Superpowers skill library; (c) hand-write minimal templates and
  borrow only the *constitution* concept.
- **Decision**: (c).
- **Rationale**: this project's core evidence is that specs and adjudications
  come from a human; a spec-generating pipeline would erase exactly what the
  repo is trying to prove. For a 10-day solo project, framework learning curve
  outweighs template value. The one durable idea — a project-level invariants
  file — became [docs/constitution.md](constitution.md).

## D2. What does "Day 1 done" mean — governance docs, or running code?

- **Context**: Yi Xin flagged that Day 1's real deliverable felt like
  "background, constraints, standards, red-team process", not test cases, and
  the plan's Day 1 acceptance felt fuzzy.
- **Options**: (a) make Day 1 a pure governance/docs day; (b) split: governance
  today, skeleton tomorrow (slippage rule allows 2 calendar days); (c) both in
  one day, with the code skeleton deliberately thinned to "CI green +
  `inspect` runs + smoke tests".
- **Decision**: (c) — both buckets, one day, one `v0.1.0` tag.
- **Rationale**: a docs-only day produces no verifiable artifact and repeats
  the exact failure mode (endless preparation, no shipping) the AI-first plan
  was written to prevent. Key clarification that resolved the fuzziness:
  **acceptance criteria ≠ test cases** — Day 1 hand-writes the former (what
  "done" means), not the latter (how it's verified in code, which starts
  Day 2).

## D3. Which constraints must be pinned as invariants on Day 1?

- **Context**: Yi Xin's requirement — describe the simulated business scenario
  and its limits explicitly: distributed behavior simulated on one machine but
  designed for real distribution; aviation S1000D domain; synthetic documents
  with deliberately injected errors.
- **Decision**: pin 8 invariants (INV-1 – INV-8) in the constitution, with the
  distributed-interface constraint (INV-2) and enumerated error injection
  (INV-3) written *before* any retrieval/indexing code exists.
- **Rationale**: INV-2 shapes every module interface from Day 3 onward —
  retrofitting it after the first indexer exists would already be
  architecture debt. The package-b violation list (VIO-1 – VIO-5) is a draft
  pending Day 1 SPEC sign-off, because it becomes the validator's entire exam.

## D4. README language and audience

- **Context**: job-search target is Canadian companies.
- **Options**: (a) Chinese-primary README; (b) English default +
  `README.zh-CN.md` kept; (c) fully bilingual everywhere.
- **Decision**: (b); additionally all governance docs (constitution, redteam,
  CLAUDE.md, templates) and the human-written evidence chain (specs,
  adjudications, journals) are in English; tutorials stay Chinese.
- **Rationale**: recruiters must be able to read the audit targets directly;
  writing the daily evidence chain in English doubles as interview-language
  practice. Full bilingual maintenance is double cost for a 10-day project.

## D5. Who writes the SPEC — the central authorship debate

- **Context**: Yi Xin challenged the original "specs are 100% human-written"
  rule: in normal development the human describes intent, AI elaborates, human
  accepts. Also proposed preserving brainstorm discussions for recruiters.
- **Options**: (a) keep specs 100% human-written, AI only asks questions;
  (b) human describes → AI writes the spec → human approves;
  (c) **layered model**: human writes the decision layer (goal, acceptance
  criteria, out-of-scope, key decisions), AI drafts the elaboration layer
  (interfaces, formats) under an explicit `AI-drafted` label, and working
  discussions are distilled into this `docs/discussions/` directory.
- **Decision**: (c).
- **Rationale**: option (b) fails the evidence test — "I approved it" is a
  zero-cost action a recruiter cannot verify, and an AI-toned spec under a
  "human-written" claim damages credibility more than it saves time. The
  layered split mirrors real industry practice (PM writes the PRD and
  acceptance bar; engineering writes the technical elaboration) and matches
  Yi Xin's PM background. The discussion log itself — this file — was Yi Xin's
  proposal, adopted because it shows the steering of AI in a form that is
  hard to fake and directly feeds Day 9's `AI-COLLABORATION.md`.

## D6. Fleshing out the business story, and three scope cuts it triggered

- **Context**: to write the Day 1 SPEC, Yi Xin supplied the full background
  story: on-site engineers beside the aircraft (latency + recall ranked
  first), training manuals as input, superseded versions to filter, a
  fail-closed ingestion gate that only reports S1000D deviations (never
  auto-corrects), basic-Schematron-only BREX, a 9-field DM metadata model,
  and an SQL-SELECT-like CLI over DM metadata.
- **Three questions AI raised, and the rulings**:
  1. *CLI timing* — chunk counts require Day 3's chunker; metadata queries
     require Day 2's model. **Ruling: split delivery across Days 1/2/3**
     (inspect basics today; queries Day 2; chunk counts Day 3), instead of
     swallowing Day 2's work into Day 1 (INV-8 risk).
  2. *Non-standard date fields* — effective/expiry dates are not S1000D DM
     status fields (issueDate is). **Ruling: keep both as project extensions,
     explicitly labeled non-standard** — they carry the expired-document
     business scenario.
  3. *Ship-maintenance documents* — a legally coded out-of-domain DM matched
     no existing violation class. **Ruling: add VIO-6**; VIO-1–5 confirmed
     unchanged, list status moved from DRAFT to CONFIRMED.

## D7. Threat model surfaced by the Day 1 red-team review

- **Context**: the Codex red team flagged the unhardened XML parser (finding
  #3). Adjudicating it, Yi Xin noticed something larger: the entire project
  implicitly assumes inputs are **non-malicious** — errors are misplaced,
  malformed, or outdated documents, never deliberate poisoning.
- **Options**: (a) build anti-poisoning validation now; (b) ignore the topic;
  (c) state the assumption explicitly, harden only against accidental/format
  hazards (defusedxml), and leave a placeholder method marking where
  poisoning defenses would live.
- **Decision**: (c) — by Yi Xin, during adjudication.
- **Rationale**: a learning system reasonably assumes non-adversarial input,
  and we currently lack the experience to enumerate poisoning defenses; but
  the assumption must be *written down* (constitution §2), not implicit —
  and the placeholder proves the direction was considered rather than missed.
  This is the first design-level insight produced by the red-team mechanism
  itself.
