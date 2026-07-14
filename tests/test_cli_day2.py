"""Day 2 CLI tests: validate and dm subcommands."""

import json
from pathlib import Path

from learnarken.cli import main

SAMPLES = Path(__file__).parent.parent / "samples"


class TestValidateCli:
    def test_package_a_passes_exit_0(self, capsys):
        assert main(["validate", str(SAMPLES / "package-a")]) == 0
        assert "PASS — no findings" in capsys.readouterr().out

    def test_package_b_json_exit_1(self, capsys):
        assert main(["validate", str(SAMPLES / "package-b"), "--json"]) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["counts"] == {"error": 6, "warning": 1}
        assert payload["brex_rules_evaluated"] == 5
        assert {f["rule_id"] for f in payload["findings"]} == {
            "BREX-001",
            "BREX-002",
            "XREF-001",
            "XREF-002",
            "XREF-003",
            "XREF-004",
            "XREF-005",
        }

    def test_human_output_groups_by_layer(self, capsys):
        main(["validate", str(SAMPLES / "package-b")])
        out = capsys.readouterr().out
        assert "L2 — BREX (single-file):" in out
        assert "L3 — cross-file integrity:" in out
        assert "fix:" in out

    def test_accepted_models_flag_clears_domain_finding(self, capsys):
        main(["validate", str(SAMPLES / "package-b"), "--accepted-models", "LA100,SS200"])
        out = capsys.readouterr().out
        assert "XREF-004" not in out

    def test_not_a_package_exit_2(self, tmp_path, capsys):
        assert main(["validate", str(tmp_path)]) == 2
        assert "no recognizable" in capsys.readouterr().err


class TestDmCli:
    def test_human_output(self, capsys):
        assert main(["dm", str(SAMPLES / "package-a"), "DMC-LA100-A-29-10-00-00A-520A-A"]) == 0
        out = capsys.readouterr().out
        assert "Hydraulic pump — Remove procedures" in out
        assert "Steps: 3" in out
        assert "Referenced by: 3" in out
        assert "BREX rules evaluated: 5" in out

    def test_dmc_prefix_optional(self, capsys):
        assert main(["dm", str(SAMPLES / "package-a"), "LA100-A-29-10-00-00A-520A-A"]) == 0

    def test_json_payload_carries_applicability_assertions(self, capsys):
        assert (
            main(["dm", str(SAMPLES / "package-c"), "LA100-A-24-50-00-00A-520A-A", "--json"]) == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["applicability"]["assertions"] == [
            {"property_ident": "serialNumber", "property_type": "prodattr", "values": "0001~0050"}
        ]
        assert payload["issue_date"] == "2026-06-05"
        assert payload["effective_date"] == "2026-06-15"  # labeled extension
        assert payload["validation"]["findings"] == []

    def test_dm_findings_surface_in_payload(self, capsys):
        assert (
            main(["dm", str(SAMPLES / "package-b"), "LA100-A-29-30-00-00A-520A-A", "--json"]) == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert [f["rule_id"] for f in payload["validation"]["findings"]] == ["BREX-001"]

    def test_unknown_dmc_exit_2_lists_available(self, capsys):
        assert main(["dm", str(SAMPLES / "package-a"), "LA100-A-99-99-99-99Z-999Z-Z"]) == 2
        err = capsys.readouterr().err
        assert "not found" in err
        assert "DMC-LA100-A-29-10-00-00A-520A-A" in err
