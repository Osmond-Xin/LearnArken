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
        assert payload["counts"] == {"error": 7, "warning": 1}
        assert payload["brex_rules_evaluated"] == 5
        assert {f["rule_id"] for f in payload["findings"]} == {
            "BREX-001",
            "BREX-002",
            "XREF-001",
            "XREF-002",
            "XREF-003",
            "XREF-004",
            "XREF-005",
            "XREF-008",
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


class TestQueryOutputContract:
    """The human output separates the model loaders' noise from the answer; the
    machine-readable output stays parseable (red-team 2026-07-27 P3)."""

    def _answer(self, refused: bool):
        from learnarken.answer import AnswerResult
        from learnarken.refusal import RefusalAction

        return AnswerResult(
            question="q",
            answer_text="Release the pressure.",
            refused=refused,
            refusal_gate="llm" if refused else None,
            action=RefusalAction(
                gate="llm", why="w", what_would_resolve="supply a module", owner_reason="none"
            )
            if refused
            else None,
            trace_id="t-1",
            model="MiniMax-M3",
        )

    def _run(self, monkeypatch, argv, refused=False):
        # The CLI imports the engine inside the command, so patch it at source.
        import learnarken.answer as answer

        monkeypatch.setattr(answer, "answer_question", lambda *a, **k: self._answer(refused))
        return main(argv)

    def test_json_output_is_parseable_and_undivided(self, monkeypatch, capsys):
        code = self._run(monkeypatch, ["query", "q", "--json"])
        out = capsys.readouterr().out
        assert code == 0
        assert cli_rule() not in out, "the divider must never enter machine-readable output"
        assert json.loads(out)["trace_id"] == "t-1"

    def test_answered_output_is_divided_once(self, monkeypatch, capsys):
        assert self._run(monkeypatch, ["query", "q"]) == 0
        out = capsys.readouterr().out
        assert out.count(cli_rule()) == 1
        assert out.index(cli_rule()) < out.index("Release the pressure.")

    def test_refusal_output_is_divided_too(self, monkeypatch, capsys):
        assert self._run(monkeypatch, ["query", "q"], refused=True) == 3
        out = capsys.readouterr().out
        assert out.count(cli_rule()) == 1
        assert "what would resolve it" in out


def cli_rule() -> str:
    from learnarken.cli import _RULE

    return _RULE.strip()


class TestQuietModelLoading:
    """Pinned through the real logger, not just the filter object: a test that
    only exercised the filter would still pass if it were never attached, or if
    the whole logger were muted again (red-team 2026-07-27 P2)."""

    NOTICE = (
        "Warning: You are sending unauthenticated requests to the HF Hub. "
        "Please set a HF_TOKEN to enable higher rate limits and faster downloads."
    )
    RETRY = "Retrying in 2s [Retry 1/5]. HTTP 429 Too Many Requests"

    def test_the_notice_is_dropped_and_retries_survive(self, caplog):
        import logging

        from learnarken.cli import _quiet_model_loading

        _quiet_model_loading()
        hub = logging.getLogger("huggingface_hub.utils._http")
        assert hub.level < logging.ERROR or hub.level == logging.NOTSET, (
            "the logger must stay audible; only the one notice is filtered"
        )
        with caplog.at_level(logging.WARNING, logger=hub.name):
            hub.warning(self.NOTICE)
            hub.warning(self.RETRY)
        assert self.NOTICE not in caplog.text
        assert "429" in caplog.text

    def test_attaching_twice_does_not_stack_filters(self):
        import logging

        from learnarken.cli import _DropAnonymousHubWarning, _quiet_model_loading

        _quiet_model_loading()
        _quiet_model_loading()
        hub = logging.getLogger("huggingface_hub.utils._http")
        attached = [f for f in hub.filters if isinstance(f, _DropAnonymousHubWarning)]
        assert len(attached) == 1

    def test_importing_the_cli_does_not_mutate_the_process(self):
        """`import learnarken.cli` must stay side-effect free: the quieting is
        an entrypoint concern, not an import-time one."""
        import importlib
        import logging
        import os

        os.environ.pop("HF_HUB_DISABLE_PROGRESS_BARS", None)
        hub = logging.getLogger("huggingface_hub.utils._http")
        hub.filters = [f for f in hub.filters if type(f).__name__ != "_DropAnonymousHubWarning"]
        importlib.reload(importlib.import_module("learnarken.cli"))
        assert "HF_HUB_DISABLE_PROGRESS_BARS" not in os.environ
        assert not [f for f in hub.filters if type(f).__name__ == "_DropAnonymousHubWarning"]
