# Day 2 Design Discussions — 2026-07-13/14

> Distilled by AI (Claude, the implementing assistant) from the two working
> sessions; **pending Yi Xin's review**. Format: question → options →
> decision → rationale. Decisions were made by Yi Xin unless noted.
> (Filed late — the Day 1 precedent called for this record on the same day;
> flagged by Yi Xin on 2026-07-14.)

## D1. What schema does L1 validate against?

- **Context**: Day 2's dictated scope made validation four-layered (L0 XML
  well-formedness → L1 schema → L2 single-file BREX → L3 cross-file), with L3
  explicitly as knowledge-graph groundwork.
- **Options**: (a) the official S1000D 4.x XSDs; (b) a project-authored
  mini-XSD covering exactly our simplified subset; (c) no XSD, hand-rolled
  structural checks.
- **Decision**: (b).
- **Rationale** (Yi Xin): we cannot access real S1000D documents, so we work
  with a similar standard and similarly generated documents — the schema is
  ours, S1000D-like, honestly labeled (INV-7). The official XSDs would reject
  the deliberately simplified synthetic samples (INV-1). Design rule that
  fell out: XSD strict on structure, lenient on attribute values — value
  checks live in BREX where findings carry fix hints.

## D2. Circular references: severity and sample carrier

- **Options**: severity error vs warning; carrier as a new VIO-7 in
  package-b (requires constitution §4 amendment) vs test fixtures only.
- **Decision**: warning + VIO-7 in package-b (cycle pair 24-30 ↔ 24-40,
  carrier = smallest DMC in the component).
- **Rationale**: S1000D does not forbid reference cycles — package-a's own
  procedures legitimately cross-reference (verified acyclic, but a 2-cycle
  would not be illegal); what cycles actually threaten is Day 6+ KG
  traversal. Keeping every violation class carried in package-b preserves
  INV-3's "the manifest is the validator's exam" property.

## D3. Structured applicability without touching Day 1 deliverables

- **Context**: chunks (Day 3) must carry applicability ("this operation/part
  does not apply to that variant"), but every Day 1 applic element is
  display-text only.
- **Options**: (a) add `<assert>` elements to 2–3 package-a DMs (AI's
  recommendation); (b) new additional samples, Day 1 packages untouched.
- **Decision**: (b) — new `samples/package-c` (serial-range and variant
  assertions), Day 1 files unmodified.
- **Rationale** (Yi Xin): supplement new samples as input rather than editing
  a tagged deliverable. Day 1 test pins on package-a stay intact; package-c
  doubles as the Day 3 filter-metadata input.

## D4. "Creation time" in the per-DMC CLI query

- **Decision**: no new field — report `issueDate` (the closest standard
  field) plus the labeled non-standard `effectiveDate`/`expiryDate`
  extensions.
- **Rationale**: S1000D has no creation timestamp; inventing one would break
  the honest-labeling rule the extension fields already walk carefully.

## D5. Schematron tooling for BREX

- **Options**: (a) declarative Python rule table evaluated over lxml trees;
  (b) real `.sch` files via `lxml.isoschematron`.
- **Decision**: (a) — "Schematron-style assertions" per the dictation.
- **Rationale**: 5 toy rules do not justify the XSLT toolchain; the rule
  table keeps id/severity/message/fix-hint declarative and testable.
  Revisit if BREX grows past toy scale (recorded as deferred, per Day 1's
  open question).

## D6. Red-team adjudication: the fail-open family (2026-07-14)

- **Context**: cross-host red team (Codex) returned 14 findings, verdict
  DO_NOT_MERGE; Yi Xin adjudicated all 14 as accept with directed fixes
  (docs/reviews/day2.md Part 2).
- **Key policy decisions** (beyond mechanical fixes):
  - **Duplicate identity**: md5-identical input = the same document, skip;
    same DMC with distinct content: same issue → error (XREF-006), strictly
    newer issue → admitted with a warning (XREF-007). This turns the
    superseded-versions business story (constitution §1) into executable
    policy for the first time.
  - **Thread safety now, not later**: the future system will be
    multi-threaded, so today's implementation must already be safe
    (per-call schema instances) — "at minimum, never wrong".
  - **Loud degradation**: unparseable dates and skipped files may degrade to
    None/skip, but always log; model-build failures are error findings,
    never silently patched stand-ins.
  - **BREX-001 semantics**: of the two offered options (strengthen rule vs
    weaken wording), the stricter preceding/local semantics was implemented:
    only reqSafety or same/earlier-step warnings cover a hazard.

## D7. Dangling DML registrations become VIO-8

- **Context**: red-team finding #1 — a DML registering a nonexistent DM
  validated clean; fixing it adds a finding class, which INV-3 forbids
  without enumeration.
- **Decision** (Yi Xin, follow-up): fix it and register the class — VIO-8 in
  constitution §4, rule XREF-008, injected into package-b's DML (carrier =
  the DML file, the one place this defect can live).
- **Rationale**: the ingestion gate is the product's core promise (INV-4);
  an unresolvable registration is exactly the kind of deviation it must
  report, so it earns a first-class violation ID rather than a scope-out.
