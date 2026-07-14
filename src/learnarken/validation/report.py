"""Finding and report models shared by all four validation layers (Day 2)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Layer(StrEnum):
    L0_WELLFORMED = "L0"
    L1_SCHEMA = "L1"
    L2_BREX = "L2"
    L3_CROSSFILE = "L3"


class Finding(BaseModel):
    rule_id: str
    layer: Layer
    severity: Severity
    file: str
    line: int | None = None
    path: str | None = None
    message: str
    fix_hint: str = ""


class ValidationReport(BaseModel):
    package: str
    files_checked: int = 0
    brex_rules_evaluated: int = 0
    findings: list[Finding] = []

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    def findings_for(self, file: str) -> list[Finding]:
        return [f for f in self.findings if f.file == file]

    def to_dict(self) -> dict:
        return {
            "package": self.package,
            "files_checked": self.files_checked,
            "brex_rules_evaluated": self.brex_rules_evaluated,
            "counts": {"error": self.error_count, "warning": self.warning_count},
            "findings": [f.model_dump() for f in self.findings],
        }
