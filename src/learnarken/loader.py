"""Build canonical models from S1000D-like XML files (Day 2).

Security posture (Day 1 red-team adjudication): every file passes through
defusedxml first — the L0 well-formedness gate — before lxml re-parses it for
line numbers, XPath, and XSD validation. lxml's parser is additionally
hardened (no entity resolution, no DTD, no network).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from defusedxml import ElementTree as SafeET
from lxml import etree

from learnarken.models import (
    Applicability,
    ApplicAssertion,
    ContentType,
    DataModule,
    DataModuleList,
    DmCode,
    DmlEntry,
    DmRef,
    ExtensionDates,
    IcnRef,
    IssueInfo,
    Language,
    PackageModel,
    PublicationModule,
)

_LXML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)

_DMCODE_ATTRS = {
    "model_ident_code": "modelIdentCode",
    "system_diff_code": "systemDiffCode",
    "system_code": "systemCode",
    "sub_system_code": "subSystemCode",
    "sub_sub_system_code": "subSubSystemCode",
    "assy_code": "assyCode",
    "disassy_code": "disassyCode",
    "disassy_code_variant": "disassyCodeVariant",
    "info_code": "infoCode",
    "info_code_variant": "infoCodeVariant",
    "item_location_code": "itemLocationCode",
}

_CONTENT_TYPES = {
    "description": ContentType.DESCRIPTIVE,
    "procedure": ContentType.PROCEDURAL,
    "faultIsolation": ContentType.FAULT_ISOLATION,
    "illustratedPartsCatalog": ContentType.IPD,
}


def parse_file(path: Path) -> etree._ElementTree:
    """L0 gate (defusedxml) + hardened lxml parse. Raises on malformed/unsafe XML."""
    SafeET.parse(path)  # rejects DTD/entity tricks and malformed XML
    return etree.parse(str(path), _LXML_PARSER)


def _dm_code(elem: etree._Element) -> DmCode:
    return DmCode(**{field: elem.get(attr, "?") for field, attr in _DMCODE_ATTRS.items()})


def _issue_info(elem: etree._Element | None) -> IssueInfo | None:
    if elem is None:
        return None
    return IssueInfo(issue_number=elem.get("issueNumber", "?"), in_work=elem.get("inWork", "?"))


def _issue_date(elem: etree._Element | None) -> date | None:
    if elem is None:
        return None
    try:
        return date(int(elem.get("year")), int(elem.get("month")), int(elem.get("day")))
    except (TypeError, ValueError):
        return None


def _iso_date(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text.strip()) if text else None
    except ValueError:
        return None


def _text(elem: etree._Element | None) -> str:
    """Element text content with XML-indentation whitespace normalized."""
    return " ".join("".join(elem.itertext()).split()) if elem is not None else ""


def _dm_refs(scope: etree._Element) -> list[DmRef]:
    refs = []
    for ref in scope.iter("dmRef"):
        code = ref.find("dmRefIdent/dmCode")
        if code is None:
            continue
        refs.append(
            DmRef(
                dm_code=_dm_code(code),
                issue_info=_issue_info(ref.find("dmRefIdent/issueInfo")),
                line=ref.sourceline,
            )
        )
    return refs


def load_data_module(path: Path, root: etree._Element) -> DataModule:
    ident = root.find("identAndStatusSection/dmAddress/dmIdent")
    items = root.find("identAndStatusSection/dmAddress/dmAddressItems")
    status = root.find("identAndStatusSection/dmStatus")
    content = root.find("content")

    code_el = ident.find("dmCode") if ident is not None else None
    if code_el is None:
        raise ValueError(f"{path.name}: no dmIdent/dmCode")

    lang_el = ident.find("language")
    language = (
        Language(
            iso_code=lang_el.get("languageIsoCode", "?"),
            country_code=lang_el.get("countryIsoCode", "?"),
        )
        if lang_el is not None
        else None
    )

    applicability = None
    extension = None
    security = qa = issue_type = None
    if status is not None:
        issue_type = status.get("issueType")
        sec_el = status.find("security")
        security = sec_el.get("securityClassification") if sec_el is not None else None
        qa_el = status.find("qualityAssurance/firstVerification")
        qa = qa_el.get("verificationType") if qa_el is not None else None
        applic_el = status.find("applic")
        if applic_el is not None:
            applicability = Applicability(
                display_text=_text(applic_el.find("displayText")),
                assertions=[
                    ApplicAssertion(
                        property_ident=a.get("applicPropertyIdent", "?"),
                        property_type=a.get("applicPropertyType", "?"),
                        values=a.get("applicPropertyValues", "?"),
                    )
                    for a in applic_el.findall("assert")
                ],
            )
        ext_el = status.find("learnarkenExtension")
        if ext_el is not None:
            extension = ExtensionDates(
                effective_date=_iso_date(ext_el.findtext("effectiveDate")),
                expiry_date=_iso_date(ext_el.findtext("expiryDate")),
            )

    content_type = ContentType.UNKNOWN
    steps = warnings = cautions = 0
    dm_refs: list[DmRef] = []
    icn_refs: list[IcnRef] = []
    if content is not None:
        for tag, ctype in _CONTENT_TYPES.items():
            if content.find(tag) is not None:
                content_type = ctype
                break
        steps = sum(1 for _ in content.iter("proceduralStep", "isolationStep"))
        warnings = sum(1 for _ in content.iter("warning"))
        cautions = sum(1 for _ in content.iter("caution"))
        dm_refs = _dm_refs(content)
        icn_refs = [
            IcnRef(ident=g.get("infoEntityIdent"), line=g.sourceline)
            for g in content.iter("graphic")
            if g.get("infoEntityIdent")
        ]

    return DataModule(
        file=path.name,
        dm_code=_dm_code(code_el),
        language=language,
        issue_info=_issue_info(ident.find("issueInfo") if ident is not None else None),
        issue_date=_issue_date(items.find("issueDate") if items is not None else None),
        issue_type=issue_type,
        tech_name=_text(items.find("dmTitle/techName") if items is not None else None),
        info_name=_text(items.find("dmTitle/infoName") if items is not None else None),
        security_classification=security,
        qa_verification=qa,
        applicability=applicability,
        extension=extension,
        content_type=content_type,
        steps=steps,
        warnings=warnings,
        cautions=cautions,
        dm_refs=dm_refs,
        icn_refs=icn_refs,
    )


def load_publication_module(path: Path, root: etree._Element) -> PublicationModule:
    ident = root.find("identAndStatusSection/pmAddress/pmIdent")
    items = root.find("identAndStatusSection/pmAddress/pmAddressItems")
    code = ident.find("pmCode") if ident is not None else None
    content = root.find("content")
    return PublicationModule(
        file=path.name,
        model_ident_code=code.get("modelIdentCode", "") if code is not None else "",
        pm_issuer=code.get("pmIssuer", "") if code is not None else "",
        pm_number=code.get("pmNumber", "") if code is not None else "",
        pm_volume=code.get("pmVolume", "") if code is not None else "",
        title=_text(items.find("pmTitle") if items is not None else None),
        issue_info=_issue_info(ident.find("issueInfo") if ident is not None else None),
        issue_date=_issue_date(items.find("issueDate") if items is not None else None),
        dm_refs=_dm_refs(content) if content is not None else [],
    )


def load_dml(path: Path, root: etree._Element) -> DataModuleList:
    ident = root.find("identAndStatusSection/dmlAddress/dmlIdent")
    items = root.find("identAndStatusSection/dmlAddress/dmlAddressItems")
    code = ident.find("dmlCode") if ident is not None else None
    content = root.find("dmlContent")
    entries = (
        [
            DmlEntry(dm_code=ref.dm_code, issue_info=ref.issue_info, line=ref.line)
            for ref in _dm_refs(content)
        ]
        if content is not None
        else []
    )
    return DataModuleList(
        file=path.name,
        model_ident_code=code.get("modelIdentCode", "") if code is not None else "",
        sender_ident=code.get("senderIdent", "") if code is not None else "",
        dml_type=code.get("dmlType", "") if code is not None else "",
        year_of_data_issue=code.get("yearOfDataIssue", "") if code is not None else "",
        seq_number=code.get("seqNumber", "") if code is not None else "",
        issue_info=_issue_info(ident.find("issueInfo") if ident is not None else None),
        issue_date=_issue_date(items.find("issueDate") if items is not None else None),
        entries=entries,
    )


def icn_idents(package_dir: Path) -> list[str]:
    icn_dir = package_dir / "icn"
    if not icn_dir.is_dir():
        return []
    return sorted(p.stem for p in icn_dir.iterdir() if p.is_file() and p.stem.startswith("ICN-"))


def load_package(package_dir: Path) -> PackageModel:
    """Convenience loader for already-valid packages (skips broken files silently).

    The validator does NOT use this: it orchestrates parsing itself so that
    parse failures become L0 findings instead of being skipped.
    """
    package = PackageModel(path=str(package_dir), icn_idents=icn_idents(package_dir))
    for path in sorted(package_dir.glob("*.xml")):
        try:
            root = parse_file(path).getroot()
        except Exception:  # noqa: BLE001 — inspect-grade tolerance, see docstring
            continue
        name = path.name.upper()
        if name.startswith("DMC-"):
            package.data_modules.append(load_data_module(path, root))
        elif name.startswith("PMC-"):
            package.publication_modules.append(load_publication_module(path, root))
        elif name.startswith("DML-"):
            package.dmls.append(load_dml(path, root))
    return package
