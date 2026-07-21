"""Four-layer package validator (Day 2, docs/specs/day2.md).

L0 well-formedness -> L1 project mini-XSD -> L2 single-file BREX ->
L3 cross-file integrity. Fail-closed layering (INV-4): a file failing L0 is
excluded from everything above; a file failing L1 skips its own L2 rules but
still enters L3 as a graph node so other files' references to it resolve.
The L3 reference graph is the future knowledge graph's groundwork.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from learnarken import loader
from learnarken.models import DataModule, DataModuleList, PackageModel, PublicationModule
from learnarken.package import NotAPackageError
from learnarken.validation.report import Finding, Layer, Severity, ValidationReport
from learnarken.validation.rules import BREX_RULES

DEFAULT_ACCEPTED_MODELS = ("LA100",)

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "learnarken.xsd"


def _elem_location(elem: etree._Element | None) -> tuple[int | None, str | None]:
    if elem is None:
        return None, None
    return elem.sourceline, elem.getroottree().getpath(elem)


def validate_package(
    package_dir: str | Path,
    accepted_models: tuple[str, ...] = DEFAULT_ACCEPTED_MODELS,
) -> ValidationReport:
    return analyze_package(package_dir, accepted_models)[0]


def list_package_files(directory: Path) -> list[Path]:
    """The recognizable S1000D-like files in a package, in deterministic
    (sorted) order. Shared by the serial and multiprocessing paths so both see
    the same file set and ordering (Day 13, INV-2 shard equivalence)."""
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
    return xml_files


@dataclass
class FileResult:
    """The per-file (L0/L1/L2) outcome — the shardable unit (Day 13). Carries
    only picklable Pydantic models + findings, never a live etree, so it can
    cross a process boundary. Cross-file dedup and L3 are the merge's job (they
    need whole-package state); a worker returns this and the main process folds
    it in (`_merge_file_results`)."""

    file: str
    findings: list[Finding] = field(default_factory=list)
    digest: str | None = None
    model: DataModule | PublicationModule | DataModuleList | None = None


def _process_file(path: Path, schema: etree.XMLSchema) -> FileResult:
    """L0 well-formedness -> L1 schema -> model build -> L2 BREX for one file.
    Pure w.r.t. cross-file state: byte-identical dedup and L3 are applied later
    in `_merge_file_results`. Splitting this out is what lets validation shard
    per-DM-file (Day 13, Decision 1) while the serial path stays byte-identical
    (it calls the exact same function)."""
    findings: list[Finding] = []

    # --- L0: well-formedness ---------------------------------------------
    try:
        size = path.stat().st_size
        if size > loader.MAX_FILE_BYTES:
            # Fail closed instead of exhausting memory (adjudication #4).
            findings.append(
                Finding(
                    rule_id="PARSE-002",
                    layer=Layer.L0_WELLFORMED,
                    severity=Severity.ERROR,
                    file=path.name,
                    message=f"file is {size} bytes, over the "
                    f"{loader.MAX_FILE_BYTES}-byte cap; refused (fail closed)",
                    fix_hint="split the module or raise MAX_FILE_BYTES; "
                    "streaming validation is Roadmap material",
                )
            )
            return FileResult(file=path.name, findings=findings)
        tree, digest = loader.parse_file(path)
    except Exception as exc:  # defusedxml + lxml raise disparate types
        findings.append(
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
        return FileResult(file=path.name, findings=findings)

    # --- L1: structural conformance to the project mini-XSD --------------
    schema_ok = schema.validate(tree)
    if not schema_ok:
        for err in schema.error_log:
            findings.append(
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

    # --- model building (also feeds L3) ----------------------------------
    root = tree.getroot()
    name = path.name.upper()
    model_obj: DataModule | PublicationModule | DataModuleList | None = None
    try:
        if name.startswith("DMC-"):
            model_obj = loader.load_data_module(path, root)
        elif name.startswith("PMC-"):
            model_obj = loader.load_publication_module(path, root)
        elif name.startswith("DML-"):
            model_obj = loader.load_dml(path, root)
    except Exception as exc:  # noqa: BLE001 — any build failure becomes a finding
        # Adjudication #9/#12: when the model cannot be built, report an error
        # and do not force-generate a stand-in node.
        findings.append(
            Finding(
                rule_id="MODEL-001",
                layer=Layer.L1_SCHEMA,
                severity=Severity.ERROR,
                file=path.name,
                message=f"cannot build canonical model: {exc}",
                fix_hint="align the structure with schemas/learnarken.xsd; "
                "references to this file will report XREF-001 until it loads",
            )
        )
        return FileResult(file=path.name, findings=findings, digest=digest)

    # --- L2: single-file BREX (skipped when L1 failed — fail closed) ------
    if schema_ok and isinstance(model_obj, DataModule):
        for rule in BREX_RULES:
            # A rule exception must fail closed (report), never crash validation
            # (INV-4). This also makes `_process_file` total w.r.t. rule errors, so
            # running it on a byte-identical duplicate (whose findings the merge
            # drops) can never crash where the old serial loop skipped the dup —
            # closing the sharded-vs-serial equivalence gap (red-team #4) without
            # pessimizing the common no-duplicate path with a pre-dedup double-parse.
            try:
                violations = list(rule.check(root, model_obj, path))
            except Exception as exc:  # noqa: BLE001 — any rule bug becomes a finding
                findings.append(
                    Finding(
                        rule_id="BREX-999",
                        layer=Layer.L2_BREX,
                        severity=Severity.ERROR,
                        file=path.name,
                        message=f"BREX rule {rule.rule_id} raised: {exc}",
                        fix_hint="rule execution error — the module is treated as "
                        "unvalidated for this rule (fail closed)",
                    )
                )
                continue
            for elem, message in violations:
                line, xpath = _elem_location(elem)
                findings.append(
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

    return FileResult(file=path.name, findings=findings, digest=digest, model=model_obj)


def build_schema() -> etree.XMLSchema:
    """A fresh XMLSchema instance. Per-call because lxml XMLSchema
    validate()/error_log is not thread-safe on a shared object (red-team
    adjudication 2026-07-14, #3); each process/worker builds its own."""
    return etree.XMLSchema(etree.parse(str(_SCHEMA_PATH)))


def _merge_file_results(
    directory: Path,
    files: list[Path],
    results: dict[str, FileResult],
    accepted_models: tuple[str, ...],
) -> tuple[ValidationReport, PackageModel]:
    """Fold per-file results into the report + package and run L3. Byte-identical
    dedup lives here (it is cross-file state): iterating `files` in sorted order,
    the first occurrence of a content digest wins and later copies are dropped —
    identical to the serial loop's `seen_digests` policy, so a sharded run is
    byte-equivalent to the single-process baseline (Day 13, Decision 1b)."""
    report = ValidationReport(
        package=str(directory),
        files_checked=len(files),
        brex_rules_evaluated=len(BREX_RULES),
    )
    package = PackageModel(path=str(directory), icn_idents=loader.icn_idents(directory))
    dm_entries: list[tuple[DataModule, str]] = []  # (model, content digest)
    seen_digests: dict[str, str] = {}  # digest -> first file name

    for path in files:
        res = results[path.name]
        # Byte-identical duplicate input: same content, not re-indexed
        # (adjudication #1: md5-identical means the same document).
        if res.digest is not None and res.digest in seen_digests:
            loader.logger.info(
                "%s is byte-identical to %s; skipped", path.name, seen_digests[res.digest]
            )
            continue
        if res.digest is not None:
            seen_digests[res.digest] = path.name
        report.findings.extend(res.findings)
        model_obj = res.model
        if isinstance(model_obj, DataModule):
            package.data_modules.append(model_obj)
            dm_entries.append((model_obj, res.digest or ""))
        elif isinstance(model_obj, PublicationModule):
            package.publication_modules.append(model_obj)
        elif isinstance(model_obj, DataModuleList):
            package.dmls.append(model_obj)

    # --- L3: cross-file integrity (reference graph) — serial, needs whole
    # package (this is the concrete Amdahl serial fraction, Day 13 A2) --------
    dm_index, dm_files, dup_findings = _resolve_dm_identities(dm_entries)
    report.findings.extend(dup_findings)
    report.findings.extend(_crossfile_findings(package, dm_index, dm_files, accepted_models))
    return report, package


def analyze_package(
    package_dir: str | Path,
    accepted_models: tuple[str, ...] = DEFAULT_ACCEPTED_MODELS,
) -> tuple[ValidationReport, PackageModel]:
    """Validate and also return the loaded canonical model (used by `dm`).

    Single-process baseline. `validation.parallel.analyze_package_sharded`
    reuses `_process_file` + `_merge_file_results` to run per-DM-file work
    across a process pool; both share this merge so results are equivalent.
    """
    directory = Path(package_dir)
    files = list_package_files(directory)
    schema = build_schema()
    results = {p.name: _process_file(p, schema) for p in files}
    return _merge_file_results(directory, files, results, accepted_models)


def _issue_key(dm: DataModule) -> tuple[int, str]:
    raw = dm.issue_info.issue_number if dm.issue_info else ""
    try:
        return (int(raw), dm.issue_info.as_str() if dm.issue_info else "")
    except ValueError:
        return (-1, raw)


def _resolve_dm_identities(
    dm_entries: list[tuple[DataModule, str]],
) -> tuple[dict[str, DataModule], dict[str, str], list[Finding]]:
    """Duplicate-DMC policy (red-team adjudication 2026-07-14, #1/#2).

    Byte-identical copies were already dropped at parse time. For distinct
    contents claiming one DMC: same issue number -> XREF-006 error; a strictly
    newer issue wins the index ("入库") with an XREF-007 warning.
    """
    findings: list[Finding] = []
    by_dmc: dict[str, list[DataModule]] = {}
    for dm, _digest in dm_entries:
        by_dmc.setdefault(dm.dmc, []).append(dm)

    dm_index: dict[str, DataModule] = {}
    for dmc, entries in by_dmc.items():
        if len(entries) > 1:
            entries = sorted(entries, key=_issue_key)
            for earlier, later in zip(entries, entries[1:], strict=False):
                if (earlier.issue_info and later.issue_info) and (
                    earlier.issue_info.as_str() == later.issue_info.as_str()
                ):
                    findings.append(
                        Finding(
                            rule_id="XREF-006",
                            layer=Layer.L3_CROSSFILE,
                            severity=Severity.ERROR,
                            file=later.file,
                            message=f"{dmc} appears in {earlier.file} and "
                            f"{later.file} with different content but the same "
                            f"issue {later.issue_info.as_str()}",
                            fix_hint="re-issue one of the modules or remove the conflict",
                        )
                    )
            newest = entries[-1]
            if _issue_key(newest) > _issue_key(entries[0]):
                copies = ", ".join(
                    f"{e.file} @ {e.issue_info.as_str() if e.issue_info else '?'}" for e in entries
                )
                findings.append(
                    Finding(
                        rule_id="XREF-007",
                        layer=Layer.L3_CROSSFILE,
                        severity=Severity.WARNING,
                        file=newest.file,
                        message=f"{dmc} has superseded duplicates ({copies}); "
                        "the newest issue was indexed",
                        fix_hint="retire superseded issues from the package",
                    )
                )
            dm_index[dmc] = newest
        else:
            dm_index[dmc] = entries[0]
    dm_files = {dmc: dm.file for dmc, dm in dm_index.items()}
    return dm_index, dm_files, findings


def _crossfile_findings(
    package: PackageModel,
    dm_index: dict[str, DataModule],
    dm_files: dict[str, str],
    accepted_models: tuple[str, ...],
) -> list[Finding]:
    findings: list[Finding] = []
    icn_idents = set(package.icn_idents)

    def finding(
        rule_id: str,
        severity: Severity,
        file: str,
        message: str,
        fix_hint: str,
        line: int | None = None,
    ) -> Finding:
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
                        "point the reference at an existing data module or add the missing module",
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

    # XREF-008 — every DML registration must resolve to a data module in the
    # package (VIO-8; red-team adjudication 2026-07-14, finding #1). Attached
    # to the DML file — the carrier of this defect.
    for dml in package.dmls:
        for entry in dml.entries:
            if entry.dm_code.as_str() not in dm_index:
                findings.append(
                    finding(
                        "XREF-008",
                        Severity.ERROR,
                        dml.file,
                        f"DML registers {entry.dm_code.as_str()}, absent from "
                        "the package — dangling registration",
                        "remove the stale entry or add the missing data module",
                        line=entry.line,
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
        dm.dmc: sorted({r.dm_code.as_str() for r in dm.dm_refs if r.dm_code.as_str() in dm_index})
        for dm in package.data_modules
    }
    for cycle in _find_cycles(graph):
        carrier = cycle[0]  # smallest DMC in the component — deterministic carrier
        # Report the strongly connected component's members, not a reconstructed
        # chain — a sorted join can fabricate edges (adjudication #7).
        findings.append(
            finding(
                "XREF-005",
                Severity.WARNING,
                dm_files.get(carrier, carrier),
                f"circular reference component: {{{', '.join(cycle)}}}",
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
