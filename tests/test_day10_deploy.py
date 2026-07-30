"""Day 10 hermetic tests: the deploy slice's pure logic (idle-watchdog
decision, trigger token/rate-limit/state mapping, status-shim allowlist) and
the API's /demo/status contract — the idle clock advances only on business
calls, never on status polling (SPEC day10 acceptance 2). Live GCP behaviour
is drilled manually via deploy/runbook.md §8."""

import importlib.util
import re
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

    def test_a_free_lock_is_taken_and_a_live_one_is_not(self):
        """Two requests, one winner. The second sees the label the first wrote
        and plans nothing (Yi Xin's ruling 2026-07-29: add the lock even though
        `instances.start` is idempotent)."""
        labels: dict[str, str] = {"env": "demo"}
        first = logic.plan_start_lock(labels, now=1000.0)
        assert first is not None
        assert first["env"] == "demo"  # existing labels are preserved, not replaced
        assert logic.plan_start_lock(first, now=1000.5) is None

    def test_the_lock_expires_so_a_crashed_request_cannot_wedge_starts(self):
        taken = logic.plan_start_lock({}, now=1000.0)
        assert logic.plan_start_lock(taken, now=1000.0 + logic.START_LOCK_TTL_S - 1) is None
        assert logic.plan_start_lock(taken, now=1000.0 + logic.START_LOCK_TTL_S + 1) is not None

    @pytest.mark.parametrize(
        "value", [None, "", "not-a-number", "1e", "  ", "inf", "-inf", "nan", "9999999999"]
    )
    def test_an_unusable_lock_value_counts_as_free(self, value):
        """Every unusable value must fail *open*. A value nobody can parse — or
        one stamped in the future — must not hold the Start button shut for
        every visitor; releasing too eagerly costs at most the duplicate start
        GCE already absorbs.

        `inf` and `nan` are here because they parse as floats: `float("inf")`
        succeeds, and the first version's clamp then returned the full TTL on
        every call. So did `9999999999` — a lock held until the year 2286, from
        a clamp the implementer wrote *and tested* as if it were a bound (red
        team 2026-07-29 P1)."""
        assert logic.start_lock_seconds_left(value, now=1000.0) == 0.0

    def test_a_lock_from_a_moment_ago_still_holds(self):
        """The fail-open rules must not swallow the ordinary case: a lock
        written seconds ago by the request that is starting the VM."""
        assert logic.start_lock_seconds_left("995", now=1000.0) == pytest.approx(115.0)
        # Small skew forward is tolerated rather than treated as garbage.
        assert logic.start_lock_seconds_left("1003", now=1000.0) > 0

    def test_the_lock_value_is_a_legal_gce_label(self):
        """Label values accept [a-z0-9_-]{0,63}; an illegal one would make the
        conditional write fail and the lock silently never be taken."""
        value = logic.plan_start_lock({}, now=1755039600.5)[logic.START_LOCK_LABEL]
        assert re.fullmatch(r"[a-z0-9_-]{1,63}", value), value
        assert re.fullmatch(r"[a-z][a-z0-9_-]{0,62}", logic.START_LOCK_LABEL)

    def test_the_lock_covers_at_least_the_full_ttl(self):
        """Stamped with `ceil`, not `int`: flooring made the lock up to a second
        shorter than the TTL it advertises (red team 2026-07-29 P3)."""
        taken = logic.plan_start_lock({}, now=1000.9)
        assert taken[logic.START_LOCK_LABEL] == "1001"

    def test_release_drops_the_lock_and_keeps_everything_else(self):
        taken = logic.plan_start_lock({"env": "demo"}, now=1000.0)
        assert logic.release_start_lock(taken) == {"env": "demo"}
        # Releasing a label set that has no lock is a no-op, not a KeyError.
        assert logic.release_start_lock({"env": "demo"}) == {"env": "demo"}

    def test_the_lock_is_shorter_than_the_global_start_floor(self):
        """It only has to cover read→start; after that the 5-minute floor and
        the instance status both refuse a second start on their own."""
        assert logic.START_LOCK_TTL_S < logic.MIN_GLOBAL_START_INTERVAL_S

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
        # gate_key and models_warm joined the contract so "ready" cannot be
        # reported while every query would 403 or block on a cold model load
        # (deploy red team R-14, 2026-07-29).
        assert set(first["services"]) == {
            "vespa",
            "neo4j",
            "llm_config",
            "threshold_artifact",
            "gate_key",
            "models_warm",
        }
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


def test_a_retry_is_debited_against_the_llm_quota(monkeypatch):
    """The quota unit is a user query, but a query whose completion breaks the
    model's output contract is asked twice. Counting only queries would let the
    fence permit twice the completions it advertises (red-team 2026-07-28 P1)."""
    from learnarken.api.demo_guard import DemoGuard

    monkeypatch.setenv("DEMO_PUBLIC", "1")
    monkeypatch.setenv("DEMO_MAX_LLM_CALLS", "2")
    guard = DemoGuard()
    with guard.llm_slot():
        assert guard.try_extra_llm_call()  # this query cost two generations
    # One query is left on paper, but its budget is already spent.
    with pytest.raises(Exception) as caught, guard.llm_slot():
        pass
    assert "limit" in str(caught.value)


def test_try_extra_llm_call_is_open_outside_public_mode(monkeypatch):
    from learnarken.api.demo_guard import DemoGuard

    monkeypatch.delenv("DEMO_PUBLIC", raising=False)
    guard = DemoGuard()
    assert guard.try_extra_llm_call() is True
    assert guard._calls == 0


def test_an_exhausted_quota_declines_the_retry(monkeypatch):
    """Asked before the second call, not reported after it: over quota the
    query refuses on its first failure instead of buying a second generation
    (red-team 2026-07-28 P2)."""
    from learnarken.api.demo_guard import DemoGuard

    monkeypatch.setenv("DEMO_PUBLIC", "1")
    monkeypatch.setenv("DEMO_MAX_LLM_CALLS", "1")
    guard = DemoGuard()
    with guard.llm_slot():
        assert guard.try_extra_llm_call() is False
