"""Day 1 smoke tests: package scanning and the inspect CLI."""

import json
from pathlib import Path

import pytest

from learnarken.cli import main
from learnarken.package import NotAPackageError, scan_package

SAMPLES = Path(__file__).parent.parent / "samples"
PACKAGE_A = SAMPLES / "package-a"
PACKAGE_B = SAMPLES / "package-b"


class TestPackageA:
    def test_counts(self):
        summary = scan_package(PACKAGE_A)
        assert summary.counts == {
            "data_modules": 8,
            "publication_modules": 1,
            "data_module_lists": 1,
        }

    def test_all_dms_parse_cleanly(self):
        summary = scan_package(PACKAGE_A)
        errors = [dm.file for dm in summary.data_modules if dm.error]
        assert errors == []

    def test_dmc_and_metadata_extraction(self):
        summary = scan_package(PACKAGE_A)
        by_dmc = {dm.dmc: dm for dm in summary.data_modules}
        pump_removal = by_dmc["DMC-LA100-A-29-10-00-00A-520A-A"]
        assert pump_removal.title == "Hydraulic pump — Remove procedures"
        assert pump_removal.issue == "001-00"
        assert pump_removal.language == "EN-CA"

    def test_version_story_dm_at_issue_002(self):
        summary = scan_package(PACKAGE_A)
        by_dmc = {dm.dmc: dm for dm in summary.data_modules}
        assert by_dmc["DMC-LA100-A-00-00-00-00A-040A-D"].issue == "002-00"


class TestPackageB:
    def test_counts(self):
        summary = scan_package(PACKAGE_B)
        assert summary.counts == {
            "data_modules": 7,
            "publication_modules": 1,
            "data_module_lists": 1,
        }

    # The full carrier set from the violation manifest (samples/package-b/README.md).
    # If any carrier file is deleted or renamed, the Day 2 validator exam breaks (INV-3).
    MANIFEST_FILES = {
        "DMC-LA100-A-29-10-00-00A-040A-D_EN-CA.xml",  # VIO-1 broken dmRef
        "DMC-LA100-A-32-10-00-00A-941A-D_EN-CA.xml",  # VIO-2 broken ICN ref
        "DMC-LA100-A-29-30-00-00A-520A-A_EN-CA.xml",  # VIO-3 missing warning
        "DMC-LA100-A-2X-10-00-00A-040A-D_EN-CA.xml",  # VIO-4 malformed DMC
        "DMC-LA100-A-24-10-00-00A-040A-D_EN-CA.xml",  # VIO-5 issue mismatch
        "DMC-SS200-A-58-10-00-00A-520A-A_EN-CA.xml",  # VIO-6 out-of-domain
        "DMC-LA100-A-24-00-00-00A-040A-D_EN-CA.xml",  # clean control module
        "PMC-LA100-LEARN-00002-00_EN-CA.xml",
        "DML-LA100-LEARN-C-2026-00002.xml",
    }

    def test_carrier_file_set_matches_manifest(self):
        actual = {p.name for p in PACKAGE_B.glob("*.xml")}
        assert actual == self.MANIFEST_FILES

    def test_violation_markers_present(self):
        """inspect is not a validator (Day 2), but the injected defects must exist."""
        summary = scan_package(PACKAGE_B)
        dmcs = {dm.dmc for dm in summary.data_modules}
        assert "DMC-SS200-A-58-10-00-00A-520A-A" in dmcs  # VIO-6 out-of-domain
        assert "DMC-LA100-A-2X-10-00-00A-040A-D" in dmcs  # VIO-4 malformed code
        vio5 = next(dm for dm in summary.data_modules if dm.dmc.startswith("DMC-LA100-A-24-1"))
        assert vio5.issue == "003-00"  # VIO-5: DML registers 001
        # VIO-1: the dangling target (29-2x subsystem) must NOT exist as a module
        assert not any(dm.dmc.startswith("DMC-LA100-A-29-2") for dm in summary.data_modules)
        # VIO-2: no icn/ directory in this package at all
        assert not (PACKAGE_B / "icn").exists()
        # VIO-3: the accumulator procedure declares <noSafety/> instead of a warning
        vio3_text = (PACKAGE_B / "DMC-LA100-A-29-30-00-00A-520A-A_EN-CA.xml").read_text()
        assert "<noSafety/>" in vio3_text
        assert "<warning>" not in vio3_text


class TestCli:
    def test_inspect_human_output(self, capsys):
        assert main(["inspect", str(PACKAGE_A)]) == 0
        out = capsys.readouterr().out
        assert "Data modules (DM):        8" in out
        assert "DMC-LA100-A-29-10-00-00A-520A-A" in out

    def test_inspect_json_output(self, capsys):
        assert main(["inspect", str(PACKAGE_B), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["counts"]["data_modules"] == 7
        assert len(payload["data_modules"]) == 7

    def test_not_a_package_exits_2(self, tmp_path, capsys):
        assert main(["inspect", str(tmp_path)]) == 2
        assert "no recognizable" in capsys.readouterr().err

    def test_missing_directory_exits_2(self, tmp_path):
        assert main(["inspect", str(tmp_path / "nope")]) == 2


def test_scan_package_raises_on_empty(tmp_path):
    with pytest.raises(NotAPackageError):
        scan_package(tmp_path)


class TestMaliciousXml:
    """Red-team finding #3: parser must reject XML entity/DTD payloads (defusedxml)."""

    BILLION_LAUGHS = (
        '<?xml version="1.0"?>\n'
        "<!DOCTYPE lolz [\n"
        '  <!ENTITY lol "lol">\n'
        '  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">\n'
        '  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">\n'
        "]>\n"
        "<dmodule><identAndStatusSection>&lol3;</identAndStatusSection></dmodule>\n"
    )

    def test_entity_bomb_rejected_not_expanded(self, tmp_path):
        (tmp_path / "DMC-EVIL-A-00-00-00-00A-040A-D_EN-CA.xml").write_text(self.BILLION_LAUGHS)
        summary = scan_package(tmp_path)
        assert len(summary.data_modules) == 1
        assert summary.data_modules[0].error is not None

    def test_cli_exits_1_on_parse_errors(self, tmp_path, capsys):
        (tmp_path / "DMC-EVIL-A-00-00-00-00A-040A-D_EN-CA.xml").write_text(self.BILLION_LAUGHS)
        assert main(["inspect", str(tmp_path)]) == 1
        assert "failed to parse" in capsys.readouterr().err

    def test_control_chars_stripped_from_output(self, tmp_path, capsys):
        # Raw control chars inside XML text are rejected by XML 1.0 itself, so
        # the realistic injection vector is the *filename*, which gets printed.
        evil_name = "DMC-EVIL\x1b[2J-A-00-00-00-00A-040A-D_EN-CA.xml"
        (tmp_path / evil_name).write_text("not xml at all")
        assert main(["inspect", str(tmp_path)]) == 1  # parse error -> exit 1
        captured = capsys.readouterr()
        assert "\x1b" not in captured.out
        assert "DMC-EVIL[2J" in captured.out
