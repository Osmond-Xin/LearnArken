"""Day 10 hermetic tests: the deploy slice's pure logic (idle-watchdog
decision, trigger token/rate-limit/state mapping, status-shim allowlist) and
the API's /demo/status contract — the idle clock advances only on business
calls, never on status polling (SPEC day10 acceptance 2). Live GCP behaviour
is drilled manually via deploy/runbook.md §8."""

import importlib.util
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
from fastapi.testclient import TestClient

import learnarken.api.app as api
from learnarken.api.demo_guard import DemoGuard, DemoQuotaExceeded

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


watchdog = _load("idle_watchdog", "deploy/vm/idle_watchdog.py")
shim = _load("status_shim", "deploy/vm/status_shim.py")
logic = _load("trigger_logic", "deploy/trigger/logic.py")


# ---------------------------------------------------------------- watchdog


class TestWatchdogDecision:
    def test_keep_below_both_fences(self):
        assert watchdog.decide(idle_seconds=0, uptime_seconds=0) == watchdog.KEEP
        assert watchdog.decide(idle_seconds=29 * 60, uptime_seconds=60) == watchdog.KEEP

    def test_idle_fence_fires_at_limit(self):
        assert watchdog.decide(idle_seconds=30 * 60, uptime_seconds=60) == watchdog.SHUTDOWN_IDLE

    def test_hard_cap_fires_even_when_active(self):
        # Fence ②: someone keeping the demo warm cannot hold the VM forever.
        assert watchdog.decide(idle_seconds=0, uptime_seconds=3 * 3600) == watchdog.SHUTDOWN_CAP

    def test_hard_cap_wins_over_idle(self):
        assert (
            watchdog.decide(idle_seconds=31 * 60, uptime_seconds=4 * 3600) == watchdog.SHUTDOWN_CAP
        )

    def test_finite_rejects_bad_status_fields(self):
        # A reachable-but-malformed /demo/status must be caught, not crash the
        # watchdog into running forever (day10 #3).
        assert watchdog._finite(42) == 42.0
        assert watchdog._finite(3.5) == 3.5
        for bad in (None, "60", float("inf"), float("nan"), True, {"x": 1}):
            assert watchdog._finite(bad) is None

    def test_vm_uptime_is_a_nonneg_float_or_inf(self):
        # Reads the kernel clock (or +inf on a non-Linux dev box) — either way a
        # number decide() can compare, never the API process's resettable start.
        up = watchdog.vm_uptime_seconds()
        assert isinstance(up, float) and up >= 0


# ---------------------------------------------------------------- demo guard


class TestDemoGuard:
    def _guard(self, monkeypatch, **env):
        for key in (
            "DEMO_PUBLIC",
            "DEMO_GATE_KEY",
            "DEMO_MAX_LLM_CALLS",
            "DEMO_MAX_CONCURRENCY",
            "DEMO_ALLOW_UPLOAD",
        ):
            monkeypatch.delenv(key, raising=False)
        for key, val in env.items():
            monkeypatch.setenv(key, val)
        return DemoGuard()

    def test_key_open_when_not_public(self, monkeypatch):
        g = self._guard(monkeypatch)
        assert g.key_ok(None) and g.key_ok("anything")
        assert g.uploads_allowed()

    def test_key_required_and_constant_time_compared_in_public(self, monkeypatch):
        secret = "s3cret-strong-key-0123"
        g = self._guard(monkeypatch, DEMO_PUBLIC="1", DEMO_GATE_KEY=secret)
        assert g.key_ok(secret)
        assert not g.key_ok("wrong")
        assert not g.key_ok(None)
        assert not g.uploads_allowed()

    def test_public_with_no_key_configured_fails_closed(self, monkeypatch):
        g = self._guard(monkeypatch, DEMO_PUBLIC="1")  # no DEMO_GATE_KEY
        assert not g.key_ok("anything")

    def test_placeholder_and_weak_keys_are_rejected(self, monkeypatch):
        # A forgotten provisioning placeholder (or any too-short key) must not
        # become a working default secret (day10 verify new-issue).
        placeholder = "CHANGE-ME-must-match-the-Cloud-Function-link-key"
        g = self._guard(monkeypatch, DEMO_PUBLIC="1", DEMO_GATE_KEY=placeholder)
        assert not g.key_ok(placeholder)
        weak = self._guard(monkeypatch, DEMO_PUBLIC="1", DEMO_GATE_KEY="short")
        assert not weak.key_ok("short")
        strong = self._guard(monkeypatch, DEMO_PUBLIC="1", DEMO_GATE_KEY="x" * 16)
        assert strong.key_ok("x" * 16)

    def test_llm_slot_is_noop_off_public(self, monkeypatch):
        g = self._guard(monkeypatch)
        for _ in range(5):
            with g.llm_slot():
                pass  # never raises, never counts

    def test_daily_call_quota_fails_closed(self, monkeypatch):
        g = self._guard(monkeypatch, DEMO_PUBLIC="1", DEMO_GATE_KEY="k", DEMO_MAX_LLM_CALLS="2")
        with g.llm_slot():
            pass
        with g.llm_slot():
            pass
        with pytest.raises(DemoQuotaExceeded), g.llm_slot():
            pass

    def test_concurrency_cap_fails_closed(self, monkeypatch):
        g = self._guard(
            monkeypatch,
            DEMO_PUBLIC="1",
            DEMO_GATE_KEY="k",
            DEMO_MAX_LLM_CALLS="100",
            DEMO_MAX_CONCURRENCY="1",
        )
        with g.llm_slot():  # noqa: SIM117 — outer slot held while inner is rejected
            with pytest.raises(DemoQuotaExceeded), g.llm_slot():
                pass
        # slot released on exit → next acquire succeeds
        with g.llm_slot():
            pass


# ---------------------------------------------------------------- trigger logic


class TestTriggerLogic:
    TOKENS = {"tok-alpha": "company-a", "tok-beta": "company-b"}

    def test_valid_token_resolves_recipient(self):
        assert logic.resolve_token("tok-alpha", self.TOKENS) == "company-a"

    def test_unknown_and_empty_tokens_refused(self):
        assert logic.resolve_token("tok-wrong", self.TOKENS) is None
        assert logic.resolve_token("", self.TOKENS) is None
        assert logic.resolve_token("tok-alpha", {}) is None

    def test_rate_limit_only_after_a_recorded_start(self):
        history: dict[str, float] = {}
        # A read-only check never burns the hour: a start that errors out and is
        # never recorded leaves the token free to retry immediately (day10 #9).
        assert not logic.is_rate_limited(history, "tok-alpha", now=1000.0)
        assert not logic.is_rate_limited(history, "tok-alpha", now=1000.5)
        logic.record_start(history, "tok-alpha", now=1000.0)
        assert logic.is_rate_limited(history, "tok-alpha", now=1000.0 + 3599)
        assert not logic.is_rate_limited(history, "tok-alpha", now=1000.0 + 3601)

    def test_rate_limit_is_per_token(self):
        history: dict[str, float] = {}
        logic.record_start(history, "tok-alpha", now=1000.0)
        assert logic.is_rate_limited(history, "tok-alpha", now=1000.0)
        assert not logic.is_rate_limited(history, "tok-beta", now=1000.0)

    @pytest.mark.parametrize(
        ("instance_status", "app_ready", "expected"),
        [
            ("RUNNING", True, "running"),
            ("RUNNING", False, "starting"),  # booted but self-check not green yet
            ("PROVISIONING", False, "starting"),
            ("STAGING", False, "starting"),
            ("STOPPING", False, "closing"),
            ("TERMINATED", False, "closed"),
            (None, False, "closed"),
            ("SOME-FUTURE-STATUS", False, "closed"),  # unknown fails closed
        ],
    )
    def test_page_state_mapping(self, instance_status, app_ready, expected):
        assert logic.page_state(instance_status, app_ready) == expected


# ---------------------------------------------------------------- status shim


@pytest.fixture
def shim_port(monkeypatch):
    # Point the proxy at a dead loopback port: the backend-down path must 502.
    monkeypatch.setattr(shim, "BACKEND_STATUS_URL", "http://127.0.0.1:9/demo/status")
    server = ThreadingHTTPServer(("127.0.0.1", 0), shim.StatusHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()


class TestStatusShim:
    def test_only_the_status_path_is_served(self, shim_port):
        with pytest.raises(HTTPError) as err:
            urlopen(f"http://127.0.0.1:{shim_port}/health")
        assert err.value.code == 404
        with pytest.raises(HTTPError) as err:
            urlopen(f"http://127.0.0.1:{shim_port}/upload")
        assert err.value.code == 404

    def test_dead_backend_fails_closed_502(self, shim_port):
        with pytest.raises(HTTPError) as err:
            urlopen(f"http://127.0.0.1:{shim_port}/demo/status")
        assert err.value.code == 502
        assert err.value.headers["Access-Control-Allow-Origin"] == "*"


# ---------------------------------------------------------------- /demo/status


@pytest.fixture
def client():
    return TestClient(api.app)


class TestDemoStatus:
    def test_contract_and_polling_never_advances_the_clock(self, client, monkeypatch):
        monkeypatch.setattr(api, "_activity", {"ts": None})
        first = client.get("/demo/status").json()
        assert first["last_business_activity"] is None
        assert first["idle_seconds"] >= 0
        assert set(first["services"]) == {"vespa", "neo4j", "llm_config", "threshold_artifact"}
        assert all(isinstance(v, bool) for v in first["services"].values())

        again = client.get("/demo/status").json()
        assert again["last_business_activity"] is None  # polling is not activity

    def test_business_call_touches_the_clock(self, client, monkeypatch):
        monkeypatch.setattr(api, "_activity", {"ts": None})
        # A refused upload still counts as a visitor interacting (the 400 comes
        # after the activity touch — the fence measures humans, not successes).
        response = client.post(
            "/upload", files={"file": ("not-a-module.txt", b"junk", "text/plain")}
        )
        assert response.status_code == 400
        after = client.get("/demo/status").json()
        assert after["last_business_activity"] is not None
        assert after["idle_seconds"] < 60


# ---------------------------------------------------------------- public-mode API gate


def _public_guard():
    import os

    os.environ.update(DEMO_PUBLIC="1", DEMO_GATE_KEY="k")
    try:
        return DemoGuard()
    finally:
        for key in ("DEMO_PUBLIC", "DEMO_GATE_KEY"):
            os.environ.pop(key, None)


class TestPublicModeGate:
    def test_upload_refused_in_public_mode(self, client, monkeypatch):
        monkeypatch.setattr(api, "GUARD", _public_guard())
        r = client.post("/upload", files={"file": ("DMC-x.xml", b"<x/>", "application/xml")})
        assert r.status_code == 403
        assert "disabled" in r.json()["detail"]

    def test_query_without_key_refused_in_public_mode(self, client, monkeypatch):
        monkeypatch.setattr(api, "GUARD", _public_guard())
        r = client.post("/query", json={"question": "what is the pressure procedure?"})
        assert r.status_code == 403

    def test_query_with_wrong_key_refused(self, client, monkeypatch):
        monkeypatch.setattr(api, "GUARD", _public_guard())
        r = client.post(
            "/query",
            json={"question": "what is the pressure procedure?"},
            headers={"X-Demo-Key": "wrong"},
        )
        assert r.status_code == 403
