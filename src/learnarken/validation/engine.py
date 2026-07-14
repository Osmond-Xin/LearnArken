"""Four-layer package validator (Day 2, docs/specs/day2.md).

L0 well-formedness -> L1 project mini-XSD -> L2 single-file BREX ->
L3 cross-file integrity. Fail-closed layering (INV-4): a file failing L0 is
excluded from everything above; a file failing L1 skips its own L2 rules but
still enters L3 as a graph node so other files' references to it resolve.
The L3 reference graph is the future knowledge graph's groundwork.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from learnarken import loader
from learnarken.models import DataModule, DataModuleList, PackageModel, PublicationModule
from learnarken.package import NotAPackageError
from learnarken.validation.report import Finding, Layer, Severity, ValidationReport
from learnarken.validation.rules import BREX_RULES

DEFAULT_ACCEPTED_MODELS = ("LA100",)

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "learnarken.xsd"
_schema: etree.XMLSchema | None = None


def _get_schema() -> etree.XMLSchema:
    global _schema
    if _schema is None:
        _schema = etree.XMLSchema(etree.parse(str(_SCHEMA_PATH)))
    return _schema


def _elem_location(elem: etree._Element | None) -> tuple[int | None, str | None]:
    if elem is None:
        return None, None
    return elem.sourceline, elem.getroottree().getpath(elem)


def validate_package(
    package_dir: str | Path,
    accepted_models: tuple[str, ...] = DEFAULT_ACCEPTED_MODELS,
) -> ValidationReport:
    directory = Path(package_dir)
    if not directory.is_dir():
        raise NotAPackageError(f"not a directory: {directory}")
    xml_files = [
        p
        for p in sorted(directory.glob("*.xml"))
        if p.name.upper().startswith(("DMC-", "PMC-", "DML-"))
    ]
    if not xml_files:
        raise NotAPackageError(
            f"no recognizable S1000D-like files (DMC-/PMC-/DML-*.xml) in: {directory}"
        )

    report = ValidationReport(
        package=str(directory),
        files_checked=len(xml_files),
        brex_rules_evaluated=len(BREX_RULES),
    )
    package = PackageModel(path=str(directory), icn_idents=loader.icn_idents(directory))
    dm_files: dict[str, str] = {}  # dmc -> file name, for L3 finding attachment

    for path in xml_files:
        # --- L0: well-formedness -----------------------------------------
        try:
            tree = loader.parse_file(path)
        except Exception as exc:  # defusedxml + lxml raise disparate types
            report.findings.append(
                Finding(
                    rule_id="PARSE-001",
                    layer=Layer.L0_WELLFORMED,
                    severity=Severity.ERROR,
                    file=path.name,
                    line=getattr(exc, "lineno", None),
                    message=f"not well-formed XML: {exc}",
                    fix_hint="repair the XML syntax; nothing above L0 ran for this file",
                )
            )
            continue

        # --- L1: structural conformance to the project mini-XSD ----------
        schema = _get_schema()
        schema_ok = schema.validate(tree)
        if not schema_ok:
            for err in schema.error_log:
                report.findings.append(
                    Finding(
                        rule_id="SCHEMA-001",
                        layer=Layer.L1_SCHEMA,
                        severity=Severity.ERROR,
                        file=path.name,
                        line=err.line,
                        path=err.path or None,
                        message=err.message,
                        fix_hint="align the structure with schemas/learnarken.xsd "
                        "(project S1000D-like subset)",
                    )
                )

        # --- model building (also feeds L3) -------------------------------
        root = tree.getroot()
        name = path.name.upper()
        model_obj: DataModule | PublicationModule | DataModuleList | None = None
        try:
            if name.startswith("DMC-"):
                model_obj = loader.load_data_module(path, root)
                package.data_modules.append(model_obj)
                dm_files[model_obj.dmc] = path.name
            elif name.startswith("PMC-"):
                model_obj = loader.load_publication_module(path, root)
                package.publication_modules.append(model_obj)
            elif name.startswith("DML-"):
                model_obj = loader.load_dml(path, root)
                package.dmls.append(model_obj)
        except ValueError as exc:
            if schema_ok:  # structurally valid yet unloadable would be a bug
                report.findings.append(
                    Finding(
                        rule_id="SCHEMA-001",
                        layer=Layer.L1_SCHEMA,
                        severity=Severity.ERROR,
                        file=path.name,
                        message=f"cannot build canonical model: {exc}",
                        fix_hint="align the structure with schemas/learnarken.xsd",
                    )
                )
            continue

        # --- L2: single-file BREX (skipped when L1 failed — fail closed) --
        if schema_ok and isinstance(model_obj, DataModule):
            for rule in BREX_RULES:
                for elem, message in rule.check(root, model_obj, path):
                    line, xpath = _elem_location(elem)
                    report.findings.append(
                        Finding(
                            rule_id=rule.rule_id,
                            layer=Layer.L2_BREX,
                            severity=rule.severity,
                            file=path.name,
                            line=line,
                            path=xpath,
                            message=message,
                            fix_hint=rule.fix_hint,
                        )
                    )

    # --- L3: cross-file integrity (reference graph) -----------------------
    report.findings.extend(_crossfile_findings(package, dm_files, accepted_models))
    return report


def _crossfile_findings(
    package: PackageModel,
    dm_files: dict[str, str],
    accepted_models: tuple[str, ...],
) -> list[Finding]:
    findings: list[Finding] = []
    dm_index = package.dm_index()
    icn_idents = set(package.icn_idents)

    def finding(rule_id: str, severity: Severity, file: str, message: str, fix_hint: str,
                line: int | None = None) -> Finding:
        return Finding(
            rule_id=rule_id,
            layer=Layer.L3_CROSSFILE,
            severity=severity,
            file=file,
            line=line,
            message=message,
            fix_hint=fix_hint,
        )

    # XREF-001 — every content dmRef (DM and PM) resolves inside the package.
    owners: list[tuple[str, list]] = [(dm.file, dm.dm_refs) for dm in package.data_modules]
    owners += [(pm.file, pm.dm_refs) for pm in package.publication_modules]
    for owner_file, refs in owners:
        for ref in refs:
            target = ref.dm_code.as_str()
            if target not in dm_index:
                findings.append(
                    finding(
                        "XREF-001",
                        Severity.ERROR,
                        owner_file,
                        f"dmRef targets {target}, absent from the package",
                        "point the reference at an existing data module or add "
                        "the missing module",
                        line=ref.line,
                    )
                )

    # XREF-002 — every ICN reference resolves to a file under icn/.
    for dm in package.data_modules:
        for icn in dm.icn_refs:
            if icn.ident not in icn_idents:
                findings.append(
                    finding(
                        "XREF-002",
                        Severity.ERROR,
                        dm.file,
                        f"graphic references {icn.ident}, not found under icn/",
                        "add the illustration file or fix infoEntityIdent",
                        line=icn.line,
                    )
                )

    # XREF-003 — DM issueInfo must match its DML registration (attached to the
    # carrier DM, per the package-b manifest convention).
    for dml in package.dmls:
        for entry in dml.entries:
            dm = dm_index.get(entry.dm_code.as_str())
            if dm is None or dm.issue_info is None or entry.issue_info is None:
                continue
            if dm.issue_info.as_str() != entry.issue_info.as_str():
                findings.append(
                    finding(
                        "XREF-003",
                        Severity.ERROR,
                        dm.file,
                        f"{dm.dmc} claims issue {dm.issue_info.as_str()} but "
                        f"{dml.file} registers it at {entry.issue_info.as_str()}",
                        "re-issue the module or correct the DML registration",
                    )
                )

    # XREF-004 — domain check: DM modelIdentCode must be in the accepted set.
    for dm in package.data_modules:
        if dm.dm_code.model_ident_code not in accepted_models:
            findings.append(
                finding(
                    "XREF-004",
                    Severity.ERROR,
                    dm.file,
                    f"modelIdentCode {dm.dm_code.model_ident_code!r} is outside the "
                    f"accepted set {sorted(accepted_models)} — out-of-domain document",
                    "remove the module from this library or extend --accepted-models",
                )
            )

    # XREF-005 — circular dmRef chains (VIO-7; warning severity, KG hygiene).
    graph = {
        dm.dmc: sorted(
            {r.dm_code.as_str() for r in dm.dm_refs if r.dm_code.as_str() in dm_index}
        )
        for dm in package.data_modules
    }
    for cycle in _find_cycles(graph):
        carrier = cycle[0]  # smallest DMC in the cycle — deterministic carrier
        chain = " -> ".join([*cycle, cycle[0]])
        findings.append(
            finding(
                "XREF-005",
                Severity.WARNING,
                dm_files.get(carrier, carrier),
                f"circular reference chain: {chain}",
                "break the cycle if unintended; cycles complicate knowledge-graph "
                "traversal (S1000D does not forbid them)",
            )
        )
    return findings


def _find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Strongly connected components with >1 node (or a self-loop), each
    returned sorted with the smallest node first. Iterative Tarjan."""
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = 0
    sccs: list[list[str]] = []

    for start in sorted(graph):
        if start in index:
            continue
        work: list[tuple[str, int]] = [(start, 0)]
        while work:
            node, child_i = work[-1]
            if child_i == 0:
                index[node] = lowlink[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            children = graph.get(node, [])
            advanced = False
            for i in range(child_i, len(children)):
                child = children[i]
                if child not in index:
                    work[-1] = (node, i + 1)
                    work.append((child, 0))
                    advanced = True
                    break
                if child in on_stack:
                    lowlink[node] = min(lowlink[node], index[child])
            if advanced:
                continue
            work.pop()
            if lowlink[node] == index[node]:
                scc = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    scc.append(member)
                    if member == node:
                        break
                if len(scc) > 1 or node in graph.get(node, []):
                    sccs.append(sorted(scc))
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
    return sorted(sccs)
