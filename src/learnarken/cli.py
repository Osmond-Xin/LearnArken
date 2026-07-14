"""LearnArken command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from learnarken.models import DataModule, PackageModel
from learnarken.package import NotAPackageError, _sanitize, scan_package
from learnarken.validation import ValidationReport, analyze_package
from learnarken.validation.rules import BREX_RULES


def _render_human(summary) -> str:
    counts = summary.counts
    lines = [
        f"Package: {summary.path}",
        f"  Data modules (DM):        {counts['data_modules']}",
        f"  Publication modules (PM): {counts['publication_modules']}",
        f"  Data module lists (DML):  {counts['data_module_lists']}",
    ]
    if summary.data_modules:
        lines.append("")
        header = f"  {'DMC':<42} {'Title':<52} {'Issue':<8} Lang"
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for dm in summary.data_modules:
            title = dm.title if len(dm.title) <= 50 else dm.title[:47] + "..."
            lines.append(f"  {dm.dmc:<42} {title:<52} {dm.issue:<8} {dm.language}")
            if dm.error:
                lines.append(f"    !! {dm.file}: {dm.error}")
    for label, files in (("PM", summary.pm_files), ("DML", summary.dml_files)):
        for name in files:
            lines.append(f"  {label}: {name}")
    return "\n".join(lines)


def _cmd_inspect(args: argparse.Namespace) -> int:
    """Exit codes: 0 = OK; 1 = inspected but some modules failed to parse;
    2 = not a recognizable package."""
    try:
        summary = scan_package(args.package)
    except NotAPackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(_render_human(summary))
    if any(dm.error for dm in summary.data_modules):
        print("warning: some data modules failed to parse (see rows above)", file=sys.stderr)
        return 1
    return 0


def _render_validation_human(report: ValidationReport) -> str:
    lines = [
        f"Package: {report.package}",
        f"  Files checked: {report.files_checked}   "
        f"BREX rules evaluated: {report.brex_rules_evaluated}",
        f"  Findings: {report.error_count} error(s), {report.warning_count} warning(s)",
    ]
    layer_names = {
        "L0": "L0 — XML well-formedness",
        "L1": "L1 — schema (project mini-XSD)",
        "L2": "L2 — BREX (single-file)",
        "L3": "L3 — cross-file integrity",
    }
    for layer, label in layer_names.items():
        layer_findings = [f for f in report.findings if f.layer == layer]
        if not layer_findings:
            continue
        lines.append(f"\n  {label}:")
        for f in layer_findings:
            where = f"{f.file}:{f.line}" if f.line else f.file
            lines.append(f"    [{f.rule_id}/{f.severity}] {_sanitize(where)}")
            lines.append(f"      {_sanitize(f.message)}")
            if f.fix_hint:
                lines.append(f"      fix: {_sanitize(f.fix_hint)}")
    if not report.findings:
        lines.append("  PASS — no findings at any layer")
    return "\n".join(lines)


def _cmd_validate(args: argparse.Namespace) -> int:
    """Exit codes: 0 = no error findings; 1 = error findings; 2 = not a package."""
    accepted = tuple(m.strip() for m in args.accepted_models.split(",") if m.strip())
    try:
        report, _ = analyze_package(args.package, accepted_models=accepted)
    except NotAPackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str))
    else:
        print(_render_validation_human(report))
    return 1 if report.error_count else 0


def _dm_payload(dm: DataModule, package: PackageModel, report: ValidationReport) -> dict:
    inbound = sorted(
        other.dmc
        for other in package.data_modules
        if other.dmc != dm.dmc and any(r.dm_code.as_str() == dm.dmc for r in other.dm_refs)
    )
    dm_findings = report.findings_for(dm.file)
    return {
        "dmc": dm.dmc,
        "file": dm.file,
        "title": dm.title,
        "issue": dm.issue_info.as_str() if dm.issue_info else None,
        "issue_type": dm.issue_type,
        "language": dm.language.as_str() if dm.language else None,
        "issue_date": str(dm.issue_date) if dm.issue_date else None,
        "security_classification": dm.security_classification,
        "qa_verification": dm.qa_verification,
        "applicability": dm.applicability.model_dump() if dm.applicability else None,
        # learnarkenExtension — labeled non-standard project fields
        "effective_date": str(dm.extension.effective_date)
        if dm.extension and dm.extension.effective_date
        else None,
        "expiry_date": str(dm.extension.expiry_date)
        if dm.extension and dm.extension.expiry_date
        else None,
        "content": {
            "type": dm.content_type,
            "steps": dm.steps,
            "warnings": dm.warnings,
            "cautions": dm.cautions,
            "outbound_dm_refs": sorted({r.dm_code.as_str() for r in dm.dm_refs}),
            "icn_refs": [icn.ident for icn in dm.icn_refs],
            "referenced_by": inbound,
        },
        "validation": {
            "brex_rules_evaluated": len(BREX_RULES),
            "findings": [f.model_dump() for f in dm_findings],
        },
    }


def _render_dm_human(payload: dict) -> str:
    c, v = payload["content"], payload["validation"]
    applic = payload["applicability"] or {}
    lines = [
        f"{payload['dmc']}  ({payload['file']})",
        "  Identification:",
        f"    Title:      {payload['title']}",
        f"    Issue:      {payload['issue']} ({payload['issue_type']})   "
        f"Language: {payload['language']}   Issue date: {payload['issue_date']}",
        "  Status:",
        f"    Security:   {payload['security_classification']}   QA: {payload['qa_verification']}",
        f"    Applicability: {applic.get('display_text') or '—'}",
    ]
    for a in applic.get("assertions", []):
        lines.append(f"      assert: {a['property_ident']} ({a['property_type']}) = {a['values']}")
    lines.append(
        f"    Effective:  {payload['effective_date']} -> Expiry: {payload['expiry_date']}"
        "   (learnarkenExtension, non-standard)"
    )
    lines += [
        "  Content:",
        f"    Type: {c['type']}   Steps: {c['steps']}   "
        f"Warnings: {c['warnings']}   Cautions: {c['cautions']}",
        f"    Outbound dmRefs: {len(c['outbound_dm_refs'])}"
        + (" -> " + ", ".join(c["outbound_dm_refs"]) if c["outbound_dm_refs"] else ""),
        f"    ICN refs: {len(c['icn_refs'])}"
        + (" -> " + ", ".join(c["icn_refs"]) if c["icn_refs"] else ""),
        f"    Referenced by: {len(c['referenced_by'])}"
        + (" <- " + ", ".join(c["referenced_by"]) if c["referenced_by"] else ""),
        "  Validation:",
        f"    BREX rules evaluated: {v['brex_rules_evaluated']}   "
        f"Findings for this DM: {len(v['findings'])}",
    ]
    for f in v["findings"]:
        lines.append(f"      [{f['rule_id']}/{f['severity']}] {f['message']}")
    return "\n".join(_sanitize(line) for line in lines)


def _cmd_dm(args: argparse.Namespace) -> int:
    """Exit codes: 0 = found; 2 = not a package / DMC not found."""
    try:
        report, package = analyze_package(args.package)
    except NotAPackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    wanted = args.dmc.upper()
    if not wanted.startswith("DMC-"):
        wanted = "DMC-" + wanted
    dm = next((d for d in package.data_modules if d.dmc.upper() == wanted), None)
    if dm is None:
        print(f"error: {_sanitize(wanted)} not found in {args.package}", file=sys.stderr)
        print(
            "available: " + ", ".join(sorted(d.dmc for d in package.data_modules)),
            file=sys.stderr,
        )
        return 2
    payload = _dm_payload(dm, package, report)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        print(_render_dm_human(payload))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="learnarken")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="summarize an S1000D-like package directory"
    )
    inspect_parser.add_argument("package", help="path to the package directory")
    inspect_parser.add_argument("--json", action="store_true", help="output JSON")
    inspect_parser.set_defaults(func=_cmd_inspect)

    validate_parser = subparsers.add_parser(
        "validate", help="run the four-layer validator on a package directory"
    )
    validate_parser.add_argument("package", help="path to the package directory")
    validate_parser.add_argument("--json", action="store_true", help="output JSON")
    validate_parser.add_argument(
        "--accepted-models",
        default="LA100",
        help="comma-separated modelIdentCode domain allowlist (default: LA100)",
    )
    validate_parser.set_defaults(func=_cmd_validate)

    dm_parser = subparsers.add_parser(
        "dm", help="show one data module: metadata, content stats, validation"
    )
    dm_parser.add_argument("package", help="path to the package directory")
    dm_parser.add_argument("dmc", help="DMC string (DMC- prefix optional)")
    dm_parser.add_argument("--json", action="store_true", help="output JSON")
    dm_parser.set_defaults(func=_cmd_dm)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
