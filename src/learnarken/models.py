"""Canonical Pydantic model for S1000D-like packages (Day 2, docs/specs/day2.md).

Field selection follows Day 1 decisions 3-4: standard S1000D metadata plus the
labeled non-standard extension dates. Applicability carries both the display
text and machine-filterable assertions (Day 2 decision 2) so Day 3 chunks can
inherit them.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ContentType(StrEnum):
    DESCRIPTIVE = "descriptive"
    PROCEDURAL = "procedural"
    FAULT_ISOLATION = "fault_isolation"
    IPD = "ipd"
    UNKNOWN = "unknown"


class DmCode(BaseModel):
    # "model_ident_code" collides with pydantic's protected "model_" namespace.
    model_config = ConfigDict(protected_namespaces=())

    model_ident_code: str
    system_diff_code: str
    system_code: str
    sub_system_code: str
    sub_sub_system_code: str
    assy_code: str
    disassy_code: str
    disassy_code_variant: str
    info_code: str
    info_code_variant: str
    item_location_code: str

    def as_str(self) -> str:
        """Human-readable DMC string, e.g. DMC-LA100-A-29-10-00-00A-520A-A."""
        return "DMC-" + "-".join(
            (
                self.model_ident_code,
                self.system_diff_code,
                self.system_code,
                self.sub_system_code + self.sub_sub_system_code,
                self.assy_code,
                self.disassy_code + self.disassy_code_variant,
                self.info_code + self.info_code_variant,
                self.item_location_code,
            )
        )


class IssueInfo(BaseModel):
    issue_number: str
    in_work: str

    def as_str(self) -> str:
        return f"{self.issue_number}-{self.in_work}"


class Language(BaseModel):
    iso_code: str
    country_code: str

    def as_str(self) -> str:
        return f"{self.iso_code.upper()}-{self.country_code.upper()}"


class ApplicAssertion(BaseModel):
    """One machine-filterable applicability assertion (simplified S1000D assert)."""

    property_ident: str
    property_type: str
    values: str


class Applicability(BaseModel):
    display_text: str = ""
    assertions: list[ApplicAssertion] = []


class ExtensionDates(BaseModel):
    """learnarkenExtension — NOT part of S1000D (Day 1 decision 3, labeled)."""

    effective_date: date | None = None
    expiry_date: date | None = None


class DmRef(BaseModel):
    dm_code: DmCode
    issue_info: IssueInfo | None = None
    line: int | None = None


class IcnRef(BaseModel):
    ident: str
    line: int | None = None


class HotspotDecl(BaseModel):
    """One declared hotspot on a figure — the canonical ground truth the Day 12
    VLM description is mechanically diffed against (docs/specs/day12.md Decision
    3a / default 1(c)). `<hotspot>` is a labeled non-standard extension (INV-1
    synthetic), scoped to the figure's `<graphic infoEntityIdent>`."""

    icn_ident: str
    hotspot_id: str
    part_number: str = ""
    label: str = ""


class DataModule(BaseModel):
    file: str
    dm_code: DmCode
    language: Language | None = None
    issue_info: IssueInfo | None = None
    issue_date: date | None = None
    issue_type: str | None = None
    tech_name: str = ""
    info_name: str = ""
    security_classification: str | None = None
    qa_verification: str | None = None
    applicability: Applicability | None = None
    extension: ExtensionDates | None = None
    content_type: ContentType = ContentType.UNKNOWN
    steps: int = 0
    warnings: int = 0
    cautions: int = 0
    dm_refs: list[DmRef] = []
    icn_refs: list[IcnRef] = []
    hotspots: list[HotspotDecl] = []

    @property
    def dmc(self) -> str:
        return self.dm_code.as_str()

    @property
    def title(self) -> str:
        return " — ".join(part for part in (self.tech_name, self.info_name) if part)


class PublicationModule(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    file: str
    model_ident_code: str = ""
    pm_issuer: str = ""
    pm_number: str = ""
    pm_volume: str = ""
    title: str = ""
    issue_info: IssueInfo | None = None
    issue_date: date | None = None
    dm_refs: list[DmRef] = []


class DmlEntry(BaseModel):
    dm_code: DmCode
    issue_info: IssueInfo | None = None
    line: int | None = None


class DataModuleList(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    file: str
    model_ident_code: str = ""
    sender_ident: str = ""
    dml_type: str = ""
    year_of_data_issue: str = ""
    seq_number: str = ""
    issue_info: IssueInfo | None = None
    issue_date: date | None = None
    entries: list[DmlEntry] = []


class PackageModel(BaseModel):
    path: str
    data_modules: list[DataModule] = []
    publication_modules: list[PublicationModule] = []
    dmls: list[DataModuleList] = []
    icn_idents: list[str] = []

    def dm_index(self) -> dict[str, DataModule]:
        return {dm.dmc: dm for dm in self.data_modules}
