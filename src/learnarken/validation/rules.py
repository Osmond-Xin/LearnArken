"""L2 single-file BREX rules — Schematron-style assertions (Day 2, Q5: a
declarative rule table evaluated over lxml trees; no isoschematron toolchain).

Each rule = (id, severity, description, fix hint, check function). A check
receives the lxml root plus the loaded DataModule and yields (element, message)
violations; the engine turns them into findings with line numbers and paths.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from learnarken.models import DataModule
from learnarken.validation.report import Severity

Violation = tuple[etree._Element | None, str]
CheckFn = Callable[[etree._Element, DataModule, Path], Iterator[Violation]]


@dataclass(frozen=True)
class BrexRule:
    rule_id: str
    severity: Severity
    description: str
    fix_hint: str
    check: CheckFn


# BREX-001 is honestly a toy heuristic (docs/specs/day2.md): real BREX rules
# are business-authored; a hazard-keyword lexicon stands in for one (INV-7).
_HAZARD_KEYWORDS = (
    "pressur",
    "nitrogen",
    "discharge",
    "voltage",
    "high current",
    "flammable",
    "toxic",
)

# Project DMC coding rules (S1000D-like, simplified): numeric SNS codes.
_DMC_PATTERNS = {
    "modelIdentCode": re.compile(r"^[A-Z0-9]{2,14}$"),
    "systemDiffCode": re.compile(r"^[A-Z0-9]{1,4}$"),
    "systemCode": re.compile(r"^\d{2}$"),
    "subSystemCode": re.compile(r"^\d$"),
    "subSubSystemCode": re.compile(r"^\d$"),
    "assyCode": re.compile(r"^\d{2}$"),
    "disassyCode": re.compile(r"^\d{2}$"),
    "disassyCodeVariant": re.compile(r"^[A-Z]$"),
    "infoCode": re.compile(r"^\d{3}$"),
    "infoCodeVariant": re.compile(r"^[A-Z]$"),
    "itemLocationCode": re.compile(r"^[A-Z]$"),
}


def _step_text(step: etree._Element) -> str:
    """Step text excluding its own inline warnings/cautions."""
    return " ".join(" ".join(para.itertext()) for para in step.findall("para")).lower()


def _check_hazard_warning(root: etree._Element, dm: DataModule, path: Path) -> Iterator[Violation]:
    procedure = root.find("content/procedure")
    if procedure is None:
        return
    # Any warning/caution anywhere in the procedure (reqSafety or inline) counts.
    if procedure.find(".//warning") is not None or procedure.find(".//caution") is not None:
        return
    for step in procedure.iter("proceduralStep"):
        text = _step_text(step)
        hits = [kw for kw in _HAZARD_KEYWORDS if kw in text]
        if hits:
            yield (
                step,
                f"step text matches hazard keyword(s) {hits} but the procedure "
                "declares no warning or caution anywhere",
            )


def _check_dmc_format(root: etree._Element, dm: DataModule, path: Path) -> Iterator[Violation]:
    code_el = root.find("identAndStatusSection/dmAddress/dmIdent/dmCode")
    if code_el is None:
        return
    bad = [
        f"{attr}={code_el.get(attr)!r}"
        for attr, pattern in _DMC_PATTERNS.items()
        if not pattern.match(code_el.get(attr) or "")
    ]
    if bad:
        # One aggregated violation per dmCode keeps the manifest mapping 1:1.
        yield code_el, f"malformed DMC field(s): {', '.join(bad)}"
    elif not path.name.startswith(dm.dmc):
        yield code_el, f"file name does not start with its own DMC {dm.dmc}"


def _check_has_steps(root: etree._Element, dm: DataModule, path: Path) -> Iterator[Violation]:
    procedure = root.find("content/procedure")
    if procedure is None:
        return
    main = procedure.find("mainProcedure")
    if main is None or main.find("proceduralStep") is None:
        yield procedure, "procedural data module has no proceduralStep"


def _check_applic_present(root: etree._Element, dm: DataModule, path: Path) -> Iterator[Violation]:
    status = root.find("identAndStatusSection/dmStatus")
    if status is not None and status.find("applic") is None:
        yield status, "dmStatus carries no applic element"


def _check_extension_dates(root: etree._Element, dm: DataModule, path: Path) -> Iterator[Violation]:
    ext = dm.extension
    if ext and ext.effective_date and ext.expiry_date and ext.effective_date >= ext.expiry_date:
        yield (
            root.find("identAndStatusSection/dmStatus/learnarkenExtension"),
            f"effectiveDate {ext.effective_date} is not before expiryDate {ext.expiry_date}",
        )


BREX_RULES: tuple[BrexRule, ...] = (
    BrexRule(
        "BREX-001",
        Severity.ERROR,
        "hazardous procedural step requires a warning/caution",
        "add a warning or caution to reqSafety or to the hazardous step",
        _check_hazard_warning,
    ),
    BrexRule(
        "BREX-002",
        Severity.ERROR,
        "DMC code fields must match the project coding rules",
        "fix the offending dmCode attribute (numeric SNS codes, e.g. systemCode='29')",
        _check_dmc_format,
    ),
    BrexRule(
        "BREX-003",
        Severity.ERROR,
        "a procedural data module must contain at least one step",
        "add proceduralStep elements to mainProcedure",
        _check_has_steps,
    ),
    BrexRule(
        "BREX-004",
        Severity.WARNING,
        "dmStatus should declare applicability",
        "add an applic element with displayText (and assert elements if restricted)",
        _check_applic_present,
    ),
    BrexRule(
        "BREX-005",
        Severity.WARNING,
        "extension effectiveDate must precede expiryDate",
        "correct the learnarkenExtension dates",
        _check_extension_dates,
    ),
)
