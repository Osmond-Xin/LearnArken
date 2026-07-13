"""LearnArken command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from learnarken.package import NotAPackageError, scan_package


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="learnarken")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="summarize an S1000D-like package directory"
    )
    inspect_parser.add_argument("package", help="path to the package directory")
    inspect_parser.add_argument("--json", action="store_true", help="output JSON")
    inspect_parser.set_defaults(func=_cmd_inspect)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
