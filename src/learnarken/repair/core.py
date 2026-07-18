"""`run_repair` — orchestrate the repair run (Day 7).

Flow: validate → for each targeted finding run the ReAct loop on a jailed copy →
assemble the `RepairReport`. In apply mode, apply-eligible verified patches are
offered to the human one by one (Ruling 1 / §1.3); approved edits are re-verified
as a set and atomically written. High-risk (dry-run-only) findings are always
proposal-only. Apply-eligible findings are processed first so their in-sandbox
verification is not perturbed by a dry-run-only fix.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from learnarken.repair.agent import LLMFn, minimax_llm, repair_finding
from learnarken.repair.apply import ApplyRefused, verify_and_apply
from learnarken.repair.config import Budget, SandboxPolicy, load_repair_config
from learnarken.repair.models import (
    EditOp,
    PatchStatus,
    ProposedPatch,
    RepairMode,
    RepairReport,
    RiskTier,
    risk_tier_for,
)
from learnarken.repair.sandbox import Sandbox
from learnarken.repair.tools import Toolbox
from learnarken.validation import DEFAULT_ACCEPTED_MODELS, analyze_package
from learnarken.validation.report import Finding

logger = logging.getLogger("learnarken")

# approver(patch) -> True to write. Default denies (fail safe: no silent writes).
Approver = Callable[[ProposedPatch], bool]


def _targeted(findings: list[Finding], only: list[str] | None) -> list[Finding]:
    if not only:
        return list(findings)
    wanted = {t.upper() for t in only}
    return [f for f in findings if f.rule_id.upper() in wanted or str(f.layer).upper() in wanted]


def _tier_order(finding: Finding) -> int:
    # Apply-eligible (0) before dry-run-only (1).
    return 0 if risk_tier_for(finding.rule_id) == RiskTier.APPLY_ELIGIBLE else 1


def run_repair(
    package_dir: str,
    *,
    mode: RepairMode = RepairMode.DRY_RUN,
    only: list[str] | None = None,
    budget: Budget | None = None,
    sandbox_policy: SandboxPolicy | None = None,
    llm: LLMFn | None = None,
    approver: Approver | None = None,
    accepted_models: tuple[str, ...] = DEFAULT_ACCEPTED_MODELS,
    seed: int = 0,
) -> RepairReport:
    config = load_repair_config()
    budget = budget or config.budget
    sandbox_policy = sandbox_policy or config.sandbox
    llm = llm or minimax_llm
    approver = approver or (lambda _p: False)

    report0, _ = analyze_package(package_dir, accepted_models)
    findings = sorted(_targeted(report0.findings, only), key=_tier_order)
    report = RepairReport(
        package=str(package_dir),
        mode=mode,
        seed=seed,
        findings_targeted=len(findings),
    )

    with Sandbox(package_dir, sandbox_policy) as sandbox:
        toolbox = Toolbox(sandbox, accepted_models)
        for finding in findings:
            tier = risk_tier_for(finding.rule_id)
            patch = repair_finding(finding, toolbox, llm, budget, tier)
            # A fix found for a high-risk class is shown but never applied.
            if tier == RiskTier.DRY_RUN_ONLY and patch.status == PatchStatus.PATCHED:
                patch.status = PatchStatus.DRY_RUN_ONLY
            report.patches.append(patch)

    if mode == RepairMode.APPLY:
        _run_apply_gate(package_dir, report, approver, accepted_models)
    return report


def _run_apply_gate(
    package_dir: str,
    report: RepairReport,
    approver: Approver,
    accepted_models: tuple[str, ...],
) -> None:
    """Prompt per apply-eligible patch; write the approved set atomically."""
    approved: list[ProposedPatch] = []
    edits_by_file: dict[str, list[EditOp]] = {}
    for patch in report.patches:
        # Recompute the tier from the rule_id at the boundary — never trust the
        # stored `patch.risk_tier` (red-team #7). A high-risk class can never
        # reach the write path even if its serialized tier were tampered.
        eligible = risk_tier_for(patch.rule_id) == RiskTier.APPLY_ELIGIBLE
        if not eligible or patch.status != PatchStatus.PATCHED:
            continue
        if approver(patch):
            approved.append(patch)
            edits_by_file.setdefault(patch.file, []).extend(patch.edits)
        else:
            patch.status = PatchStatus.DECLINED

    if not approved:
        return
    try:
        result = verify_and_apply(package_dir, edits_by_file, accepted_models)
    except ApplyRefused as exc:
        # Combined approved set failed re-verification — write nothing, keep the
        # patches as proposals, and surface the fail-closed refusal.
        logger.warning("apply refused (fail closed): %s", exc)
        return
    written = set(result.written)
    for patch in approved:
        if patch.file in written:
            patch.status = PatchStatus.APPLIED
