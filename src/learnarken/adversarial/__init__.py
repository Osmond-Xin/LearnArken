"""Day 8 adversarial evaluation: attack the RAG, judge groundedness, calibrate.

See docs/specs/day8.md. Heterogeneous judges (Codex + Gemini, never MiniMax),
intersection headline, Cohen's Kappa calibration against human labels.
"""

from learnarken.adversarial.models import (
    AdversarialCase,
    AdversarialReport,
    JudgeVerdict,
    RowResult,
)
from learnarken.adversarial.run import build_report, evaluate, load_cases, write_artifacts

__all__ = [
    "AdversarialCase",
    "AdversarialReport",
    "JudgeVerdict",
    "RowResult",
    "build_report",
    "evaluate",
    "load_cases",
    "write_artifacts",
]
