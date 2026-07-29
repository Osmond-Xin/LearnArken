"""Regressions for the first real execution of the Day 10 deployment.

Every test here corresponds to a finding in docs/reviews/deploy-2026-07-29.md —
defects that unit tests could not have caught before, because the deployment had
never been run on a machine other than the author's laptop.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VM_DIR = REPO_ROOT / "deploy" / "vm"


def _load_watchdog():
    import importlib.util

    spec = importlib.util.spec_from_file_location("idle_watchdog", VM_DIR / "idle_watchdog.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_shim():
    import importlib.util

    spec = importlib.util.spec_from_file_location("status_shim", VM_DIR / "status_shim.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDeviceIsResolvedNotHardcoded:
    """R-02: `device: "mps"` made the whole stack unrunnable off one laptop."""

    def test_env_override_wins(self, monkeypatch):
        from learnarken.embedding import providers

        providers.resolve_device.cache_clear()
        monkeypatch.setenv("LEARNARKEN_DEVICE", "cpu")
        assert providers.resolve_device() == "cpu"
        providers.resolve_device.cache_clear()

    def test_cpu_host_gets_a_dtype_it_can_actually_run(self, monkeypatch):
        """fp16 on CPU is not usably implemented in PyTorch; a CPU host must
        get fp32 or the model loads and then fails at inference."""
        from learnarken.embedding import providers

        providers.resolve_device.cache_clear()
        monkeypatch.setenv("LEARNARKEN_DEVICE", "cpu")
        config = providers._local_config("qwen3-8b")
        assert config["model_kwargs"]["device"] == "cpu"
        assert config["model_kwargs"]["model_kwargs"]["torch_dtype"] == "float32"
        providers.resolve_device.cache_clear()

    def test_no_module_hardcodes_mps(self):
        for path in ("src/learnarken/embedding/providers.py", "src/learnarken/retrieval/hybrid.py"):
            source = (REPO_ROOT / path).read_text(encoding="utf-8")
            assert '"device": "mps"' not in source, f"{path} pins the device again"


class TestWatchdogBootWindow:
    """R-01/R-06: the fence must not power off the boot it exists to protect,
    and must never let the boot window hold the machine past the hard cap."""

    def test_provisioning_sentinel_suppresses_the_unreachable_strike(self, tmp_path, monkeypatch):
        watchdog = _load_watchdog()
        sentinel = tmp_path / "provisioning"
        sentinel.touch()
        monkeypatch.setattr(watchdog, "PROVISIONING_SENTINEL", sentinel)
        monkeypatch.setattr(watchdog, "vm_uptime_seconds", lambda: 10_000.0)
        assert watchdog._boot_window() is True

    def test_boot_grace_expires(self, tmp_path, monkeypatch):
        watchdog = _load_watchdog()
        monkeypatch.setattr(watchdog, "PROVISIONING_SENTINEL", tmp_path / "absent")
        monkeypatch.setattr(watchdog, "vm_uptime_seconds", lambda: watchdog.BOOT_GRACE_S + 1)
        assert watchdog._boot_window() is False

    def test_hard_cap_still_wins_inside_the_boot_window(self, tmp_path, monkeypatch):
        """The sentinel suppresses only the unreachable strike. A provisioning
        run that hangs must still hit the uptime cap, or R-01 (an unfenced,
        billing VM) comes straight back."""
        watchdog = _load_watchdog()
        sentinel = tmp_path / "provisioning"
        sentinel.touch()
        monkeypatch.setattr(watchdog, "PROVISIONING_SENTINEL", sentinel)
        monkeypatch.setattr(watchdog, "vm_uptime_seconds", lambda: watchdog.HARD_CAP_S + 1)
        shutdowns = []
        monkeypatch.setattr(watchdog, "_shutdown", lambda reason: shutdowns.append(reason))
        assert watchdog.main() == 0
        assert shutdowns == [watchdog.SHUTDOWN_CAP]

    def test_boot_grace_is_not_shorter_than_the_strike_window(self):
        """A grace shorter than FAIL_LIMIT minutes would leave the original
        race intact."""
        watchdog = _load_watchdog()
        assert watchdog.BOOT_GRACE_S >= watchdog.FAIL_LIMIT * 60


class TestShimDoesNotLeakUsageTiming:
    """R-18: the public shim forwarded the backend payload verbatim."""

    def test_activity_timestamps_are_dropped(self):
        shim = _load_shim()
        view = shim._public_view(
            {
                "status": "ready",
                "services": {"vespa": True},
                "idle_seconds": 12.0,
                "started_at": 1.0,
                "last_business_activity": 2.0,
            }
        )
        assert view == {"status": "ready", "services": {"vespa": True}, "idle_seconds": 12.0}

    def test_non_dict_payload_fails_closed(self):
        shim = _load_shim()
        assert shim._public_view(["not", "a", "dict"]) == {"status": "unreachable"}


class TestSecondLookIsInsideTheSpendFence:
    """R-05: up to 5 billed VLM calls were made with the quota recording one."""

    def test_denied_budget_refuses_before_any_call(self):
        from learnarken.multimodal.second_look import FigureRefusal, consensus_read

        calls = []

        def describe(*args, **kwargs):
            calls.append(1)
            raise AssertionError("must not be reached once the fence says no")

        with pytest.raises(FigureRefusal, match="spend fence"):
            consensus_read(b"png", {"01"}, [], "q", describe=describe, budget=lambda: False)
        assert calls == []

    def test_budget_is_consulted_once_per_sample(self):
        from learnarken.multimodal.second_look import FigureRefusal, consensus_read
        from learnarken.multimodal.vlm import VLMUnavailable

        asked = []

        def budget() -> bool:
            asked.append(1)
            return len(asked) <= 2  # fence allows two samples, then denies

        def describe(*args, **kwargs):
            raise VLMUnavailable("flaky")  # consumes an attempt, casts no vote

        with pytest.raises(FigureRefusal):
            consensus_read(b"png", {"01"}, [], "q", describe=describe, budget=budget)
        assert len(asked) == 3  # two allowed samples, the third denied


class TestPublicBindRefusesWhenTheGateIsOff:
    """R-07: the script bound 0.0.0.0 while DemoGuard fails *open* outside
    public mode, so a missing demo.env served an ungated app to the internet."""

    def _run(self, env: dict[str, str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(VM_DIR / "run_demo_vm.sh")],
            capture_output=True,
            text=True,
            timeout=60,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin", **env},
        )

    @pytest.mark.skipif(sys.platform == "win32", reason="bash script")
    def test_refuses_without_public_mode(self):
        result = self._run({})
        assert result.returncode == 1
        assert "DEMO_PUBLIC is not 1" in result.stderr

    @pytest.mark.skipif(sys.platform == "win32", reason="bash script")
    def test_refuses_on_the_placeholder_key(self):
        result = self._run(
            {
                "DEMO_PUBLIC": "1",
                "DEMO_GATE_KEY": "CHANGE-ME-must-match-the-Cloud-Function-link-key",
            }
        )
        assert result.returncode == 1
        assert "DEMO_GATE_KEY" in result.stderr

    @pytest.mark.skipif(sys.platform == "win32", reason="bash script")
    def test_refuses_on_a_short_key(self):
        result = self._run({"DEMO_PUBLIC": "1", "DEMO_GATE_KEY": "tooshort"})
        assert result.returncode == 1
        assert "16 chars" in result.stderr


class TestTriggerRateLimitSurvivesColdStarts:
    """R-15: the only rate limit lived in one function instance's memory."""

    def _logic(self):
        sys.path.insert(0, str(REPO_ROOT / "deploy" / "trigger"))
        import logic

        return logic

    def test_a_vm_that_never_started_is_not_limited(self):
        assert self._logic().start_floor_seconds_left(None, 1000.0) == 0.0

    def test_a_very_recent_start_is_limited(self):
        logic = self._logic()
        assert logic.start_floor_seconds_left(1000.0, 1060.0) == 240.0

    def test_the_floor_does_not_lock_out_a_later_legitimate_visitor(self):
        """The floor must stay well under the idle-shutdown window, or one
        visitor's session would deny the next recipient for the rest of the
        hour — the fix would have created a worse defect than the finding."""
        logic = self._logic()
        assert logic.MIN_GLOBAL_START_INTERVAL_S < logic.MIN_START_INTERVAL_S
        assert logic.start_floor_seconds_left(1000.0, 1000.0 + 35 * 60) == 0.0


class TestReadyEmailDoesNotCarryTheGateKey:
    """R-12: the ready notification mailed a URL with DEMO_GATE_KEY in it."""

    def test_no_demo_url_in_the_ready_notification(self):
        source = (REPO_ROOT / "deploy" / "trigger" / "main.py").read_text(encoding="utf-8")
        ready_block = source[source.index("demo] ready") : source.index("return _json")]
        assert "demo_url" not in ready_block


class TestClickRecordSurvivesWithoutEmail:
    """Email is optional (no sending mailbox — applications go out via LinkedIn
    and web forms), so the function log has to carry the interest signal."""

    def _main_source(self) -> str:
        return (REPO_ROOT / "deploy" / "trigger" / "main.py").read_text(encoding="utf-8")

    def test_unconfigured_smtp_is_a_clean_no_op(self):
        """Not an exception swallowed by the handler — that is indistinguishable
        from a real delivery failure in the logs."""
        source = self._main_source()
        assert 'if not all(os.environ.get(name) for name in ("SMTP_HOST", "SMTP_USER"' in source

    def test_opening_the_link_logs_which_recipient(self):
        source = self._main_source()
        assert "demo link opened by recipient=%s" in source

    def test_starting_the_vm_logs_which_recipient(self):
        source = self._main_source()
        assert "VM start issued by recipient=%s" in source

    def test_info_logging_is_actually_enabled(self):
        """The click record is logger.info; Python drops INFO by default, so on
        the deployed function it was written and discarded — the one interest
        signal, silently missing (found on the live deployment, 2026-07-29)."""
        source = self._main_source()
        assert "logging.basicConfig(level=logging.INFO)" in source
        assert "logger.setLevel(logging.INFO)" in source

    def test_the_raw_token_is_never_logged(self):
        """The label identifies the company; the token is the credential."""
        source = self._main_source()
        for line in source.splitlines():
            if "logger." in line and "token" in line:
                assert "_tok_tag(token)" in line, line


class TestProvisionArmsTheFenceFirst:
    """R-01: the watchdog used to be installed after the container pulls and
    the multi-GB model download — so a failed provision left a running,
    unfenced, billing VM. This is a text assertion on purpose: the ordering IS
    the fix, and it is the ordering that regressed."""

    def test_watchdog_is_enabled_before_the_index_run(self):
        script = (VM_DIR / "provision.sh").read_text(encoding="utf-8")
        arm = script.index("systemctl enable --now learnarken-watchdog.timer")
        index_run = script.index("learnarken index")
        assert arm < index_run

    def test_a_failed_provision_clears_the_sentinel(self):
        script = (VM_DIR / "provision.sh").read_text(encoding="utf-8")
        assert "trap 'rm -f /run/learnarken-provisioning' EXIT" in script

    def test_existing_but_stopped_containers_are_started(self):
        """R-04 (second half): `docker inspect` succeeds for a *stopped*
        container, so `inspect || run` did nothing at all after a reboot and
        provisioning waited on health that could never arrive."""
        script = (VM_DIR / "provision.sh").read_text(encoding="utf-8")
        assert "docker inspect learnarken-vespa >/dev/null 2>&1 || docker run" not in script
        assert 'docker start "$name"' in script

    def test_container_health_wait_fails_closed_on_timeout(self):
        """R-19: the wait loop used to fall through silently, surfacing a dead
        container four steps later as a confusing `docker exec` error."""
        script = (VM_DIR / "provision.sh").read_text(encoding="utf-8")
        assert "STOP: vespa config server and/or neo4j never became healthy" in script

    def test_vespa_package_deploy_is_unconditional(self):
        """R-04: gating the root deploy on liveness skipped it on every re-run,
        so a changed application package never reached the engine."""
        script = (VM_DIR / "provision.sh").read_text(encoding="utf-8")
        deploy_line = "docker exec learnarken-vespa vespa deploy"
        assert deploy_line in script
        before = script[: script.index(deploy_line)]
        assert "rm -rf /tmp/learnarken-app" in before, "staging dir must be cleared first"
        # docker cp lands root-owned files; docker exec defaults to the image's
        # unprivileged user and cannot remove them (seen for real 2026-07-29).
        assert "docker exec -u root learnarken-vespa rm -rf" in before


class TestProvisionContainerLogicActuallyRuns:
    """Round-2 red team, fairly: the assertions above are text matches on the
    script, which would pass while the shell behaviour was wrong. These run the
    real `start_or_run` against fake `docker` binaries and check what it did."""

    def _harness(self, tmp_path: Path, existing_image: str | None) -> subprocess.CompletedProcess:
        """Extract start_or_run from the real script and drive it with a fake
        docker whose `inspect` reports `existing_image` for the container."""
        script = (VM_DIR / "provision.sh").read_text(encoding="utf-8")
        start = script.index("start_or_run() {")
        end = script.index("\n}\n", start) + 3
        func = script[start:end]

        calls = tmp_path / "calls.log"
        fake = tmp_path / "docker"
        exists = "yes" if existing_image else "no"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$@" >> "{calls}"\n'
            'if [ "$1" = "inspect" ]; then\n'
            f'  [ "{exists}" = "no" ] && exit 1\n'
            '  case "$*" in\n'
            f'    *"{{{{.Image}}}}"*) echo "{existing_image or ""}"; exit 0;;\n'
            '    *"{{.Id}}"*) echo "sha256:WANTED"; exit 0;;\n'
            "  esac\n"
            "  exit 0\n"
            "fi\n"
            "exit 0\n"
        )
        fake.chmod(0o755)
        runner = tmp_path / "run.sh"
        runner.write_text(
            f"set -euo pipefail\nPATH={tmp_path}:$PATH\n{func}\n"
            'start_or_run learnarken-vespa -p 1:1 "some-image@sha256:WANTED"\n'
        )
        result = subprocess.run(["bash", str(runner)], capture_output=True, text=True, timeout=60)
        result.stdout += calls.read_text() if calls.exists() else ""
        return result

    def test_missing_container_is_created(self, tmp_path):
        result = self._harness(tmp_path, existing_image=None)
        assert result.returncode == 0, result.stderr
        assert "run -d --name learnarken-vespa" in result.stdout

    def test_stopped_container_on_the_right_image_is_started_not_recreated(self, tmp_path):
        result = self._harness(tmp_path, existing_image="sha256:WANTED")
        assert result.returncode == 0, result.stderr
        assert "start learnarken-vespa" in result.stdout
        assert "rm -f" not in result.stdout

    def test_container_built_from_a_different_image_is_recreated(self, tmp_path):
        """Digest pinning is worthless if a container from the old mutable tag
        is simply restarted (round-2 red team)."""
        result = self._harness(tmp_path, existing_image="sha256:STALE")
        assert result.returncode == 0, result.stderr
        assert "rm -f learnarken-vespa" in result.stdout
        assert "run -d --name learnarken-vespa" in result.stdout
