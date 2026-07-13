# package-b — Invalid Synthetic Sample Package (Violation Manifest)

Synthetic S1000D-like package for the fictional **LA100** aircraft with
**deliberately injected, enumerated violations** (constitution INV-3, classes
confirmed in [docs/specs/day1.md](../../docs/specs/day1.md)). This package is
intended to **fail** validation with findings matching exactly this manifest.

## Violation manifest

| VIO | File | Injected defect | Expected detection (Day 2) |
| --- | --- | --- | --- |
| VIO-1 | DMC-LA100-A-**29-10**-00-00A-040A-D | `dmRef` targets DMC-LA100-A-29-**2**0-00-00A-520A-A, which does not exist in this package | Reference-integrity check: unresolved dmRef |
| VIO-2 | DMC-LA100-A-**32-10**-00-00A-941A-D | `graphic infoEntityIdent="ICN-LA100-32-999-01"`; no such illustration (package has no `icn/` at all) | Reference-integrity check: unresolved ICN |
| VIO-3 | DMC-LA100-A-**29-30**-00-00A-520A-A | Step 2 discharges a pressurized nitrogen accumulator with no preceding warning/caution (`<noSafety/>` declared) | BREX rule: hazardous step requires warning |
| VIO-4 | DMC-LA100-A-**2X-10**-00-00A-040A-D | `systemCode="2X"` — non-numeric SNS system code; DMC malformed | DMC coding check: illegal code format |
| VIO-5 | DMC-LA100-A-**24-10**-00-00A-040A-D | DM claims `issueNumber="003"`; the DML registers it at `001` | Issue-info consistency check: DM vs DML |
| VIO-6 | DMC-**SS200**-A-58-10-00-00A-520A-A | Ship ballast-pump module (vessel SS200) — legally coded but out-of-domain for an aircraft library | Domain check: modelIdentCode not in accepted set |
| — (clean) | DMC-LA100-A-**24-00**-00-00A-040A-D | No violation. Present to prove the validator does not over-flag compliant modules | Must produce zero findings |

Support files: PMC-LA100-LEARN-00002-00 (references only structurally normal
modules) and DML-LA100-LEARN-C-2026-00002 (registers all seven DMs; carries
the VIO-5 mismatch).

## Rules of this package (INV-3)

- **Violation identity is defined by the carrier data module**, i.e. the DM
  file named in the manifest above. Each violation class has exactly one
  carrier.
- The DML **registers** every module in the package — including the malformed
  `2X` code and the out-of-domain `SS200` code — because registering what
  exists is a DML's job. A validator must **not** count these registry
  entries as additional VIO-4/VIO-6 findings; they resolve to the same
  carrier DM. (The single exception is VIO-5, where the DML entry itself is
  half of the inconsistency — the finding still attaches to the carrier DM.)
- A validator finding that does not map to this manifest means either the
  manifest or the validator is wrong — that is a bug, not a feature.
- Simplifications vs. real S1000D are the same as
  [package-a](../package-a/README.md).
