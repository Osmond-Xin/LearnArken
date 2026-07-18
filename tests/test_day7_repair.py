"""Day 7 repair agent — golden repair pairs, tiers, budget, and apply (hermetic).

The LLM is scripted (no live services, INV-5): each test drives the ReAct loop
with a fixed action sequence, so the whole suite runs in CI. The trust basis is
the real deterministic validator — a scripted patch is accepted only if the
validator actually clears the finding.
"""

from __future__ import annotations

import shutil

import pytest

from learnarken.repair import PatchStatus, RepairMode, RiskTier, run_repair
from learnarken.repair.agent import LLMResponse, repair_finding
from learnarken.repair.config import Budget, SandboxPolicy
from learnarken.repair.sandbox import Sandbox
from learnarken.repair.tools import Toolbox, finding_key
from learnarken.validation import analyze_package
from learnarken.validation.report import Finding

# The dangling dmRef in package-b (VIO-1 / XREF-001) and its minimal fix.
_XREF1_FILE = "DMC-LA100-A-29-10-00-00A-040A-D_EN-CA.xml"
_XREF1_XPATH = "//dmRef[.//dmCode[@systemCode='29' and @subSystemCode='2' and @infoCode='520']]"


class ScriptedLLM:
    """Replays a fixed action list; repeats the last action when exhausted."""

    def __init__(self, actions: list[dict], tokens: int = 100) -> None:
        self.actions = actions
        self.tokens = tokens
        self.calls = 0

    def __call__(self, system: str, user: str) -> LLMResponse:
        action = self.actions[min(self.calls, len(self.actions) - 1)]
        self.calls += 1
        return LLMResponse(action=action, tokens=self.tokens)


def _finding(package: str, rule_id: str) -> Finding:
    report, _ = analyze_package(package)
    return next(f for f in report.findings if f.rule_id == rule_id)


def _fix_xref1_action(finding: Finding) -> dict:
    return {
        "thought": "the dmRef targets an absent module; remove the dangling reference",
        "tool": "propose_patch",
        "args": {
            "file": finding.file,
            "target_key": finding_key(finding),
            "edits": [{"op": "remove_element", "xpath": _XREF1_XPATH}],
        },
    }


# --- golden repair pair (INV-3) ------------------------------------------


def test_xref1_golden_repair_pair():
    """A scripted patch clears exactly VIO-1 and introduces zero new findings."""
    finding = _finding("samples/package-b", "XREF-001")
    llm = ScriptedLLM([_fix_xref1_action(finding)])
    with Sandbox("samples/package-b", SandboxPolicy()) as sb:
        patch = repair_finding(finding, Toolbox(sb), llm, Budget(), RiskTier.APPLY_ELIGIBLE)
    assert patch.status == PatchStatus.PATCHED
    assert patch.validator_delta.is_clean_fix
    assert patch.validator_delta.introduced == []
    assert finding_key(finding) in patch.validator_delta.cleared
    assert patch.diff and "dmRef" in patch.diff


def test_legal_package_has_nothing_to_repair():
    report = run_repair(
        "samples/package-a", llm=ScriptedLLM([{"tool": "run_validator", "args": {}}])
    )
    assert report.findings_targeted == 0
    assert report.patches == []


# --- risk-tier routing ----------------------------------------------------


def test_vio6_is_dry_run_only_and_never_applied(tmp_path):
    """XREF-004 (out-of-domain) is high-risk: never written, even under --apply."""
    pkg = tmp_path / "package-b"
    shutil.copytree("samples/package-b", pkg)
    before = (pkg / "DMC-SS200-A-58-10-00-00A-520A-A_EN-CA.xml").read_bytes()
    # Approve-everything: proves the gate, not the human, blocks a dry-run-only class.
    report = run_repair(
        str(pkg),
        mode=RepairMode.APPLY,
        only=["XREF-004"],
        approver=lambda _p: True,
        llm=ScriptedLLM([{"tool": "run_validator", "args": {}}]),
    )
    xref4 = next(p for p in report.patches if p.rule_id == "XREF-004")
    assert xref4.risk_tier == RiskTier.DRY_RUN_ONLY
    assert xref4.status != PatchStatus.APPLIED
    assert (pkg / "DMC-SS200-A-58-10-00-00A-520A-A_EN-CA.xml").read_bytes() == before


# --- apply: approve / decline (Ruling 1, INV-2) --------------------------


def test_apply_approve_writes_atomically(tmp_path):
    pkg = tmp_path / "package-b"
    shutil.copytree("samples/package-b", pkg)
    finding = _finding(str(pkg), "XREF-001")
    report = run_repair(
        str(pkg),
        mode=RepairMode.APPLY,
        only=["XREF-001"],
        approver=lambda _p: True,
        llm=ScriptedLLM([_fix_xref1_action(finding)]),
    )
    applied = next(p for p in report.patches if p.rule_id == "XREF-001")
    assert applied.status == PatchStatus.APPLIED
    # The active corpus now validates without XREF-001, and no leftover .bak/.new.
    after, _ = analyze_package(str(pkg))
    assert not any(f.rule_id == "XREF-001" for f in after.findings)
    assert not list(pkg.glob("*.bak")) and not list(pkg.glob("*.new"))


def test_apply_decline_leaves_corpus_untouched(tmp_path):
    pkg = tmp_path / "package-b"
    shutil.copytree("samples/package-b", pkg)
    finding = _finding(str(pkg), "XREF-001")
    snapshot = (pkg / _XREF1_FILE).read_bytes()
    report = run_repair(
        str(pkg),
        mode=RepairMode.APPLY,
        only=["XREF-001"],
        approver=lambda _p: False,  # human declines
        llm=ScriptedLLM([_fix_xref1_action(finding)]),
    )
    declined = next(p for p in report.patches if p.rule_id == "XREF-001")
    assert declined.status == PatchStatus.DECLINED
    assert (pkg / _XREF1_FILE).read_bytes() == snapshot  # byte-identical


# --- budget circuit-breaker (research §5.1) ------------------------------


def test_no_progress_breaker_trips():
    """Repeated rejected patches trip the oscillation breaker — bounded, closed."""
    finding = _finding("samples/package-b", "XREF-001")
    # A patch whose xpath matches nothing → never accepted → no-progress climbs.
    dud = {
        "tool": "propose_patch",
        "args": {
            "file": finding.file,
            "edits": [{"op": "remove_element", "xpath": "//nonexistent"}],
        },
    }
    llm = ScriptedLLM([dud])
    budget = Budget(max_iterations=50, no_progress_limit=3)
    with Sandbox("samples/package-b", SandboxPolicy()) as sb:
        patch = repair_finding(finding, Toolbox(sb), llm, budget, RiskTier.APPLY_ELIGIBLE)
    assert patch.status == PatchStatus.REFUSED
    assert patch.iterations_used <= 3  # stopped by no-progress, not the iteration cap


def test_token_budget_breaker_trips():
    finding = _finding("samples/package-b", "XREF-001")
    llm = ScriptedLLM([{"tool": "run_validator", "args": {}}], tokens=10_000)
    budget = Budget(max_iterations=50, max_tokens=100)
    with Sandbox("samples/package-b", SandboxPolicy()) as sb:
        patch = repair_finding(finding, Toolbox(sb), llm, budget, RiskTier.APPLY_ELIGIBLE)
    assert patch.status == PatchStatus.BUDGET_EXHAUSTED
    assert patch.iterations_used == 1


def test_iteration_cap_refuses_closed():
    finding = _finding("samples/package-b", "XREF-001")
    llm = ScriptedLLM([{"tool": "run_validator", "args": {}}])  # never proposes a patch
    budget = Budget(max_iterations=4, no_progress_limit=99, max_tokens=10_000_000)
    with Sandbox("samples/package-b", SandboxPolicy()) as sb:
        patch = repair_finding(finding, Toolbox(sb), llm, budget, RiskTier.APPLY_ELIGIBLE)
    assert patch.status == PatchStatus.REFUSED
    assert patch.iterations_used == 4


# --- over-repair guard ----------------------------------------------------


def test_patch_introducing_new_finding_is_rejected():
    """A patch that clears the target but breaks something else is not accepted."""
    finding = _finding("samples/package-b", "XREF-001")
    # Remove a required-by-schema element to force a new finding while (maybe)
    # touching the target file: the guard must reject it and revert.
    bad = {
        "tool": "propose_patch",
        "args": {
            "file": finding.file,
            "target_key": finding_key(finding),
            "edits": [{"op": "remove_element", "xpath": "/dmodule/identAndStatusSection"}],
        },
    }
    llm = ScriptedLLM([bad])
    with Sandbox("samples/package-b", SandboxPolicy()) as sb:
        tb = Toolbox(sb)
        patch = repair_finding(
            finding, tb, llm, Budget(no_progress_limit=1), RiskTier.APPLY_ELIGIBLE
        )
        # the file must be reverted — the sandbox still shows the original findings
        assert any(f.rule_id == "XREF-001" for f in tb.validate())
    assert patch.status == PatchStatus.REFUSED


# --- config, patch engine, crash recovery --------------------------------


def test_config_override_applies_cli_flags():
    from learnarken.repair.config import Budget as B
    from learnarken.repair.config import load_repair_config, override_budget

    base = load_repair_config().budget
    overridden = override_budget(base, max_iterations=3, max_tokens=None)
    assert overridden.max_iterations == 3
    assert overridden.max_tokens == base.max_tokens  # untouched
    assert isinstance(base, B)


def test_patch_engine_ops():
    from learnarken.repair.models import EditOp
    from learnarken.repair.patch import PatchError, apply_edits

    doc = b'<?xml version="1.0"?><r><a x="1">t</a><b/></r>'
    out = apply_edits(doc, [EditOp(op="set_attr", xpath="//a", attr="x", value="2")])
    assert b'x="2"' in out
    out = apply_edits(doc, [EditOp(op="set_text", xpath="//a", value="z")])
    assert b">z<" in out
    out = apply_edits(doc, [EditOp(op="remove_element", xpath="//b")])
    assert b"<b/>" not in out
    # ambiguous xpath (matches 2 nodes) is refused — keeps patches minimal
    doc2 = b"<r><a/><a/></r>"
    with pytest.raises(PatchError):
        apply_edits(doc2, [EditOp(op="remove_element", xpath="//a")])


def test_recover_interrupted_apply(tmp_path):
    from learnarken.repair.apply import recover_interrupted_apply

    active = tmp_path / "DMC-x.xml"
    active.write_text("NEW-HALF-WRITTEN")
    (tmp_path / "DMC-x.xml.bak").write_text("OLD-GOOD")  # crash left a backup
    (tmp_path / "DMC-x.xml.new").write_text("scratch")
    (tmp_path / ".repair-apply.journal").write_text("DMC-x.xml")  # our own journal
    restored = recover_interrupted_apply(tmp_path)
    assert restored == ["DMC-x.xml"]
    assert active.read_text() == "OLD-GOOD"  # rolled back to last known-good
    assert not list(tmp_path.glob("*.bak")) and not list(tmp_path.glob("*.new"))


def test_recover_ignores_unjournalled_bak(tmp_path):
    """A stray .bak with no journal is NOT trusted (red-team #11)."""
    from learnarken.repair.apply import recover_interrupted_apply

    active = tmp_path / "DMC-x.xml"
    active.write_text("CURRENT")
    (tmp_path / "DMC-x.xml.bak").write_text("ATTACKER-PLANTED")
    restored = recover_interrupted_apply(tmp_path)
    assert restored == []
    assert active.read_text() == "CURRENT"  # untouched
