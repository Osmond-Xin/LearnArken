"""Self-healing repair agent (Day 7, docs/specs/day7.md).

An LLM-driven ReAct loop that diagnoses L0–L3 validation findings and proposes
fixes. Two modes:

- **dry-run** (default): work entirely on a sandbox copy, write nothing, emit a
  `RepairReport` — the patch set + rationale + consulted evidence + the
  before/after validator delta.
- **apply** (`--apply`): for apply-eligible patches, prompt the human per patch
  (Ruling 1 / constitution §1.3 — never silent); on approval, commit via an
  atomic staged swap (INV-2 idempotent + rollback). High-risk classes
  (L0 syntax, L1 structural, VIO-6) are dry-run-only and never offered.

Trust basis (research §3.3 / §5.4): a fix is accepted only because the
*deterministic* Day 2 validator re-runs clean — never because the LLM said so.
The verifier is independent of the generator, so no generator–verifier
collusion. Unbounded loops are cut by a configurable iteration/token/no-progress
circuit-breaker (research §5.1); over-repair is blocked by a minimal-diff +
zero-new-findings guard (research §5.2).
"""

from learnarken.repair.config import Budget, RepairConfig, load_repair_config
from learnarken.repair.core import run_repair
from learnarken.repair.models import (
    PatchStatus,
    ProposedPatch,
    RepairMode,
    RepairReport,
    RiskTier,
    risk_tier_for,
)

__all__ = [
    "Budget",
    "PatchStatus",
    "ProposedPatch",
    "RepairConfig",
    "RepairMode",
    "RepairReport",
    "RiskTier",
    "load_repair_config",
    "risk_tier_for",
    "run_repair",
]
