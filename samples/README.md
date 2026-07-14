# Samples

Two kinds of content live here: **synthetic packages** (the project's working
data, authored for LearnArken) and **real reference files** (kept only to study
authentic S1000D structure).

## 1. Synthetic packages (the project's actual inputs — INV-1)

| Package | Purpose |
| --- | --- |
| [package-a/](package-a/README.md) | **Valid** S1000D-like package for the fictional LA100 aircraft: 8 data modules (descriptive, procedural, fault isolation, IPD) + PM + DML + placeholder ICN. Intended to pass all validation. |
| [package-b/](package-b/README.md) | **Invalid** package carrying violation classes VIO-1..VIO-7 exactly once each, plus one clean control module. The violation manifest in its README is the Day 2 validator's exam (INV-3). |
| [package-c/](package-c/README.md) | **Valid** package whose DMs carry structured applicability assertions (serial range, variant) — added by the Day 2 SPEC Q3 adjudication as new input, leaving package-a/b untouched. |

All synthetic XML follows S1000D 4.x core element semantics with honestly
labeled simplifications and one labeled non-standard extension
(`learnarkenExtension`); see each package README.

## 2. Real reference files (`s1000d/`) — license audit

Real, publicly sourced S1000D files used **only as structural reference**
(never copied into synthetic content, never indexed):

1. **[Amplexor/oxygen-asd-s1000d](https://github.com/Amplexor/oxygen-asd-s1000d)
   — Apache-2.0** ✅ committed to this repo with attribution:
   - `DMC-Procedural-Template-Amplexor.xml` (procedural skeleton, proced.xsd)
   - `DMC-IPD-Template-Amplexor.xml` (illustrated parts data, ipd.xsd)
   - `DMC-Fault-Isolation-Template-Amplexor.xml` (fault isolation, fault.xsd)
2. **[kibook/s1kd-tools-doc](https://github.com/kibook/s1kd-tools-doc) —
   no license declared** ⚠️ all rights reserved by default. Its files
   (`DMC-/PMC-/DML-S1KDTOOLS-*`) are **excluded from this repository** via
   `.gitignore` and exist only in local working copies for study
   (audited 2026-07-11). "Publicly visible" does not mean "redistributable."

## 3. Why no ATA iSpec 2200 / ASD S2000M files?

Both are **proprietary standards**: ATA iSpec 2200 (Airlines for America) and
ASD S2000M (AeroSpace, Security and Defence Industries Association of Europe)
distribute their DTDs/schemas to paying members only; redistributing them
would be infringement. S1000D is the modern, open, modular-XML standard of
this domain, so this project works exclusively with S1000D-like structures
(see [docs/constitution.md](../docs/constitution.md) §2).
