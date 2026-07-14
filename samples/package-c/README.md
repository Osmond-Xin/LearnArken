# package-c — Structured-Applicability Sample Package (valid)

Synthetic S1000D-like package for the fictional **LA100** aircraft, added by
the **Day 2 SPEC Q3 adjudication** (2026-07-13): applicability samples are
supplied as *new additional input* so the Day 1 deliverables (package-a/b)
stay untouched.

Purpose: every DM here carries **structured applicability assertions** in
addition to the display text — the machine-filterable form that Day 3 chunk
metadata will inherit ("this operation/part does not apply to that
variant/serial range").

| File | Content | Applicability |
| --- | --- | --- |
| DMC-LA100-A-**24-50**-00-00A-520A-A | Main battery — remove procedure | `serialNumber` ∈ `0001~0050` |
| DMC-LA100-A-**32-20**-00-00A-040A-D | Nose gear steering damper — description | `variant` = `B` |
| DML-LA100-LEARN-C-2026-00003 | Registers both DMs | — |

The `<assert applicPropertyIdent= applicPropertyType= applicPropertyValues=>`
form follows S1000D applic semantics in simplified single-assertion shape (no
`evaluate` boolean nesting — honestly labeled simplification, INV-7).

This package is **valid**: `learnarken validate` must produce zero findings.
Simplifications vs. real S1000D are the same as
[package-a](../package-a/README.md).
