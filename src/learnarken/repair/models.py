"""Repair data models and the risk-tier map (Day 7).

Risk tiers (spec Ruling 1b): every enumerated VIO class is apply-eligible
(behind the per-patch human gate); only L0 well-formedness, L1 structural, and
VIO-6 out-of-domain are high-risk dry-run-only. The map is keyed by the
validator's own `rule_id`s so it stays 1:1 with what `analyze_package` emits.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from learnarken.validation.report import Finding


class RepairMode(StrEnum):
    DRY_RUN = "dry-run"
    APPLY = "apply"


class RiskTier(StrEnum):
    APPLY_ELIGIBLE = "apply-eligible"  # apply after per-patch human approval
    DRY_RUN_ONLY = "dry-run-only"  # structural rewrite / scope judgment — never applied


class PatchStatus(StrEnum):
    PATCHED = "patched"  # a verified fix (finding cleared, zero new findings)
    APPLIED = "applied"  # patched AND written to disk after human approval
    DECLINED = "declined"  # patched, offered, human declined at the apply gate
    DRY_RUN_ONLY = "dry-run-only"  # high-risk tier — shown, not offered for apply
    REFUSED = "refused"  # no verified fix found (fail closed, INV-4)
    BUDGET_EXHAUSTED = "budget-exhausted"  # circuit-breaker tripped before a fix


# rule_id -> risk tier. Anything not listed defaults to dry-run-only (fail safe:
# an unknown finding class is treated as high-risk until classified).
_HIGH_RISK: frozenset[str] = frozenset(
    {
        "PARSE-001",  # L0 malformed XML — structural rewrite is a guess
        "PARSE-002",  # L0 oversized file — not a content fix
        "SCHEMA-001",  # L1 mini-XSD structural
        "MODEL-001",  # L1 canonical-model build failure (structural)
        "XREF-004",  # VIO-6 out-of-domain — fix is "remove", a §1.1 human call
    }
)
_APPLY_ELIGIBLE: frozenset[str] = frozenset(
    {
        "BREX-001",  # VIO-3 hazardous step missing warning
        "BREX-002",  # VIO-4 illegal DMC coding
        "BREX-003",  # procedural DM missing steps
        "BREX-004",  # applicability missing (warning)
        "BREX-005",  # extension dates (warning)
        "XREF-001",  # VIO-1 dangling dmRef
        "XREF-002",  # VIO-2 dangling ICN
        "XREF-003",  # VIO-5 issueInfo ↔ DML mismatch
        "XREF-005",  # VIO-7 reference cycle (warning)
        "XREF-008",  # VIO-8 dangling DML registration
    }
)


def risk_tier_for(rule_id: str) -> RiskTier:
    """Map a validator rule_id to its repair risk tier (fail safe: unknown → high)."""
    if rule_id in _APPLY_ELIGIBLE:
        return RiskTier.APPLY_ELIGIBLE
    return RiskTier.DRY_RUN_ONLY


class EditOp(BaseModel):
    """One structured, minimal XML edit — the only shape a patch may take.

    Free-form XML rewriting is deliberately not allowed: bounded ops keep every
    patch minimal-diff and auditable, and stop the LLM from smuggling arbitrary
    markup past the validator.
    """

    op: str  # set_attr | set_text | remove_element | insert_element
    xpath: str  # anchors the edit to a single node (the "minimal diff" scope)
    attr: str | None = None  # for set_attr
    value: str | None = None  # for set_attr / set_text
    xml: str | None = None  # for insert_element (a single element fragment)
    position: str = "before"  # insert_element: before | after | append-child


class ValidatorDelta(BaseModel):
    """The closed-loop verification result for a candidate patch."""

    findings_before: int
    findings_after: int
    cleared: list[str] = Field(default_factory=list)  # "rule_id@file" cleared
    introduced: list[str] = Field(default_factory=list)  # new findings (must be empty)

    @property
    def is_clean_fix(self) -> bool:
        return not self.introduced and self.findings_after < self.findings_before


class ProposedPatch(BaseModel):
    """One finding's repair outcome — the auditable unit (research §3.4)."""

    rule_id: str
    layer: str
    file: str
    message: str
    risk_tier: RiskTier
    status: PatchStatus
    edits: list[EditOp] = Field(default_factory=list)
    diff: str = ""  # unified diff over the target file (empty when refused)
    rationale: str = ""  # distilled from the ReAct thoughts
    evidence: list[str] = Field(default_factory=list)  # consulted module/chunk ids
    validator_delta: ValidatorDelta | None = None
    iterations_used: int = 0
    tokens_used: int = 0

    @classmethod
    def from_finding(cls, finding: Finding, tier: RiskTier, status: PatchStatus) -> ProposedPatch:
        return cls(
            rule_id=finding.rule_id,
            layer=str(finding.layer),
            file=finding.file,
            message=finding.message,
            risk_tier=tier,
            status=status,
        )


class RepairReport(BaseModel):
    """The full run artifact — emitted in dry-run, persisted for auditability."""

    package: str
    mode: RepairMode
    seed: int
    findings_targeted: int
    patches: list[ProposedPatch] = Field(default_factory=list)

    @property
    def fixed_count(self) -> int:
        return sum(
            1 for p in self.patches if p.status in (PatchStatus.PATCHED, PatchStatus.APPLIED)
        )

    @property
    def applied_count(self) -> int:
        return sum(1 for p in self.patches if p.status == PatchStatus.APPLIED)

    @property
    def refused_count(self) -> int:
        return sum(
            1
            for p in self.patches
            if p.status in (PatchStatus.REFUSED, PatchStatus.BUDGET_EXHAUSTED)
        )

    @property
    def all_resolved(self) -> bool:
        """True when nothing was refused — including a clean package (exit 0)."""
        return self.refused_count == 0
