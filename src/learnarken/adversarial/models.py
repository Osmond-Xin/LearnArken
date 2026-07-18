"""Day 8 adversarial-evaluation models (docs/specs/day8.md).

The pipeline runs each adversarial case through the Day 5 answer engine, then
scores it two ways:

- **behavior** — deterministic (did the system answer / refuse / clarify as the
  case's `expected_behavior` requires, and did it avoid any `must_not_state`
  value)? No LLM needed.
- **groundedness** — for *answered* rows only, each heterogeneous judge
  (Codex, Gemini — never MiniMax, the generator) scores whether every claim in
  the answer is supported by the cited evidence. The headline uses the
  **intersection** of the judges (SPEC decision C).
"""

from __future__ import annotations

from pydantic import BaseModel


class AdversarialCase(BaseModel):
    id: str
    category: str  # rewrite-invariance | perturbation | no-answer | cross-doc
    question: str
    expected_behavior: str  # answer | refuse | clarify
    attack_note: str
    anchor: dict = {}  # must_cite_dmc / must_state / must_not_state
    ai_drafted: bool = True


class ClaimVerdict(BaseModel):
    claim: str
    supported: bool
    evidence: str = ""


class JudgeVerdict(BaseModel):
    judge: str  # "codex" | "gemini" | ...
    model: str | None = None
    invoked_at: str | None = None
    verdict: str  # "grounded" | "hallucinated" | "na" | "error"
    groundedness: float | None = None  # supported / total claims
    claims: list[ClaimVerdict] = []
    reasoning: str = ""
    raw: str = ""  # exact CLI stdout (frozen artifact, INV-5)

    @property
    def grounded(self) -> bool:
        return self.verdict == "grounded"


class RowResult(BaseModel):
    case_id: str
    category: str
    expected_behavior: str
    refused: bool
    refusal_gate: str | None = None
    answer_text: str
    citations: list[str] = []  # chunk ids
    behavior_pass: bool
    behavior_note: str = ""
    slipped_gate: str | None = None  # for a defect: which gate should have caught it
    judge_verdicts: dict[str, JudgeVerdict] = {}
    grounded_intersection: bool | None = None  # None when there was no answer to judge
    trace_id: str


class AdversarialReport(BaseModel):
    seed: int
    generated_at: str
    generator_model: str | None = None
    judges: list[str] = []
    n: int
    behavior_pass_rate: float
    per_category: dict[str, dict] = {}
    per_judge_groundedness: dict[str, float] = {}
    judge_errors: dict[str, int] = {}  # per-judge count of error/invalid verdicts (fail-closed)
    intersection_groundedness: float | None = None
    inter_judge_disagreements: list[str] = []  # case ids where judges disagree
    kappa: dict[str, dict] = {}  # judge -> {kappa, n} (filled once human labels exist)
    rows: list[RowResult] = []
