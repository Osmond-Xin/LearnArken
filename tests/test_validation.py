"""Day 2 golden tests: four-layer validator against the sample packages and
per-rule fixture pairs (INV-3: every rule has >= 1 passing + 1 violating case).

Pass side: package-a (and package-c) yield zero findings, which exercises the
passing case of every rule; rules without a package-b carrier get their
violating case from the synthetic fixtures below.
"""

from pathlib import Path

import pytest

from learnarken.models import ContentType
from learnarken.validation import analyze_package, validate_package
from learnarken.validation.engine import _find_cycles

SAMPLES = Path(__file__).parent.parent / "samples"


# --- sample-package golden results -----------------------------------------


class TestPackageA:
    def test_zero_findings(self):
        report = validate_package(SAMPLES / "package-a")
        assert report.findings == []
        assert report.files_checked == 10  # 8 DM + PM + DML


class TestPackageC:
    def test_zero_findings(self):
        report = validate_package(SAMPLES / "package-c")
        assert report.findings == []

    def test_structured_applicability_parses(self):
        _, package = analyze_package(SAMPLES / "package-c")
        by_dmc = package.dm_index()
        battery = by_dmc["DMC-LA100-A-24-50-00-00A-520A-A"]
        (assertion,) = battery.applicability.assertions
        assert assertion.property_ident == "serialNumber"
        assert assertion.property_type == "prodattr"
        assert assertion.values == "0001~0050"
        damper = by_dmc["DMC-LA100-A-32-20-00-00A-040A-D"]
        (assertion,) = damper.applicability.assertions
        assert (assertion.property_ident, assertion.values) == ("variant", "B")


class TestPackageBManifest:
    """Findings must map 1:1 to the violation manifest (samples/package-b/README.md)."""

    EXPECTED = {
        ("BREX-001", "DMC-LA100-A-29-30-00-00A-520A-A_EN-CA.xml"),  # VIO-3
        ("BREX-002", "DMC-LA100-A-2X-10-00-00A-040A-D_EN-CA.xml"),  # VIO-4
        ("XREF-001", "DMC-LA100-A-29-10-00-00A-040A-D_EN-CA.xml"),  # VIO-1
        ("XREF-002", "DMC-LA100-A-32-10-00-00A-941A-D_EN-CA.xml"),  # VIO-2
        ("XREF-003", "DMC-LA100-A-24-10-00-00A-040A-D_EN-CA.xml"),  # VIO-5
        ("XREF-004", "DMC-SS200-A-58-10-00-00A-520A-A_EN-CA.xml"),  # VIO-6
        ("XREF-005", "DMC-LA100-A-24-30-00-00A-040A-D_EN-CA.xml"),  # VIO-7
    }

    @pytest.fixture
    def report(self):
        return validate_package(SAMPLES / "package-b")

    def test_findings_map_one_to_one_to_manifest(self, report):
        assert {(f.rule_id, f.file) for f in report.findings} == self.EXPECTED
        assert len(report.findings) == len(self.EXPECTED)  # no double-counting

    def test_severities(self, report):
        assert report.error_count == 6
        assert report.warning_count == 1  # VIO-7 cycle is warning severity (Q2)

    def test_clean_control_module_yields_nothing(self, report):
        assert report.findings_for("DMC-LA100-A-24-00-00-00A-040A-D_EN-CA.xml") == []

    def test_findings_carry_location_and_fix_hint(self, report):
        vio1 = next(f for f in report.findings if f.rule_id == "XREF-001")
        assert vio1.line is not None
        assert "29-20" in vio1.message
        assert all(f.fix_hint for f in report.findings)

    def test_cycle_message_names_the_component_members(self, report):
        # Members, not a reconstructed chain — a sorted join can fabricate
        # edges (red-team adjudication 2026-07-14, #7).
        vio7 = next(f for f in report.findings if f.rule_id == "XREF-005")
        assert "component" in vio7.message
        assert "DMC-LA100-A-24-30-00-00A-040A-D" in vio7.message
        assert "DMC-LA100-A-24-40-00-00A-040A-D" in vio7.message
        assert "->" not in vio7.message


# --- per-rule fixture pairs (violating side for rules with no VIO carrier) --

DM_FILE = "DMC-LA100-A-00-00-00-00A-040A-D_EN-CA.xml"

APPLIC = "<applic><displayText><simplePara>LA100, all</simplePara></displayText></applic>"
EXT_OK = (
    "<learnarkenExtension><effectiveDate>2026-01-01</effectiveDate>"
    "<expiryDate>2027-01-01</expiryDate></learnarkenExtension>"
)
DESCRIPTION = (
    "<description><levelledPara><title>General</title>"
    "<para>Plain harmless text.</para></levelledPara></description>"
)


def make_dm(applic: str = APPLIC, extension: str = EXT_OK, content: str = DESCRIPTION) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<dmodule>
  <identAndStatusSection>
    <dmAddress>
      <dmIdent>
        <dmCode modelIdentCode="LA100" systemDiffCode="A" systemCode="00"
                subSystemCode="0" subSubSystemCode="0" assyCode="00"
                disassyCode="00" disassyCodeVariant="A"
                infoCode="040" infoCodeVariant="A" itemLocationCode="D"/>
        <language languageIsoCode="en" countryIsoCode="CA"/>
        <issueInfo issueNumber="001" inWork="00"/>
      </dmIdent>
      <dmAddressItems>
        <issueDate year="2026" month="06" day="01"/>
        <dmTitle><techName>Fixture</techName><infoName>Description</infoName></dmTitle>
      </dmAddressItems>
    </dmAddress>
    <dmStatus issueType="new">
      <security securityClassification="01"/>
      {applic}
      {extension}
    </dmStatus>
  </identAndStatusSection>
  <content>{content}</content>
</dmodule>
"""


def run_on(tmp_path, xml: str, filename: str = DM_FILE):
    (tmp_path / filename).write_text(xml)
    return validate_package(tmp_path)


class TestFixtureRulePairs:
    def test_template_itself_is_clean(self, tmp_path):
        """Passing case shared by every fixture below."""
        assert run_on(tmp_path, make_dm()).findings == []

    def test_parse_001_malformed_xml(self, tmp_path):
        report = run_on(tmp_path, "<dmodule><unclosed>")
        (finding,) = report.findings  # fail-closed: nothing above L0 ran
        assert (finding.rule_id, finding.layer, finding.severity) == (
            "PARSE-001",
            "L0",
            "error",
        )

    def test_schema_001_structural_violation_and_fail_closed_l2(self, tmp_path):
        # dmStatus removed entirely: schema error; BREX must NOT run (fail-closed),
        # so the missing applic does not additionally raise BREX-004.
        xml = (
            make_dm()
            .replace('<dmStatus issueType="new">', "<dmStatusX>")
            .replace("</dmStatus>", "</dmStatusX>")
        )
        report = run_on(tmp_path, xml)
        assert report.findings, "schema violation must be reported"
        assert {f.rule_id for f in report.findings} == {"SCHEMA-001"}
        assert all(f.layer == "L1" for f in report.findings)

    def test_brex_003_procedure_without_steps(self, tmp_path):
        proc = "<procedure><mainProcedure></mainProcedure></procedure>"
        report = run_on(tmp_path, make_dm(content=proc))
        (finding,) = report.findings
        assert (finding.rule_id, finding.severity) == ("BREX-003", "error")

    def test_brex_004_missing_applic_is_warning(self, tmp_path):
        report = run_on(tmp_path, make_dm(applic=""))
        (finding,) = report.findings
        assert (finding.rule_id, finding.severity) == ("BREX-004", "warning")

    def test_brex_005_inverted_extension_dates(self, tmp_path):
        bad_ext = (
            "<learnarkenExtension><effectiveDate>2028-01-01</effectiveDate>"
            "<expiryDate>2026-01-01</expiryDate></learnarkenExtension>"
        )
        report = run_on(tmp_path, make_dm(extension=bad_ext))
        (finding,) = report.findings
        assert (finding.rule_id, finding.severity) == ("BREX-005", "warning")


# --- cycle detection unit tests ---------------------------------------------


class TestFindCycles:
    def test_acyclic_graph(self):
        assert _find_cycles({"a": ["b"], "b": ["c"], "c": []}) == []

    def test_two_cycle(self):
        assert _find_cycles({"a": ["b"], "b": ["a"], "c": ["a"]}) == [["a", "b"]]

    def test_self_loop(self):
        assert _find_cycles({"a": ["a"], "b": []}) == [["a"]]

    def test_three_cycle_reported_once(self):
        graph = {"a": ["b"], "b": ["c"], "c": ["a"], "d": ["b"]}
        assert _find_cycles(graph) == [["a", "b", "c"]]


# --- model/loader details ----------------------------------------------------


class TestCanonicalModel:
    def test_content_stats_and_types(self):
        _, package = analyze_package(SAMPLES / "package-a")
        by_dmc = package.dm_index()
        pump = by_dmc["DMC-LA100-A-29-10-00-00A-520A-A"]
        assert pump.content_type == ContentType.PROCEDURAL
        assert (pump.steps, pump.warnings) == (3, 2)
        ipd = by_dmc["DMC-LA100-A-29-10-00-00A-941A-D"]
        assert ipd.content_type == ContentType.IPD
        assert [icn.ident for icn in ipd.icn_refs] == ["ICN-LA100-29-001-01"]

    def test_extension_dates_and_issue_date(self):
        _, package = analyze_package(SAMPLES / "package-a")
        pump = package.dm_index()["DMC-LA100-A-29-10-00-00A-520A-A"]
        assert str(pump.issue_date) == "2026-03-15"
        assert str(pump.extension.effective_date) == "2026-04-01"
        assert str(pump.extension.expiry_date) == "2028-04-01"

    def test_dml_entries_registered(self):
        _, package = analyze_package(SAMPLES / "package-b")
        (dml,) = package.dmls
        assert len(dml.entries) == 9  # registers all nine DMs, incl. VIO-7 pair
