"""Tests for the Day 2 red-team adjudication fixes (docs/reviews/day2.md,
rulings of 2026-07-14). Each test cites the adjudication item it verifies.
"""

import logging
from pathlib import Path

from learnarken import loader
from learnarken.cli import main
from learnarken.validation import validate_package
from test_validation import DM_FILE, make_dm, run_on

SAMPLES = Path(__file__).parent.parent / "samples"


def _second_issue(xml: str, issue: str = "002") -> str:
    """A distinct-content variant of the fixture DM at a given issue number."""
    return xml.replace('issueNumber="001"', f'issueNumber="{issue}"').replace(
        "<techName>Fixture</techName>", "<techName>Fixture edited</techName>"
    )


class TestDuplicateDmcPolicy:
    """Adjudication #1/#2: md5-identical -> skip; same DMC + same issue ->
    error; same DMC + newer issue -> newest indexed, warning."""

    def test_byte_identical_duplicate_is_skipped_silently(self, tmp_path):
        xml = make_dm()
        (tmp_path / DM_FILE).write_text(xml)
        (tmp_path / DM_FILE.replace(".xml", "-copy.xml")).write_text(xml)
        report = validate_package(tmp_path)
        assert report.findings == []

    def test_same_issue_distinct_content_is_error(self, tmp_path):
        (tmp_path / DM_FILE).write_text(make_dm())
        (tmp_path / DM_FILE.replace(".xml", "-dup.xml")).write_text(
            _second_issue(make_dm(), issue="001")
        )
        report = validate_package(tmp_path)
        (finding,) = report.findings
        assert (finding.rule_id, finding.severity) == ("XREF-006", "error")
        assert "same issue 001-00" in finding.message

    def test_newer_issue_wins_index_with_warning(self, tmp_path):
        (tmp_path / DM_FILE).write_text(make_dm())
        newer_file = DM_FILE.replace(".xml", "-r2.xml")
        (tmp_path / newer_file).write_text(_second_issue(make_dm(), issue="002"))
        report = validate_package(tmp_path)
        (finding,) = report.findings
        assert (finding.rule_id, finding.severity) == ("XREF-007", "warning")
        assert finding.file == newer_file  # attached to the indexed (newest) issue
        assert "the newest issue was indexed" in finding.message


class TestResourceCap:
    """Adjudication #4: oversized files are refused with a finding, fail closed."""

    def test_oversized_file_yields_parse_002(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "MAX_FILE_BYTES", 64)
        report = run_on(tmp_path, make_dm())
        (finding,) = report.findings
        assert (finding.rule_id, finding.layer, finding.severity) == (
            "PARSE-002",
            "L0",
            "error",
        )
        assert "fail closed" in finding.message


class TestModelBuildFailure:
    """Adjudication #9/#12: unloadable file -> MODEL-001 error, no stand-in node,
    whole-package run survives."""

    def test_model_001_reported_alongside_schema_errors(self, tmp_path):
        broken = "<?xml version='1.0'?><dmodule><bogus/></dmodule>"
        (tmp_path / DM_FILE).write_text(broken)
        report = validate_package(tmp_path)
        rule_ids = {f.rule_id for f in report.findings}
        assert "MODEL-001" in rule_ids  # reported, not silently dropped
        assert "SCHEMA-001" in rule_ids
        assert all(f.severity == "error" for f in report.findings)


class TestBrex001PrecedingSemantics:
    """Adjudication #5: only reqSafety or same/earlier-step warnings cover a
    hazard; a warning in a LATER step does not."""

    HAZARD_STEP = "<proceduralStep><para>Discharge the nitrogen precharge.</para></proceduralStep>"
    WARNED_STEP = (
        "<proceduralStep><warning><warningAndCautionPara>Danger."
        "</warningAndCautionPara></warning><para>Continue.</para></proceduralStep>"
    )

    def _proc(self, *steps: str) -> str:
        return "<procedure><mainProcedure>" + "".join(steps) + "</mainProcedure></procedure>"

    def test_later_step_warning_does_not_cover(self, tmp_path):
        report = run_on(tmp_path, make_dm(content=self._proc(self.HAZARD_STEP, self.WARNED_STEP)))
        (finding,) = report.findings
        assert finding.rule_id == "BREX-001"
        assert "no preceding warning" in finding.message

    def test_earlier_step_warning_covers(self, tmp_path):
        report = run_on(tmp_path, make_dm(content=self._proc(self.WARNED_STEP, self.HAZARD_STEP)))
        assert report.findings == []


class TestParserHardening:
    """Adjudication #6/#14: any DTD refused; bytes read once for both parsers."""

    def test_bare_dtd_is_refused(self, tmp_path):
        xml = '<?xml version="1.0"?><!DOCTYPE dmodule SYSTEM "x.dtd">' + make_dm().split("?>", 1)[1]
        report = run_on(tmp_path, xml)
        (finding,) = report.findings
        assert (finding.rule_id, finding.layer) == ("PARSE-001", "L0")


class TestLoudDegradation:
    """Adjudication #8/#11: bad dates and skipped files are logged, never silent."""

    def test_unparseable_extension_date_logs_warning(self, tmp_path, caplog):
        bad_ext = (
            "<learnarkenExtension><effectiveDate>not-a-date</effectiveDate>"
            "<expiryDate>2027-01-01</expiryDate></learnarkenExtension>"
        )
        with caplog.at_level(logging.WARNING, logger="learnarken"):
            report = run_on(tmp_path, make_dm(extension=bad_ext))
        assert report.findings == []  # stays None, no finding (per ruling)
        assert any("not-a-date" in r.message and DM_FILE in r.message for r in caplog.records)

    def test_load_package_logs_skipped_files(self, tmp_path, caplog):
        (tmp_path / DM_FILE).write_text("<dmodule><unclosed>")
        with caplog.at_level(logging.WARNING, logger="learnarken"):
            loader.load_package(tmp_path)
        assert any("skipping unparseable" in r.message for r in caplog.records)


class TestSanitizedHumanOutput:
    """Adjudication #10: every human-output field passes _sanitize."""

    def test_validate_header_sanitizes_package_path(self, tmp_path, capsys):
        evil = tmp_path / "pkg\x1b[2Jevil"
        evil.mkdir()
        (evil / DM_FILE).write_text(make_dm())
        assert main(["validate", str(evil)]) == 0
        assert "\x1b" not in capsys.readouterr().out

    def test_dm_available_list_is_sanitized(self, tmp_path, capsys):
        evil = tmp_path / "pkg\x1b[2Jevil"
        evil.mkdir()
        (evil / DM_FILE).write_text(make_dm())
        assert main(["dm", str(evil), "LA100-A-99-99-99-99Z-999Z-Z"]) == 2
        assert "\x1b" not in capsys.readouterr().err


def test_thread_safety_concurrent_validations():
    """Adjudication #3: per-call schema instances — concurrent validations of
    a bad and a clean package must not interleave (at minimum, never error)."""
    from concurrent.futures import ThreadPoolExecutor

    def counts(pkg):
        r = validate_package(SAMPLES / pkg)
        return (r.error_count, r.warning_count)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(counts, ["package-a", "package-b"] * 8))
    assert results == [(0, 0), (7, 1)] * 8
