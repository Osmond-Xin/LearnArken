"""ToT vs single-shot repair on package-b (Day 13, Decisions 3–4).

Measures whether Tree-of-Thoughts (3 heterogeneous role candidates + deterministic
validator selection) gives a **quantifiable** improvement over single-shot repair,
reported honestly as **k/n** (not bare percentages) with **two-column token cost**
(prompt vs completion). ToT need not win: if it does not beat the baseline the tool
records the failure reason and the next hypothesis (Decision 4, INV-7).

Definitions (Decision 4):
- attempted `n`       = repair-eligible findings in package-b
- validator-pass k/n  = the *deterministic validator* accepted a fix (never LLM self-judgment)
- human-review k/n    = verified but high-risk (dry-run-only) → needs a human at the apply gate
- no-fix/refused k/n  = no accepted fix (fail closed)
- regression k/n      = a selected fix that introduced a new finding — **0 by construction**
  (`propose_patch` rejects any patch that introduces one; reported with that caveat)

This calls the **live** LLM (subscription-bounded, MiniMax proxy); it is a one-time
eval, not run in CI (mirrors day8/day12 eval tools).

    uv run python tools/day13_tot_eval.py [samples/package-b] [--limit N]

Output is frozen at eval/results/day13-tot.json.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from learnarken.repair.agent import LLMResponse, repair_finding
from learnarken.repair.config import Budget, SandboxPolicy, load_repair_config
from learnarken.repair.models import PatchStatus, RiskTier, risk_tier_for
from learnarken.repair.sandbox import Sandbox
from learnarken.repair.tools import Toolbox
from learnarken.repair.tot import DEFAULT_ROLES, Role, tot_repair
from learnarken.validation import DEFAULT_ACCEPTED_MODELS, analyze_package

_OUT = Path("eval/results/day13-tot.json")


@dataclass
class _Tokens:
    prompt: int = 0
    completion: int = 0
    total: int = 0


@dataclass
class _Accountant:
    """Wraps the live LLM to tally prompt/completion tokens across all calls it
    makes, so the eval can report the two-column cost (Decision 4)."""

    tokens: _Tokens = field(default_factory=_Tokens)

    def llm(self, *, temperature: float, preamble: str = ""):
        from learnarken.llm.minimax import LLMContractError, chat_json

        def _call(system: str, user: str) -> LLMResponse:
            try:
                result = chat_json(
                    f"{preamble}\n\n{system}" if preamble else system,
                    user,
                    temperature=temperature,
                    max_tokens=1024,
                )
            except LLMContractError as exc:
                self.tokens.completion += 64
                self.tokens.total += 64
                return LLMResponse(
                    action={"thought": f"contract error: {exc}", "tool": ""}, tokens=256
                )
            usage = result.usage or {}
            self.tokens.prompt += int(usage.get("prompt_tokens", 0))
            self.tokens.completion += int(usage.get("completion_tokens", 0))
            total = int(usage.get("total_tokens", 0))
            self.tokens.total += total
            return LLMResponse(action=result.parsed, tokens=total or 256)

        return _call


def _baseline(finding, package_dir, budget, policy, accepted_models) -> tuple[bool, _Tokens]:
    acc = _Accountant()
    tier = risk_tier_for(finding.rule_id)
    with Sandbox(package_dir, policy) as sandbox:
        patch = repair_finding(
            finding, Toolbox(sandbox, accepted_models), acc.llm(temperature=0.0), budget, tier
        )
    passed = patch.status == PatchStatus.PATCHED
    return passed, acc.tokens


def _tot(finding, package_dir, roles, budget, policy, accepted_models):
    acc = _Accountant()

    def llm_for(role: Role):
        return acc.llm(temperature=role.temperature, preamble=role.preamble)

    result = tot_repair(
        finding,
        package_dir,
        roles=roles,
        llm_for=llm_for,
        budget=budget,
        sandbox_policy=policy,
        accepted_models=accepted_models,
    )
    return result, acc.tokens


def _kn(count: int, n: int) -> str:
    return f"{count}/{n}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", nargs="?", default="samples/package-b")
    parser.add_argument("--limit", type=int, default=None, help="cap findings (smoke test)")
    parser.add_argument(
        "--repeat",
        type=int,
        default=3,
        help="runs per finding — the LLM is non-deterministic; a single run is noise "
        "(scan B5). k/n is reported over the majority of R runs.",
    )
    args = parser.parse_args()

    config = load_repair_config()
    budget: Budget = config.budget
    policy: SandboxPolicy = config.sandbox
    roles = DEFAULT_ROLES

    report0, _ = analyze_package(args.package, DEFAULT_ACCEPTED_MODELS)
    findings = report0.findings[: args.limit] if args.limit else report0.findings
    n = len(findings)

    per_finding: list[dict] = []
    repeats = max(1, args.repeat)
    # k/n is over the MAJORITY of R runs (a finding "solved" if it passes in > R/2
    # runs) — the robust signal, not a single noisy draw (scan B5).
    base_solved = tot_solved = human_review = refused = regression = 0
    base_tok = _Tokens()
    tot_tok = _Tokens()
    errored = 0
    flipped: list[str] = []
    models = DEFAULT_ACCEPTED_MODELS

    for finding in findings:
        tier = risk_tier_for(finding.rule_id)
        b_passes = t_passes = 0
        selected_roles: list[str] = []
        f_error: str | None = None
        for _ in range(repeats):
            try:
                b_pass, b_tokens = _baseline(finding, args.package, budget, policy, models)
                t_result, t_tokens = _tot(finding, args.package, roles, budget, policy, models)
            except Exception as exc:  # noqa: BLE001 — a live-LLM surprise is recorded,
                f_error = f"{type(exc).__name__}: {exc}"  # not fatal (fail-closed run).
                break
            b_passes += int(b_pass)
            if t_result.selected is not None:
                t_passes += 1
                selected_roles.append(t_result.selected.role)
            for tok, acc in ((base_tok, b_tokens), (tot_tok, t_tokens)):
                tok.prompt += acc.prompt
                tok.completion += acc.completion
                tok.total += acc.total

        if f_error is not None:
            errored += 1
            refused += 1
            per_finding.append({"rule_id": finding.rule_id, "file": finding.file, "error": f_error})
            continue

        b_solved = b_passes * 2 > repeats  # majority of R
        t_solved = t_passes * 2 > repeats
        base_solved += int(b_solved)
        tot_solved += int(t_solved)
        if t_solved and tier == RiskTier.DRY_RUN_ONLY:
            human_review += 1
        if not t_solved:
            refused += 1
        unstable = (0 < b_passes < repeats) or (0 < t_passes < repeats)
        if unstable:
            flipped.append(finding.rule_id)

        per_finding.append(
            {
                "rule_id": finding.rule_id,
                "file": finding.file,
                "risk_tier": str(tier),
                "baseline_pass_rate": f"{b_passes}/{repeats}",
                "tot_pass_rate": f"{t_passes}/{repeats}",
                "tot_selected_roles": selected_roles,
                "unstable_across_runs": unstable,
            }
        )

    improvement = tot_solved - base_solved
    nondeterminism = (
        f"Non-deterministic generator: {len(flipped)} finding(s) flipped across the "
        f"{repeats} runs ({sorted(set(flipped))}) — a single run is noise, so k/n is the "
        "majority of R (scan B5 / honest-nondeterministic-eval)."
        if flipped
        else f"All findings were stable across the {repeats} runs (no flips)."
    )
    if improvement > 0:
        verdict = (
            f"ToT improved majority-solved by {improvement} case(s) "
            f"({_kn(base_solved, n)} → {_kn(tot_solved, n)}) at ~{len(roles)}x completion cost. "
            "Marginal ROI: a funnel (single-shot first, ToT only on failure) captures the gain "
            "without paying Nx on the easy cases (DR A funnel)."
        )
    elif improvement == 0:
        verdict = (
            f"No improvement: ToT and baseline both {_kn(base_solved, n)} majority-solved at "
            f"~{len(roles)}x cost. The bottleneck is edit correctness, not sampling breadth — "
            "the findings single-shot solves are the ones ToT solves, and more candidates do "
            "not make the unsolved ones solvable. Next hypothesis: ToT should help most on "
            "complex-structural cases where a single edit path is easy to get wrong. **This is "
            "the 'when is search not worth it' result — a valid, passing outcome (Decision 4).**"
        )
    else:
        verdict = (
            f"ToT UNDERPERFORMED baseline ({_kn(tot_solved, n)} vs {_kn(base_solved, n)}). "
            "Investigate: role personas may steer off the minimal fix, or the reward-hack veto "
            "may over-fire. Recorded honestly (Decision 4)."
        )

    result = {
        "experiment": "ToT vs single-shot repair on package-b (Day 13, Decisions 3-4)",
        "scale": "toy-scale / directional only — small n, do not extrapolate (INV-7)",
        "attempted_n": n,
        "repeats": repeats,
        "errored_findings": errored,
        "candidates_per_case": len(roles),
        "roles": [r.name for r in roles],
        "k_over_n": {
            "baseline_majority_solved": _kn(base_solved, n),
            "tot_majority_solved": _kn(tot_solved, n),
            "human_review_needed": _kn(human_review, n),
            "no_fix_refused": _kn(refused, n),
            "regression": _kn(regression, n),
        },
        "nondeterminism_note": nondeterminism,
        "regression_note": "0 by construction: propose_patch rejects any patch that "
        "introduces a new finding, so a selected fix never regresses (Decision 4 caveat).",
        "token_cost_two_column": {
            "baseline": vars(base_tok),
            "tot": vars(tot_tok),
            "note": f"summed over {repeats} runs x {n} findings. ToT completion ≈ Nx baseline "
            "(N candidates); prompt is inflated too but is cacheable in principle (shared error "
            "context) — DR A §7.1.",
        },
        "selection": "deterministic sandbox validator, never LLM self-judgment (Decision 3b)",
        "verdict": verdict,
        "per_finding": per_finding,
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {_OUT}")
    print(f"  baseline {_kn(base_solved, n)} vs ToT {_kn(tot_solved, n)} majority-solved "
          f"(R={repeats}, {len(roles)} cand/case)")
    print(f"  {nondeterminism}")
    print(f"  {verdict}")


if __name__ == "__main__":
    main()
