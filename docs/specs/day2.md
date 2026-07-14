# Day 2 SPEC — Canonical Model & Layered Validator (v0.2.0)

> **Authorship note (INV-6)**: the decision layer below was dictated by
> Yi Xin in the 2026-07-13 working session (in Chinese); AI transcribed and
> translated it with content unchanged. The Interfaces section is AI-drafted.
> **Status: APPROVED by Yi Xin, 2026-07-13** — open questions Q1–Q5 were
> adjudicated in the same session (answers transcribed in "Adjudicated
> decisions" below); implementation authorized on that reply.

## Goal (one sentence) — [HUMAN, transcribed]

Build the canonical Pydantic model and a **four-layer validator**
(well-formedness → schema → single-file BREX → cross-file integrity), exposed
through `learnarken validate` and a per-DMC info query, tagged `v0.2.0`.

## Key Decisions — [HUMAN, transcribed from 2026-07-13 dictation]

1. **Validation is layered, four levels:**
   - **L0 — XML well-formedness**: the file parses as legal XML.
   - **L1 — structural conformance** to the (project's S1000D-style) schema.
   - **L2 — single-file BREX**: does the file satisfy its applicable BREX,
     implemented as Schematron-style assertions.
   - **L3 — cross-file integrity**, explicitly as **groundwork for the
     future knowledge graph**: dangling `dmRef`? missing ICN? issue/version
     mismatch? circular references?
2. **Applicability enters the model (and later the chunk metadata)**: an
   operation, part, or other item may be *inapplicable* to a certain
   model/variant; this must be captured so Day 3 chunks can carry and filter
   on it. *(AI scope note: the chunker itself is Day 3 — Day 2 delivers the
   applicability model that chunks will inherit.)*
3. **CLI must answer per-DMC queries**: for a given DMC, report the model
   info, how many content items, how many BREX rules (evaluated/violated),
   creation time, and similar facts.

Inherited from Day 1 decisions 3–5 (docs/specs/day1.md), landing today:

- DM metadata fields: DMC, title, issueInfo, language, security
  classification, applicability, QA status; plus the labeled non-standard
  extensions `effectiveDate` / `expiryDate`.
- DM content types: descriptive, procedural (with steps), fault isolation,
  IPD, warnings/cautions, abnormal-handling sections.
- Day 2 CLI = full metadata model + SQL-SELECT-like queries.

## Interfaces — [AI-DRAFTED, pending review]

### Module layout

```text
src/learnarken/
  models.py       # Pydantic: DmCode, IssueInfo, Applicability, DataModule,
                  # PublicationModule, DmlEntry, Reference (dmRef/icnRef), …
  validation/
    __init__.py   # run_validation(package) -> ValidationReport
    layers.py     # L0 wellformed, L1 schema, L2 brex, L3 crossfile
    rules.py      # declarative BREX rule table (see below)
  schemas/
    learnarken-dm.xsd   # project mini-XSD (simplified subset — see Q1)
```

### Findings schema (shared by all four layers)

```json
{
  "rule_id": "XREF-001",
  "layer": "L3",
  "severity": "error",            // error | warning | info
  "file": "DMC-LA100-A-29-10-00-00A-040A-D_EN-CA.xml",
  "line": 42,
  "path": "/dmodule/content//dmRef[1]",
  "message": "dmRef targets DMC-LA100-A-29-20-00-00A-520A-A, absent from package",
  "fix_hint": "Point the reference at an existing DM or add the missing DM"
}
```

- **Fail-closed layering (INV-4)**: a file that fails L0 is excluded from
  L1–L3; a file failing L1 still enters L3 only as a graph *node* (so other
  files' references to it can resolve) but its own content rules are skipped.
- `validate` exit codes: `0` = no error-severity findings; `1` = at least one
  error finding; `2` = not a package (Day 1 convention).

### Rule set and VIO mapping

| Rule | Layer | Severity | Checks | package-b carrier |
| --- | --- | --- | --- | --- |
| PARSE-001 | L0 | error | XML parses (defusedxml) | — (test fixture) |
| SCHEMA-001 | L1 | error | validates against project XSD | — (test fixture) |
| BREX-001 | L2 | error | hazardous step must be preceded by warning/caution | VIO-3 |
| BREX-002 | L2 | error | DMC code format (numeric SNS codes; filename ↔ dmCode agree) | VIO-4 |
| BREX-003 | L2 | error | procedural DM contains ≥ 1 mainProcedure step | — (test fixture) |
| BREX-004 | L2 | warning | `dmStatus` carries an `applic` element | — (test fixture) |
| BREX-005 | L2 | warning | extension `effectiveDate` < `expiryDate` | — (test fixture) |
| XREF-001 | L3 | error | every `dmRef` resolves inside the package | VIO-1 |
| XREF-002 | L3 | error | every `infoEntityIdent` (ICN) resolves | VIO-2 |
| XREF-003 | L3 | error | DM issueInfo matches its DML registration | VIO-5 |
| XREF-004 | L3 | error | `modelIdentCode` in accepted set (default `{LA100}`) | VIO-6 |
| XREF-005 | L3 | warning | no circular `dmRef` chains (KG hygiene) | VIO-7 (new, Q2) |

Added by the red-team adjudication of 2026-07-14 (docs/reviews/day2.md;
rows AI-drafted, decisions Yi Xin's):

| Rule | Layer | Severity | Checks | package-b carrier |
| --- | --- | --- | --- | --- |
| PARSE-002 | L0 | error | file exceeds the size cap — refused, fail closed (adjudication #4) | — (test fixture) |
| MODEL-001 | L1 | error | canonical model cannot be built — report, never force-generate (#9/#12) | — (test fixture) |
| XREF-006 | L3 | error | duplicate DMC with distinct content at the same issue (#2; byte-identical inputs are deduplicated by md5 first, #1) | — (test fixture) |
| XREF-007 | L3 | warning | duplicate DMC where a strictly newer issue exists — newest indexed ("入库"), superseded copies warned (#2) | — (test fixture) |

Constraints from the package-b manifest: findings must map **1:1** to
VIO-1 – VIO-7 (each attached to its carrier DM; DML registry entries are not
double-counted); the clean DM (24-00) must yield zero findings. package-a
must yield zero findings at every layer.

BREX-001 is honestly a **toy heuristic**: a procedural DM whose step text
matches a hazard lexicon (pressure, nitrogen, discharge, voltage, …) with no
**preceding** warning/caution — covered means a warning/caution in reqSafety
or in the same or an *earlier* step; later-step warnings do not count
(adjudication #5 chose the strict preceding/local semantics). Real BREX
rules are business-authored; this stands in for one (INV-7 labeling).

### New samples (Q2/Q3 adjudication)

- **package-b + VIO-7**: two new descriptive DMs forming a reference cycle
  (`24-30` ↔ `24-40`); carrier = `DMC-LA100-A-24-30-00-00A-040A-D`. Both are
  registered in the package-b DML; the manifest README gains a VIO-7 row.
  Day 1 tests pinning the package-b file set/counts are updated accordingly.
- **`samples/package-c` (new, additive)**: a small *valid* package whose DMs
  carry **structured applicability assertions** (e.g. serial-number range,
  variant) in addition to display text — the input Day 3 chunks will filter
  on. package-a/b files are not modified (Q3 adjudication).

### Applicability model (Q3)

```python
class ApplicAssertion(BaseModel):
    property_ident: str      # e.g. "serialNumber", "variant"
    property_type: str       # "prodattr" | "condition"
    values: str              # e.g. "0001~0050"

class Applicability(BaseModel):
    display_text: str                      # human-readable, always present
    assertions: list[ApplicAssertion] = [] # machine-filterable, may be empty
```

### CLI

```text
learnarken validate <package-dir> [--json] [--accepted-models LA100]
learnarken dm <package-dir> <DMC> [--json]
```

`learnarken dm` (per-DMC query, decision 3) prints:

- **identification** — DMC, title, issue, language, issueDate
- **status** — security, QA, applicability (display text + assertions),
  extension effective/expiry dates *(the standard has no "creation time";
  `issueDate` is the closest standard field — see Q4)*
- **content stats** — steps, warnings, cautions, outbound dmRefs, ICN refs,
  and inbound references (which DMs point here — the KG preview)
- **validation** — BREX rules evaluated / findings raised for this DM

## Acceptance Criteria — [assembled from execution-plan.md Day 2 + the
2026-07-13 dictation; pending human approval]

- [ ] Pydantic model covers: DMC, the four DM content types, PM, DML,
      references, warning/caution, applicability, extension dates
- [ ] `learnarken validate samples/package-a` → zero findings, exit 0
      (both output formats)
- [ ] `learnarken validate samples/package-b` → findings map 1:1 to the
      manifest VIO-1 – VIO-7, each precise to file + path/line; the clean DM
      yields zero findings; exit 1
- [ ] `learnarken validate samples/package-c` → zero findings; its structured
      applicability assertions parse into the model
- [ ] Every rule in the table has ≥ 1 passing and ≥ 1 violating golden test
      (rules without a package-b carrier use `tests/fixtures/`)
- [ ] `learnarken dm samples/package-a <any DMC>` answers with the fields
      above; `--json` variant works
- [ ] CI green; feature branch → PR → squash merge → tag `v0.2.0` with
      release notes

## Explicitly Out of Scope (today) — [AI-DRAFTED from prior scope
decisions, pending approval]

- **No chunker, no chunks** (Day 3) — today only guarantees the model carries
  what chunks will need (applicability, DMC, task metadata)
- No retrieval, no indexing, no knowledge-base storage (Day 3+)
- **No actual knowledge graph** — L3's reference graph is an in-memory
  validation structure; no RDF/SPARQL, no graph export (Planned / Day 4
  re-evaluation checkpoint)
- No full S1000D applicability *expression evaluation* (boolean applic
  engine); only structured assertions + display text
- No auto-fix (Day 7) — findings carry `fix_hint` strings only
- No real S1000D XSD conformance (see Q1 — samples are simplified, INV-1)

## Adjudicated decisions on Q1–Q5 — [HUMAN, transcribed from Yi Xin's
2026-07-13 reply]

1. **Q1 — accepted.** The schema is **our own**, S1000D-like. Rationale as
   stated: we cannot access real S1000D documents, so we work with a similar
   standard and similarly generated documents.
2. **Q2 — accepted as recommended.** Circular reference is a **warning**,
   and **VIO-7 is added** (to package-b, with the constitution §4 amendment).
3. **Q3 — adjusted.** Do **not** touch the Day 1 deliverables: add **new
   applicability samples as additional input** (a new `samples/package-c`),
   instead of editing package-a modules.
4. **Q4 — accepted.** No new field; report `issueDate` plus the labeled
   extension dates.
5. **Q5 — accepted.** Assertion-style rules (declarative table + lxml XPath),
   no isoschematron toolchain.

## Risks & Open Questions — [adjudicated above; original questions kept for
the record]

Inherited risk R1/R2 (Day 1) applies with force today: **our XSD and BREX
rules encode our own understanding of S1000D, not expert ground truth.**
The project XSD is honest as "a schema for our simplified subset" (INV-7),
not as S1000D conformance.

- **Q1 — Schema source for L1.** Real S1000D 4.x XSDs would reject our
  deliberately simplified synthetic samples (INV-1). *Recommendation:* author
  a project mini-XSD (`schemas/learnarken-dm.xsd`) covering exactly our
  subset, labeled as such in the README (INV-7). Alternative: skip XSD and
  hand-roll structural checks — weaker story, not recommended.
- **Q2 — Circular-reference check has no carrier.** package-b's manifest
  (constitution §4) enumerates VIO-1–6 only, and package-a's dmRef graph is
  currently acyclic (verified 2026-07-13). Options: (a) add **VIO-7
  (circular dmRef chain)** to package-b — requires a constitution §4
  amendment, which is human-only; (b) keep the check but test it via
  fixtures only. Also: severity — S1000D does not forbid reference cycles,
  so `warning` is proposed, not `error`. *Recommendation:* (a) + warning.
- **Q3 — Structured applicability requires a sample edit.** All current
  applic elements are display-text only ("LA100, all serial numbers"), which
  cannot express "this step does not apply to variant X". *Recommendation:*
  add structured `<assert>` elements (e.g. serial-number ranges) to 2–3
  package-a DMs — synthetic, INV-1-compliant, but it touches Day 1
  deliverables, so it needs your sign-off.
- **Q4 — "Creation time" mapping.** S1000D has no creation timestamp;
  the standard field is `issueDate`, plus our extension
  `effectiveDate`/`expiryDate`. *Recommendation:* `learnarken dm` reports all
  three, labeled; no new extension field.
- **Q5 — Schematron tooling** (deferred here by Day 1 spec).
  *Recommendation:* a declarative Python rule table evaluated with lxml
  XPath (rule id / severity / xpath / message / fix hint) — "Schematron-style
  assertions" per the dictation, without the isoschematron/XSLT toolchain.
  Alternative: real `.sch` files via `lxml.isoschematron` — closer to
  industry practice, heavier; revisit when BREX grows past toy scale.

The 3 tutorial concepts to verify during implementation *(to be filled from
Yi Xin's notes after the learning step — BREX/SNS section of tutorial 01)*:

1. _(unfilled)_
2. _(unfilled)_
3. _(unfilled)_
