"""Tree-of-Thoughts repair: best-of-N candidates + deterministic validator
selection (Day 13, Decision 3; docs/specs/day13.md).

This is the minimal usable form of inference-time search — Best-of-N = a depth-1,
width-N Tree of Thoughts (scan B2). For one finding it generates **N heterogeneous
role candidates** (conservative / schema-focused / reference-focused — Decision 3b),
each an independent ReAct run in its **own sandbox**, and **selects by the
deterministic sandbox validator, never by LLM self-judgment** (Decision 3b, INV-4).
Diversity is explainable strategy (distinct roles at low/mid-low temperature), not
creative-writing randomness (Decision 3 reason).

Reuse over reinvention: the candidate generator is Day 7's `repair_finding`, the
validator is Day 7's `propose_patch` (the "perfect ORM" / engineering world-model,
scan B2), and the reward-hacking veto reuses the same diff-distance idea as the
apply gate (scan B3). Each candidate is a fully self-contained sandbox job, which
is exactly what lets the asyncio orchestrator evaluate them concurrently
(`learnarken.perf.orchestrate`, Decision 7) — the two Day-13 tracks' seam.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from learnarken.repair.agent import LLMFn, LLMResponse, repair_finding
from learnarken.repair.config import Budget, SandboxPolicy, load_repair_config
from learnarken.repair.models import PatchStatus, ProposedPatch, RiskTier, risk_tier_for
from learnarken.repair.sandbox import Sandbox
from learnarken.repair.tools import Toolbox, finding_key
from learnarken.validation import DEFAULT_ACCEPTED_MODELS
from learnarken.validation.report import Finding

# Fraction of the source file a single patch may delete before it is vetoed as a
# reward-hack (delete-the-node-to-silence-the-finding, scan B3 / DR A pitfall 2).
#
# HONEST LIMITATION (toy scale, INV-7): this is a *crude, scale-sensitive* signal.
# On a small module a *legitimate* removal — e.g. deleting a dangling dmRef to clear
# XREF-001, which Day 7 itself applies — is already ~25% of the file, so a tight
# threshold false-flags the correct fix. Its real job is catching *gross* "delete
# most of the file" hacks; the `propose_patch` no-new-findings guard already catches
# destructive deletions that break structure. Distinguishing a reference removal
# from a business-data removal needs a per-finding-class semantic veto — Roadmap.
# 0.5 is chosen so the legitimate reference removals are not vetoed here.
REWARD_HACK_DELETE_FRACTION = 0.5


@dataclass(frozen=True)
class Role:
    """A repair persona: a system-prompt preamble + a sampling temperature. The
    preamble is prepended to the shared ReAct SYSTEM_PROMPT so each candidate
    approaches the same finding from a different, *explainable* angle."""

    name: str
    preamble: str
    temperature: float


CONSERVATIVE = Role(
    name="conservative",
    preamble="ROLE: conservative fixer. Prefer the smallest possible edit — "
    "set_attr or set_text on the exact node the finding points at. Never remove an "
    "element if an attribute/text edit can clear the finding. Change as little as possible.",
    temperature=0.2,
)
SCHEMA_FOCUSED = Role(
    name="schema_focused",
    preamble="ROLE: schema-focused fixer. Reason from the project mini-XSD and the "
    "S1000D-like structure: make the module structurally conformant. Query the XML "
    "structure before editing; ensure required elements/attributes are present and correct.",
    temperature=0.2,
)
REFERENCE_FOCUSED = Role(
    name="reference_focused",
    preamble="ROLE: reference-focused fixer. Reason from cross-file references "
    "(dmRef, ICN, DML registrations, issueInfo). Use search_corpus to see how sibling "
    "modules encode the correct reference, then align the target to a real, resolvable one.",
    temperature=0.4,
)

DEFAULT_ROLES: tuple[Role, ...] = (CONSERVATIVE, SCHEMA_FOCUSED, REFERENCE_FOCUSED)


class Candidate(BaseModel):
    """One role's patch attempt, with the explainability fields Decision 3a
    requires (rationale / target finding / patch summary / risk note)."""

    role: str
    target_finding: str
    rationale: str
    patch_summary: str
    risk_note: str
    status: PatchStatus
    validator_passed: bool
    diff: str = ""
    deleted_fraction: float = 0.0
    vetoed: bool = False
    veto_reason: str = ""
    tokens_used: int = 0

    @property
    def selectable(self) -> bool:
        """A candidate may be selected only if it is an apply-ready verified fix.

        Requires `status == PATCHED` (red-team P1): after `tot_repair` downgrades a
        high-risk candidate to DRY_RUN_ONLY, `validator_passed` stays True, so
        gating on status is what stops a dry-run-only proposal from being returned
        as a `selected` (apply-ready) fix. Plus the reward-hacking veto (Decision
        3b, INV-4)."""
        return self.status == PatchStatus.PATCHED and self.validator_passed and not self.vetoed


class ToTResult(BaseModel):
    """The outcome for one finding: every candidate + the validator-selected
    winner (or None → refuse, fail closed)."""

    target_finding: str
    rule_id: str
    candidates: list[Candidate] = Field(default_factory=list)
    selected: Candidate | None = None
    selection_reason: str = ""
    total_tokens: int = 0


CandidateJob = Callable[[], Candidate]
# A runner evaluates the per-candidate jobs. Default is sequential; the asyncio
# orchestrator (Decision 7) supplies a concurrent one — the tracks' seam.
CandidateRunner = Callable[[Sequence[CandidateJob]], list[Candidate]]


def _refused_candidate(label: str, reason: str) -> Candidate:
    """A fail-closed placeholder for a candidate that could not be evaluated
    (exception / timeout). Never selectable (status REFUSED)."""
    return Candidate(
        role=label,
        target_finding="",
        rationale=reason,
        patch_summary="no verified patch",
        risk_note=reason,
        status=PatchStatus.REFUSED,
        validator_passed=False,
    )


def _sequential_runner(jobs: Sequence[CandidateJob]) -> list[Candidate]:
    """Evaluate candidates in order, converting a per-candidate exception into a
    refused candidate (red-team P1): one role's LLM transport error must not abort
    the whole ToT run and starve the other roles — same fail-closed contract as
    `concurrent_runner`."""
    results: list[Candidate] = []
    for i, job in enumerate(jobs):
        try:
            results.append(job())
        except Exception as exc:  # noqa: BLE001 — captured as a refused candidate, not raised
            reason = f"candidate error: {type(exc).__name__}: {exc}"
            results.append(_refused_candidate(f"job{i}", reason))
    return results


def concurrent_runner(*, limit: int = 3, timeout: float = 60.0) -> CandidateRunner:
    """A CandidateRunner that fans the candidate jobs out concurrently via the
    asyncio orchestrator (Decision 7) — this is the Track-A/Track-B seam. A job
    that times out or errors becomes a **refused** candidate (fail closed, INV-4),
    so one bad candidate never sinks the whole finding (Decision 7d)."""
    from learnarken.perf.orchestrate import run_bounded_sync

    def _run(jobs: Sequence[CandidateJob]) -> list[Candidate]:
        outcomes = run_bounded_sync(list(jobs), limit=limit, timeout=timeout)
        results: list[Candidate] = []
        for outcome in outcomes:
            if outcome.status == "success" and outcome.value is not None:
                results.append(outcome.value)
            else:
                results.append(
                    _refused_candidate(
                        f"job{outcome.index}",
                        f"orchestration {outcome.status}: {outcome.error}",
                    )
                )
        return results

    return _run


def _role_llm(role: Role) -> LLMFn:
    """Production LLM for a role: M3 via chat_json with the role preamble + the
    role temperature. Mirrors `agent.minimax_llm` but parameterized (kept here so
    the Day 7 path is untouched)."""

    def _call(system: str, user: str) -> LLMResponse:
        from learnarken.llm.minimax import LLMContractError, chat_json

        try:
            result = chat_json(
                f"{role.preamble}\n\n{system}",
                user,
                temperature=role.temperature,
                max_tokens=1024,
            )
        except LLMContractError as exc:
            return LLMResponse(action={"thought": f"contract error: {exc}", "tool": ""}, tokens=256)
        tokens = int(result.usage.get("total_tokens", 0))
        if tokens <= 0:
            tokens = (len(system) + len(user) + len(result.raw_content)) // 4
        return LLMResponse(action=result.parsed, tokens=tokens)

    return _call


def _deleted_fraction(package_dir: Path, patch: ProposedPatch) -> float | None:
    """Fraction of the source file's lines the patch removes — the reward-hacking
    signal (a big net deletion means "delete the node to silence the finding").

    Returns None when the source cannot be read: the caller then **vetoes** (fail
    closed, red-team P2) rather than treating an unreadable source as 0% deleted.
    `patch.file` is validator-sourced (a package basename bound server-side, not
    LLM-chosen), but reject traversal defensively before reading."""
    if not patch.diff:
        return 0.0
    if "/" in patch.file or "\\" in patch.file or ".." in patch.file:
        return None
    source = package_dir / patch.file
    try:
        original_lines = max(1, len(source.read_text(encoding="utf-8").splitlines()))
    except OSError:
        return None
    removed = sum(
        1 for line in patch.diff.splitlines() if line.startswith("-") and not line.startswith("---")
    )
    return removed / original_lines


def _summarize(patch: ProposedPatch) -> str:
    if not patch.edits:
        return "no verified patch"
    return "; ".join(f"{e.op} @ {e.xpath}" for e in patch.edits)[:300]


def _make_candidate(
    role: Role, package_dir: Path, patch: ProposedPatch, tier: RiskTier
) -> Candidate:
    validator_passed = patch.status == PatchStatus.PATCHED
    deleted = _deleted_fraction(package_dir, patch) if validator_passed else 0.0
    if validator_passed and deleted is None:
        # Source unreadable / suspicious path → cannot verify the patch is not a
        # reward-hack, so veto (fail closed, red-team P2).
        vetoed = True
        deleted = 0.0
        veto_reason = "source unreadable — cannot verify deletion (fail closed)"
    elif validator_passed and deleted > REWARD_HACK_DELETE_FRACTION:
        vetoed = True
        veto_reason = (
            f"deletes {deleted:.0%} of the source (> {REWARD_HACK_DELETE_FRACTION:.0%}) — "
            "reward-hack veto (delete-the-node-to-silence-the-finding)"
        )
    else:
        vetoed, deleted, veto_reason = False, (deleted or 0.0), ""
    risk_note = (
        f"tier={tier}; reward-hack check: {'VETOED — ' + veto_reason if vetoed else 'ok'}"
    )
    return Candidate(
        role=role.name,
        target_finding=f"{patch.rule_id}@{patch.file}",
        rationale=patch.rationale or "(no reasoning recorded)",
        patch_summary=_summarize(patch),
        risk_note=risk_note,
        status=patch.status,
        validator_passed=validator_passed,
        diff=patch.diff,
        deleted_fraction=round(deleted, 4),
        vetoed=vetoed,
        veto_reason=veto_reason,
        tokens_used=patch.tokens_used,
    )


def _candidate_job(
    role: Role,
    finding: Finding,
    package_dir: Path,
    budget: Budget,
    policy: SandboxPolicy,
    accepted_models: tuple[str, ...],
    tier: RiskTier,
    llm_for: Callable[[Role], LLMFn],
) -> Candidate:
    """Run one role's ReAct repair in its **own** sandbox and package the result.

    Own sandbox is essential: an accepted patch mutates the jail, so candidates
    must not share one. Self-containment is also what makes the job safe to run
    concurrently (Decision 7)."""
    llm = llm_for(role)
    with Sandbox(package_dir, policy) as sandbox:
        toolbox = Toolbox(sandbox, accepted_models)
        patch = repair_finding(finding, toolbox, llm, budget, tier)
    return _make_candidate(role, package_dir, patch, tier)


def _select(candidates: list[Candidate], roles: Sequence[Role]) -> tuple[Candidate | None, str]:
    """Deterministic selection (Decision 3b): among validator-passing, non-vetoed
    candidates prefer the least invasive (smallest deletion), then role order, then
    diff text for a total order. No LLM judges the winner."""
    order = {role.name: i for i, role in enumerate(roles)}
    selectable = [c for c in candidates if c.selectable]
    if not selectable:
        n_vetoed = sum(1 for c in candidates if c.vetoed)
        return None, (
            f"no selectable candidate ({len(candidates)} tried, {n_vetoed} vetoed) — "
            "refuse, fail closed (INV-4)"
        )
    winner = min(selectable, key=lambda c: (c.deleted_fraction, order.get(c.role, 99), c.diff))
    return winner, (
        f"validator-selected role={winner.role} (least invasive of "
        f"{len(selectable)} passing candidates; deterministic, no LLM judge)"
    )


def build_candidate_jobs(
    finding: Finding,
    package_dir: str | Path,
    *,
    roles: Sequence[Role] = DEFAULT_ROLES,
    llm_for: Callable[[Role], LLMFn] | None = None,
    budget: Budget | None = None,
    sandbox_policy: SandboxPolicy | None = None,
    accepted_models: tuple[str, ...] = DEFAULT_ACCEPTED_MODELS,
) -> list[CandidateJob]:
    """The per-role candidate jobs for one finding, unevaluated. Each is a
    self-contained sandbox run — safe to evaluate sequentially or concurrently.
    Exposed so the asyncio benchmark (Decision 7) can drive them through the
    orchestrator directly and read real success/timeout/error outcomes."""
    config = load_repair_config()
    budget = budget or config.budget
    policy = sandbox_policy or config.sandbox
    llm_for = llm_for or _role_llm
    directory = Path(package_dir)
    tier = risk_tier_for(finding.rule_id)
    return [
        (
            lambda role=role: _candidate_job(
                role, finding, directory, budget, policy, accepted_models, tier, llm_for
            )
        )
        for role in roles
    ]


def tot_repair(
    finding: Finding,
    package_dir: str | Path,
    *,
    roles: Sequence[Role] = DEFAULT_ROLES,
    llm_for: Callable[[Role], LLMFn] | None = None,
    budget: Budget | None = None,
    sandbox_policy: SandboxPolicy | None = None,
    accepted_models: tuple[str, ...] = DEFAULT_ACCEPTED_MODELS,
    runner: CandidateRunner | None = None,
) -> ToTResult:
    """Generate N role candidates for one finding and select by the validator.

    `runner` evaluates the candidate jobs — sequential by default; pass the
    asyncio orchestrator's runner (Decision 7) to fan them out concurrently.
    `llm_for` maps a role to its LLM (production role LLM by default; tests inject
    scripted per-role LLMs for hermetic runs).
    """
    tier = risk_tier_for(finding.rule_id)
    runner = runner or _sequential_runner
    jobs = build_candidate_jobs(
        finding,
        package_dir,
        roles=roles,
        llm_for=llm_for,
        budget=budget,
        sandbox_policy=sandbox_policy,
        accepted_models=accepted_models,
    )
    candidates = runner(jobs)
    # High-risk classes are never applied even if a candidate verifies (Day 7
    # discipline): reflect that in the status so downstream never treats it as
    # apply-ready.
    for candidate in candidates:
        if tier == RiskTier.DRY_RUN_ONLY and candidate.status == PatchStatus.PATCHED:
            candidate.status = PatchStatus.DRY_RUN_ONLY

    selected, reason = _select(candidates, roles)
    return ToTResult(
        target_finding=finding_key(finding),
        rule_id=finding.rule_id,
        candidates=candidates,
        selected=selected,
        selection_reason=reason,
        total_tokens=sum(c.tokens_used for c in candidates),
    )
