"""Day 13 Tree-of-Thoughts repair — selection, veto, refusal (hermetic).

The LLM is scripted per role (no live services, INV-5). The trust basis is the
real deterministic validator: a candidate is selectable only if `propose_patch`
actually cleared the finding — never because the LLM claimed success (Decision 3b).
"""

from __future__ import annotations

from learnarken.repair.agent import LLMResponse
from learnarken.repair.config import Budget
from learnarken.repair.models import PatchStatus, ProposedPatch, RiskTier
from learnarken.repair.tools import finding_key
from learnarken.repair.tot import (
    DEFAULT_ROLES,
    REWARD_HACK_DELETE_FRACTION,
    Candidate,
    _make_candidate,
    _sequential_runner,
    concurrent_runner,
    tot_repair,
)
from learnarken.validation import analyze_package
from learnarken.validation.report import Finding

_XREF1_XPATH = "//dmRef[.//dmCode[@systemCode='29' and @subSystemCode='2' and @infoCode='520']]"


class ScriptedLLM:
    def __init__(self, actions: list[dict], tokens: int = 100) -> None:
        self.actions = actions
        self.tokens = tokens
        self.calls = 0

    def __call__(self, system: str, user: str) -> LLMResponse:
        action = self.actions[min(self.calls, len(self.actions) - 1)]
        self.calls += 1
        return LLMResponse(action=action, tokens=self.tokens)


def _finding(rule_id: str) -> Finding:
    report, _ = analyze_package("samples/package-b")
    return next(f for f in report.findings if f.rule_id == rule_id)


def _fix(finding: Finding) -> dict:
    return {
        "thought": "remove the dangling dmRef",
        "tool": "propose_patch",
        "args": {
            "file": finding.file,
            "target_key": finding_key(finding),
            "edits": [{"op": "remove_element", "xpath": _XREF1_XPATH}],
        },
    }


_DUD = {
    "thought": "try nothing that matches",
    "tool": "propose_patch",
    "args": {"file": "x", "edits": [{"op": "remove_element", "xpath": "//nonexistent"}]},
}


def _llm_for(scripts: dict[str, list[dict]]):
    return lambda role: ScriptedLLM(scripts[role.name])


# --- selection: validator decides, least-invasive wins --------------------


def test_tot_selects_validator_passing_candidate():
    finding = _finding("XREF-001")
    fix = _fix(finding)
    scripts = {"conservative": [fix], "schema_focused": [_DUD], "reference_focused": [fix]}
    result = tot_repair(
        finding,
        "samples/package-b",
        llm_for=_llm_for(scripts),
        budget=Budget(no_progress_limit=1),
    )
    # Two roles produced a validator-passing fix; the dud role did not.
    passers = {c.role for c in result.candidates if c.selectable}
    assert passers == {"conservative", "reference_focused"}
    # Deterministic tie-break picks the earliest role order (conservative).
    assert result.selected is not None and result.selected.role == "conservative"
    assert "validator-selected" in result.selection_reason
    # 3x visible token cost (Decision 4) — all candidates counted.
    assert result.total_tokens == sum(c.tokens_used for c in result.candidates)


def test_tot_candidates_carry_explainability_fields():
    """Each candidate carries rationale / target / patch summary / risk note (3a)."""
    finding = _finding("XREF-001")
    roles = ("conservative", "schema_focused", "reference_focused")
    scripts = {name: [_fix(finding)] for name in roles}
    result = tot_repair(
        finding, "samples/package-b", llm_for=_llm_for(scripts), budget=Budget(no_progress_limit=1)
    )
    for c in result.candidates:
        assert c.target_finding and c.rationale and c.patch_summary and c.risk_note
        assert len(result.candidates) == len(DEFAULT_ROLES)


def test_tot_refuses_when_no_candidate_passes_validator():
    """All roles fail → no selection, fail closed (INV-4). The LLM cannot talk its
    way to success; only the validator decides."""
    finding = _finding("XREF-001")
    scripts = {name: [_DUD] for name in ("conservative", "schema_focused", "reference_focused")}
    result = tot_repair(
        finding, "samples/package-b", llm_for=_llm_for(scripts), budget=Budget(no_progress_limit=1)
    )
    assert result.selected is None
    assert "refuse" in result.selection_reason
    assert all(not c.selectable for c in result.candidates)


# --- reward-hacking veto (Decision 3 / scan B3) ---------------------------


def test_reward_hack_veto_fires_on_large_deletion(tmp_path):
    """A validator-passing patch that deletes most of the source is vetoed and
    becomes unselectable, even though the validator accepted it."""
    src = tmp_path / "DMC-x.xml"
    src.write_text("\n".join(f"<line{i}/>" for i in range(20)) + "\n")
    # A diff that removes 15 of 20 lines (75% > 50% threshold).
    big_delete_diff = "".join(f"-<line{i}/>\n" for i in range(15))
    patch = ProposedPatch(
        rule_id="XREF-001",
        layer="L3",
        file="DMC-x.xml",
        message="m",
        risk_tier=RiskTier.APPLY_ELIGIBLE,
        status=PatchStatus.PATCHED,
        diff=big_delete_diff,
    )
    candidate = _make_candidate(DEFAULT_ROLES[0], tmp_path, patch, RiskTier.APPLY_ELIGIBLE)
    assert candidate.deleted_fraction > REWARD_HACK_DELETE_FRACTION
    assert candidate.vetoed and not candidate.selectable
    assert "reward-hack" in candidate.veto_reason


def test_small_edit_is_not_vetoed(tmp_path):
    src = tmp_path / "DMC-x.xml"
    src.write_text("\n".join(f"<line{i}/>" for i in range(20)) + "\n")
    small_diff = "-<line0/>\n+<line0 fixed='1'/>\n"
    patch = ProposedPatch(
        rule_id="XREF-001",
        layer="L3",
        file="DMC-x.xml",
        message="m",
        risk_tier=RiskTier.APPLY_ELIGIBLE,
        status=PatchStatus.PATCHED,
        diff=small_diff,
    )
    candidate = _make_candidate(DEFAULT_ROLES[0], tmp_path, patch, RiskTier.APPLY_ELIGIBLE)
    assert not candidate.vetoed and candidate.selectable


# --- red-team fixes: fail-closed candidate handling -----------------------


def _candidate(**kw) -> Candidate:
    base = {
        "role": "c",
        "target_finding": "t",
        "rationale": "r",
        "patch_summary": "s",
        "risk_note": "n",
        "status": PatchStatus.PATCHED,
        "validator_passed": True,
    }
    return Candidate(**{**base, **kw})


def test_dry_run_only_candidate_is_not_selectable():
    """A high-risk (dry-run-only) candidate that verified is NOT apply-ready:
    `selected` must never return it (red-team P1)."""
    c = _candidate(status=PatchStatus.DRY_RUN_ONLY, validator_passed=True)
    assert not c.selectable


def test_sequential_runner_converts_exception_to_refused():
    """One candidate raising must not abort the ToT run — it becomes a refused
    candidate so the other roles still count (red-team P1, fail closed)."""

    def boom() -> Candidate:
        raise RuntimeError("llm transport error")

    out = _sequential_runner([boom, lambda: _candidate(role="ok")])
    assert out[0].status == PatchStatus.REFUSED and not out[0].selectable
    assert out[1].role == "ok" and out[1].selectable


def test_veto_on_unreadable_source_fails_closed(tmp_path):
    """If the source file can't be read, the deletion veto cannot verify the
    patch — it vetoes rather than assuming 0% deleted (red-team P2)."""
    patch = ProposedPatch(
        rule_id="XREF-001",
        layer="L3",
        file="MISSING.xml",
        message="m",
        risk_tier=RiskTier.APPLY_ELIGIBLE,
        status=PatchStatus.PATCHED,
        diff="-<a/>\n",
    )
    c = _make_candidate(DEFAULT_ROLES[0], tmp_path, patch, RiskTier.APPLY_ELIGIBLE)
    assert c.vetoed and not c.selectable and "unreadable" in c.veto_reason


# --- fail-closed tool dispatch (INV-4, exposed by ToT) --------------------


def test_read_module_missing_file_is_observation_not_crash():
    """A hallucinated filename (common when 3 candidates sample at temp>0) must
    return an observation error, never crash the run (INV-4 fail-closed)."""
    from learnarken.repair.config import SandboxPolicy
    from learnarken.repair.sandbox import Sandbox
    from learnarken.repair.tools import Toolbox

    with Sandbox("samples/package-b", SandboxPolicy()) as sb:
        obs = Toolbox(sb).call("read_module", {"file": "DMC-DOES-NOT-EXIST.xml"})
    assert "error" in obs and "FileNotFoundError" in obs["error"]


# --- concurrent runner equivalence (Decision 7 seam) ----------------------


def test_concurrent_runner_matches_sequential():
    finding = _finding("XREF-001")
    fix = _fix(finding)
    scripts = {"conservative": [fix], "schema_focused": [_DUD], "reference_focused": [fix]}
    seq = tot_repair(
        finding, "samples/package-b", llm_for=_llm_for(scripts), budget=Budget(no_progress_limit=1)
    )
    con = tot_repair(
        finding,
        "samples/package-b",
        llm_for=_llm_for(scripts),
        budget=Budget(no_progress_limit=1),
        runner=concurrent_runner(limit=3, timeout=30.0),
    )
    assert seq.selected.role == con.selected.role == "conservative"
    assert {c.role for c in seq.candidates if c.selectable} == {
        c.role for c in con.candidates if c.selectable
    }
