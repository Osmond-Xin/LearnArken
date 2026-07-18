"""The ReAct repair loop for one finding (Day 7).

`repair_finding` drives an injected LLM through Reason→Act→Observe cycles until
a patch is verified clean or a circuit-breaker trips. The LLM is a callable so
tests can script it deterministically (INV-5, hermetic CI) and production wraps
`llm/minimax.py`.

Circuit-breaker (research §5.1, spec Decision 4) — three independent bounds, any
of which fails the finding **closed** (never an unbounded loop):
  1. max_iterations   — hard cap on ReAct steps
  2. max_tokens       — cumulative LLM tokens
  3. no_progress_limit — consecutive rejected patches (the oscillation case, Q3)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from learnarken.repair.config import Budget
from learnarken.repair.models import (
    EditOp,
    PatchStatus,
    ProposedPatch,
    RiskTier,
    ValidatorDelta,
)
from learnarken.repair.prompt import SYSTEM_PROMPT, render_user
from learnarken.repair.tools import Toolbox, finding_key
from learnarken.validation.report import Finding


@dataclass
class LLMResponse:
    """One agent decision + the token cost of producing it."""

    action: dict  # {"thought": str, "tool": str, "args": dict}
    tokens: int = 0


# system, user -> decision. Raises LLMError on transport failure (fail closed).
LLMFn = Callable[[str, str], LLMResponse]


@dataclass
class _Trace:
    thoughts: list[str] = field(default_factory=list)
    evidence: set[str] = field(default_factory=set)


def _collect_evidence(tool: str, args: dict, obs: dict, trace: _Trace) -> None:
    if tool == "read_module" and "file" in args:
        trace.evidence.add(str(args["file"]))
    if tool == "search_corpus":
        for hit in obs.get("hits", []):
            if hit.get("chunk_id"):
                trace.evidence.add(hit["chunk_id"])


def repair_finding(
    finding: Finding,
    toolbox: Toolbox,
    llm: LLMFn,
    budget: Budget,
    tier: RiskTier,
) -> ProposedPatch:
    """Run the ReAct loop for a single finding; always returns a ProposedPatch."""
    patch = ProposedPatch.from_finding(finding, tier, PatchStatus.REFUSED)
    target_key = finding_key(finding)
    # Bind the target server-side so the LLM cannot retarget or cross-patch
    # (red-team #4/#5); propose_patch enforces both.
    toolbox.sandbox.target_key = target_key
    toolbox.sandbox.target_file = finding.file
    trace = _Trace()
    history: list[dict] = []
    tokens = 0
    no_progress = 0

    for step in range(budget.max_iterations):
        patch.iterations_used = step + 1
        response = llm(SYSTEM_PROMPT, render_user(finding, history, target_key))
        tokens += max(response.tokens, 0)
        patch.tokens_used = tokens
        if tokens > budget.max_tokens:
            patch.status = PatchStatus.BUDGET_EXHAUSTED
            break

        action = response.action or {}
        if action.get("thought"):
            trace.thoughts.append(str(action["thought"]))
        tool = action.get("tool")
        args = action.get("args") or {}
        if not isinstance(tool, str) or not tool:
            # Contract violation: record it, count it as a wasted (no-progress)
            # step so a model that never emits a tool cannot spin forever.
            history.append({"error": "no tool selected — emit one JSON action with a 'tool'"})
            no_progress += 1
            if no_progress >= budget.no_progress_limit:
                break
            continue

        obs = toolbox.call(tool, args)
        _collect_evidence(tool, args, obs, trace)

        if tool == "propose_patch":
            if obs.get("accepted"):
                patch.status = PatchStatus.PATCHED
                patch.edits = [EditOp(**e) for e in args.get("edits", [])]
                patch.diff = obs.get("diff", "")
                patch.validator_delta = ValidatorDelta(**obs["delta"])
                break
            no_progress += 1
            if no_progress >= budget.no_progress_limit:
                history.append({"propose_patch": obs})
                break
        else:
            # Any productive investigation resets the oscillation counter only
            # when it is a patch attempt; investigation steps still consume the
            # iteration budget, so they cannot loop unbounded either.
            pass

        history.append({tool: obs})

    patch.rationale = " → ".join(t for t in trace.thoughts if t)[:1000]
    patch.evidence = sorted(trace.evidence)
    return patch


def minimax_llm(system: str, user: str) -> LLMResponse:
    """Production LLM: M3 via chat_json. A contract violation (unparseable /
    shapeless) becomes a no-tool action so the loop records it and retries; a
    transport failure (LLMError) propagates to fail the run closed."""
    from learnarken.llm.minimax import LLMContractError, chat_json

    try:
        result = chat_json(system, user, temperature=0.0, max_tokens=1024)
    except LLMContractError as exc:
        # Even a contract failure cost tokens — charge an estimate so a model
        # stuck emitting garbage still exhausts the token budget (red-team #13).
        return LLMResponse(action={"thought": f"contract error: {exc}", "tool": ""}, tokens=256)
    tokens = int(result.usage.get("total_tokens", 0))
    if tokens <= 0:  # some proxies report no usage — estimate ~4 chars/token
        tokens = (len(system) + len(user) + len(result.raw_content)) // 4
    return LLMResponse(action=result.parsed, tokens=tokens)
