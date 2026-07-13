"""Package scanning for S1000D-like sample packages.

Day 1 scope (docs/specs/day1.md): parse only what the inspect table needs —
dmCode, titles, issueInfo, language — directly from XML. The full canonical
Pydantic model arrives on Day 2.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

# Strip ASCII control characters from XML-sourced text before display
# (red-team finding #9: ANSI/control chars in titles could corrupt terminals).
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

# dmCode attributes in S1000D order, joined into the human-readable DMC string.
_DMC_ATTR_GROUPS: tuple[tuple[str, ...], ...] = (
    ("modelIdentCode",),
    ("systemDiffCode",),
    ("systemCode",),
    ("subSystemCode", "subSubSystemCode"),
    ("assyCode",),
    ("disassyCode", "disassyCodeVariant"),
    ("infoCode", "infoCodeVariant"),
    ("itemLocationCode",),
)


@dataclass
class DataModuleInfo:
    file: str
    dmc: str
    title: str
    issue: str
    language: str
    error: str | None = None


@dataclass
class PackageSummary:
    path: str
    data_modules: list[DataModuleInfo] = field(default_factory=list)
    pm_files: list[str] = field(default_factory=list)
    dml_files: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "data_modules": len(self.data_modules),
            "publication_modules": len(self.pm_files),
            "data_module_lists": len(self.dml_files),
        }

    def to_dict(self) -> dict:
        return {
            "package": self.path,
            "counts": self.counts,
            "data_modules": [
                {
                    "file": dm.file,
                    "dmc": dm.dmc,
                    "title": dm.title,
                    "issue": dm.issue,
                    "language": dm.language,
                    **({"error": dm.error} if dm.error else {}),
                }
                for dm in self.data_modules
            ],
            "publication_modules": self.pm_files,
            "data_module_lists": self.dml_files,
        }


class NotAPackageError(Exception):
    """Directory does not exist or contains no recognizable S1000D-like files."""


def check_input_security(path: Path) -> None:
    """Placeholder for deliberate-poisoning / malicious-input checks.

    This project assumes inputs are non-malicious: errors are misplaced,
    malformed, or outdated documents, not adversarial poisoning (constitution
    §2, decided in the Day 1 red-team adjudication). Dedicated anti-poisoning
    validation is out of scope for now; this hook marks where it would live.
    Format-level hazards (entity expansion, DTD tricks) are separately
    mitigated by parsing through defusedxml.
    """
    return None


def _sanitize(text: str) -> str:
    return _CONTROL_CHARS.sub("", text)


def _dmc_string(dm_code: ET.Element) -> str:
    parts = ["".join(dm_code.get(attr, "?") for attr in group) for group in _DMC_ATTR_GROUPS]
    return "DMC-" + "-".join(parts)


def _parse_data_module(path: Path) -> DataModuleInfo:
    try:
        root = SafeET.parse(path).getroot()
    except (ET.ParseError, DefusedXmlException, ValueError) as exc:
        return DataModuleInfo(
            file=_sanitize(path.name),
            dmc="?",
            title="?",
            issue="?",
            language="?",
            error=_sanitize(f"XML parse error: {exc}"),
        )

    dm_code = root.find(".//dmIdent/dmCode")
    issue_info = root.find(".//dmIdent/issueInfo")
    language = root.find(".//dmIdent/language")
    tech_name = root.find(".//dmAddressItems/dmTitle/techName")
    info_name = root.find(".//dmAddressItems/dmTitle/infoName")

    title_bits = [el.text.strip() for el in (tech_name, info_name) if el is not None and el.text]
    issue = (
        f"{issue_info.get('issueNumber', '?')}-{issue_info.get('inWork', '?')}"
        if issue_info is not None
        else "?"
    )
    lang = (
        f"{language.get('languageIsoCode', '?').upper()}-{language.get('countryIsoCode', '?')}"
        if language is not None
        else "?"
    )
    return DataModuleInfo(
        file=_sanitize(path.name),
        dmc=_sanitize(_dmc_string(dm_code)) if dm_code is not None else "?",
        title=_sanitize(" — ".join(title_bits)) if title_bits else "?",
        issue=_sanitize(issue),
        language=_sanitize(lang),
    )


def scan_package(package_dir: str | Path) -> PackageSummary:
    """Scan a package directory and summarize its S1000D-like content files."""
    directory = Path(package_dir)
    if not directory.is_dir():
        raise NotAPackageError(f"not a directory: {directory}")

    summary = PackageSummary(path=str(directory))
    for path in sorted(directory.glob("*.xml")):
        check_input_security(path)  # placeholder hook, see its docstring
        name = path.name.upper()
        if name.startswith("DMC-"):
            summary.data_modules.append(_parse_data_module(path))
        elif name.startswith("PMC-"):
            summary.pm_files.append(_sanitize(path.name))
        elif name.startswith("DML-"):
            summary.dml_files.append(_sanitize(path.name))

    if not (summary.data_modules or summary.pm_files or summary.dml_files):
        raise NotAPackageError(
            f"no recognizable S1000D-like files (DMC-/PMC-/DML-*.xml) in: {directory}"
        )
    return summary
