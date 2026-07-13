# package-a — Valid Synthetic Sample Package

Synthetic S1000D-like data package for the fictional **LA100** light utility
aircraft. Authored for LearnArken (INV-1: no real technical data). This
package is intended to **pass** all validation.

## Contents

| File | Type | What it is |
| --- | --- | --- |
| DMC-LA100-A-00-00-00-00A-040A-D | Descriptive | Aircraft general description (issue 002 — carries the version story) |
| DMC-LA100-A-29-00-00-00A-040A-D | Descriptive | Hydraulic system overview, cross-refs the pump tasks |
| DMC-LA100-A-29-10-00-00A-520A-A | Procedural | Hydraulic pump removal (warnings before hazardous steps) |
| DMC-LA100-A-29-10-00-00A-720A-A | Procedural | Hydraulic pump installation |
| DMC-LA100-A-32-10-00-00A-310A-A | Procedural | Main landing gear inspection |
| DMC-LA100-A-29-10-00-00A-421A-A | Fault isolation | Low hydraulic pressure troubleshooting |
| DMC-LA100-A-32-10-00-00A-421A-A | Fault isolation | Gear does not retract troubleshooting |
| DMC-LA100-A-29-10-00-00A-941A-D | IPD | Hydraulic pump parts list, references ICN-LA100-29-001-01 |
| PMC-LA100-LEARN-00001-00 | Publication module | Manual table of contents referencing all 8 DMs |
| DML-LA100-LEARN-C-2026-00001 | Data module list | Registers all 8 DMs with their issue numbers |
| icn/ICN-LA100-29-001-01.svg | Illustration | Placeholder graphic referenced by the IPD |

## Simplifications vs. real S1000D (honest list, INV-7)

- No DTD/XSD declaration; element set is a hand-picked subset of S1000D 4.x
  core semantics (`dmodule`, `dmAddress`, `dmCode`, `issueInfo`, `dmStatus`,
  `content` with description / procedure / faultIsolation /
  illustratedPartsCatalog).
- `<learnarkenExtension>` (`effectiveDate`, `expiryDate`) is **not S1000D** —
  a labeled project extension carrying the expired-document business scenario.
- Fault isolation uses simplified `isolationStep` prose instead of the full
  S1000D fault isolation question/answer tree.
- Applicability is display text only; no computable applic model.
- BREX data module intentionally absent until Day 2 (basic Schematron rules).
