"""Repair budgets and sandbox policy — versioned config (Day 7, Decision 4).

Defaults live here; `[tool.learnarken.repair]` in `pyproject.toml` overrides
them (versioned ⇒ reproducible, INV-5); CLI flags override the file. The budget
is the infinite-loop / token circuit-breaker (research §5.1): a run can never
exceed these bounds.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace

from learnarken.config import REPO_ROOT


@dataclass(frozen=True)
class Budget:
    """Per-finding circuit-breaker bounds."""

    max_iterations: int = 12  # hard cap on ReAct steps for one finding
    max_tokens: int = 60_000  # cumulative LLM tokens for one finding
    no_progress_limit: int = 3  # abort if the validator delta doesn't shrink N steps


@dataclass(frozen=True)
class SandboxPolicy:
    """The jail's toy-scale (INV-7) allow-lists and resource caps."""

    timeout_s: float = 10.0
    mem_mb: int = 1024  # RLIMIT_AS cap; generous enough for the interpreter to start
    # No pathlib/sys: they expose file I/O and module internals that the AST
    # attribute denylist cannot fully contain (red-team #1).
    allowed_python_imports: tuple[str, ...] = (
        "lxml",
        "defusedxml",
        "re",
        "json",
        "collections",
        "itertools",
        "math",
    )
    shell_whitelist: tuple[str, ...] = ("xmllint", "cat", "grep", "head", "wc", "ls")


@dataclass(frozen=True)
class RepairConfig:
    budget: Budget = field(default_factory=Budget)
    sandbox: SandboxPolicy = field(default_factory=SandboxPolicy)


def load_repair_config(pyproject: str | None = None) -> RepairConfig:
    """Load `[tool.learnarken.repair]`, falling back to the dataclass defaults."""
    path = pyproject if pyproject is not None else str(REPO_ROOT / "pyproject.toml")
    try:
        with open(path, "rb") as fh:
            table = tomllib.load(fh).get("tool", {}).get("learnarken", {}).get("repair", {})
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return RepairConfig()

    # Clamp to sane maxima so a config typo can't make the loop operationally
    # unbounded (red-team #14).
    budget = Budget(
        max_iterations=min(int(table.get("max_iterations", Budget.max_iterations)), 100),
        max_tokens=min(int(table.get("max_tokens", Budget.max_tokens)), 500_000),
        no_progress_limit=min(int(table.get("no_progress_limit", Budget.no_progress_limit)), 20),
    )
    defaults = SandboxPolicy()
    sandbox = SandboxPolicy(
        timeout_s=min(float(table.get("sandbox_timeout_s", defaults.timeout_s)), 60.0),
        mem_mb=int(table.get("sandbox_mem_mb", defaults.mem_mb)),
        allowed_python_imports=tuple(
            table.get("allowed_python_imports", defaults.allowed_python_imports)
        ),
        shell_whitelist=tuple(table.get("shell_whitelist", defaults.shell_whitelist)),
    )
    return RepairConfig(budget=budget, sandbox=sandbox)


def override_budget(
    budget: Budget, *, max_iterations: int | None = None, max_tokens: int | None = None
) -> Budget:
    """Apply CLI overrides onto a config-loaded budget (only the given fields)."""
    changes = {}
    if max_iterations is not None:
        changes["max_iterations"] = max_iterations
    if max_tokens is not None:
        changes["max_tokens"] = max_tokens
    return replace(budget, **changes) if changes else budget
