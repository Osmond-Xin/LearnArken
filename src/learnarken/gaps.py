"""Gaps as a distinct output class (Arken pillar 4).

Their definition, quoted from the pinned snapshot
(docs/research/arken-source-snapshot-2026-07-26.md §2):

    Gap — "A detected domain where admitted knowledge is incomplete, requiring
    expert contribution", routed **separately** from refusals ("questions
    unanswerable with current sources").

A gap here is a *declared-but-absent* data module: the corpus itself states the
module should exist — either a `dmRef` pointing at it (XREF-001) or a DML
registering it (XREF-008) — and no admitted package contains it. That gives a
gap two properties a refusal does not have: a **deterministic signature** (the
DMC, which the standard supplies) and an addressable **owner**.

## The honest boundary, stated in code because it changes what may be claimed

Arken's gap concerns *admitted* knowledge. In this repo a declared-but-absent
module is an **ingest error** (XREF-001 and XREF-008 are both `Severity.ERROR`),
so a package containing one is rejected and never admitted. The two concepts
therefore meet at a stage boundary, not at the same stage:

- `PRE_ADMISSION_DECLARED_MISSING` — found in a package the gate **rejected**.
  This is what this repo can produce today. It is a real routed action item, but
  it is *not* Arken's gap, because the knowledge was never admitted.
- `ADMITTED_DECLARED_MISSING` — found across packages that **passed** the gate.
  Reachable only when references may legitimately point outside a package, which
  this project's closed-world package model forbids. Computed here (the corpus
  union is checked, not just the owning package), so the class is not fiction —
  but on the current corpus it is expected to be empty, and that emptiness is
  reported rather than hidden.

Claiming pillar 4 as *Implemented* on the strength of the first kind alone would
be an INV-7 breach. What is implemented is the routing mechanism and the
signature; the admitted case waits on a validation-semantics decision that is
out of scope here (see docs/specs/arken-alignment-2026-07-26.md).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from learnarken.models import PackageModel
from learnarken.owners import OwnerMap
from learnarken.validation import analyze_package


class GapKind(StrEnum):
    ADMITTED_DECLARED_MISSING = "admitted_declared_missing"
    PRE_ADMISSION_DECLARED_MISSING = "pre_admission_declared_missing"


class Gap(BaseModel):
    """A declared-but-absent domain, with who should supply it."""

    signature: str
    """The DMC the corpus declares and does not contain — deterministic, from the standard."""

    kind: GapKind
    declared_by: str
    """The file carrying the declaration (a DM for dmRef, the DML for a registration)."""

    declared_in_package: str
    detected_via: str
    """`dmRef` or `dml-registration` — how the corpus declared it."""

    owner: str | None = None
    owner_reason: str | None = None
    owner_source: str | None = None

    @property
    def routed(self) -> bool:
        return self.owner is not None


class GapReport(BaseModel):
    admitted_packages: list[str] = []
    rejected_packages: list[str] = []
    gaps: list[Gap] = []

    @property
    def admitted_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.kind is GapKind.ADMITTED_DECLARED_MISSING]

    @property
    def pre_admission_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.kind is GapKind.PRE_ADMISSION_DECLARED_MISSING]

    def to_dict(self) -> dict:
        return {
            "admitted_packages": self.admitted_packages,
            "rejected_packages": self.rejected_packages,
            "counts": {
                "admitted_declared_missing": len(self.admitted_gaps),
                "pre_admission_declared_missing": len(self.pre_admission_gaps),
            },
            "gaps": [g.model_dump() for g in self.gaps],
        }


def _declarations(package: PackageModel) -> list[tuple[str, str, str]]:
    """Every (target DMC, declaring file, how) the package asserts should exist."""
    out: list[tuple[str, str, str]] = []
    for dm in package.data_modules:
        for ref in dm.dm_refs:
            out.append((ref.dm_code.as_str(), dm.file, "dmRef"))
    for pm in package.publication_modules:
        for ref in pm.dm_refs:
            out.append((ref.dm_code.as_str(), pm.file, "dmRef"))
    for dml in package.dmls:
        for entry in dml.entries:
            out.append((entry.dm_code.as_str(), dml.file, "dml-registration"))
    return out


def collect_gaps(
    package_dirs: list[str | Path],
    accepted_models: tuple[str, ...] = ("LA100",),
) -> GapReport:
    """Detect declared-but-absent modules across a corpus of packages.

    Admission is decided per package by the existing validator: a package with
    error findings is rejected, exactly as `learnarken validate` reports it. The
    presence check is then made against the **union** of admitted packages, so a
    reference satisfied by a sibling admitted package is not a gap.
    """
    report = GapReport()
    loaded: list[tuple[Path, PackageModel, bool]] = []
    for raw in package_dirs:
        directory = Path(raw)
        validation, package = analyze_package(directory, accepted_models=accepted_models)
        admitted = validation.error_count == 0
        loaded.append((directory, package, admitted))
        (report.admitted_packages if admitted else report.rejected_packages).append(str(directory))

    admitted_dmcs = {
        dm.dmc for _dir, package, admitted in loaded if admitted for dm in package.data_modules
    }

    for directory, package, admitted in loaded:
        owners = OwnerMap.load(directory)
        present_here = {dm.dmc for dm in package.data_modules}
        for target, declared_by, how in _declarations(package):
            # An admitted sibling package satisfying the reference is not a gap;
            # for a rejected package, only its own contents count, since nothing
            # in it was admitted.
            known = admitted_dmcs | present_here if admitted else present_here
            if target in known:
                continue
            owner_ref = owners.resolve(target)
            report.gaps.append(
                Gap(
                    signature=target,
                    kind=GapKind.ADMITTED_DECLARED_MISSING
                    if admitted
                    else GapKind.PRE_ADMISSION_DECLARED_MISSING,
                    declared_by=declared_by,
                    declared_in_package=str(directory),
                    detected_via=how,
                    owner=owner_ref.owner,
                    owner_reason=owner_ref.reason,
                    owner_source=owner_ref.source if owner_ref.routed else None,
                )
            )
    return report


def render_gaps(report: GapReport) -> str:
    lines: list[str] = []
    if report.admitted_packages:
        lines.append(f"Admitted: {', '.join(report.admitted_packages)}")
    if report.rejected_packages:
        lines.append(f"Rejected at ingest: {', '.join(report.rejected_packages)}")
    lines.append("")

    for label, group in (
        ("Gaps in admitted knowledge (Arken pillar 4)", report.admitted_gaps),
        ("Declared-missing in rejected packages (pre-admission)", report.pre_admission_gaps),
    ):
        lines.append(f"{label}: {len(group)}")
        for gap in group:
            lines.append(f"  {gap.signature}")
            lines.append(f"    declared via {gap.detected_via} in {gap.declared_by}")
            if gap.routed:
                lines.append(f"    owner: {gap.owner}  [{gap.owner_source}]")
            else:
                lines.append(f"    owner: unknown — {gap.owner_reason}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
