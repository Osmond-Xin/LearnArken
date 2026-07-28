"""Arken pillar alignment — Phase 1 (docs/specs/arken-alignment-2026-07-26.md).

Acceptance criteria quote the pinned source snapshot
(docs/research/arken-source-snapshot-2026-07-26.md), not a paraphrase, per
red-team finding F-05.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from learnarken.answer.trace import (
    READABLE_FORMATS,
    TRACE_FORMAT,
    UnreadableTraceError,
    read_trace,
)
from learnarken.chunking.base import Chunk
from learnarken.citation_status import (
    CURRENT,
    SUPERSEDED,
    UNKNOWN,
    UNREGISTERED,
    statuses_for,
)
from learnarken.clearance import ClearanceError, partition
from learnarken.gaps import Gap, GapKind, GapReport, collect_gaps, render_gaps
from learnarken.owners import NO_MAP, OwnerMap
from learnarken.refusal import RESOLUTIONS, route

PKG_A = "samples/package-a"
PKG_B = "samples/package-b"


@pytest.fixture(scope="module")
def corpus_report():
    return collect_gaps([PKG_A, PKG_B])


def test_admission_is_decided_by_the_existing_validator(corpus_report):
    """A gap's kind depends on whether the gate admitted the package it came from."""
    assert corpus_report.admitted_packages == [PKG_A]
    assert corpus_report.rejected_packages == [PKG_B]


def test_clean_package_declares_no_gaps():
    """package-a validates clean, so nothing it declares is missing."""
    report = collect_gaps([PKG_A])
    assert report.gaps == []


def test_declared_but_absent_module_becomes_a_gap_with_a_deterministic_signature(corpus_report):
    """The signature is the DMC the standard supplies — not a generated id."""
    signatures = {g.signature for g in corpus_report.pre_admission_gaps}
    assert "DMC-LA100-A-29-20-00-00A-520A-A" in signatures


def test_both_declaration_paths_are_detected(corpus_report):
    """A module can be declared by a dmRef (XREF-001) or a DML registration (XREF-008)."""
    assert {g.detected_via for g in corpus_report.pre_admission_gaps} == {
        "dmRef",
        "dml-registration",
    }


def test_gap_from_a_rejected_package_is_not_claimed_as_an_admitted_gap(corpus_report):
    """INV-7: Arken's gap is about *admitted* knowledge.

    Everything package-b declares is pre-admission, because the gate rejected
    it. Reporting these as pillar-4 gaps would overclaim.
    """
    assert corpus_report.admitted_gaps == []
    assert corpus_report.pre_admission_gaps
    assert all(
        g.kind is GapKind.PRE_ADMISSION_DECLARED_MISSING for g in corpus_report.pre_admission_gaps
    )


def test_owner_is_routed_when_the_map_knows_the_system(corpus_report):
    """F-11: the routed path must be exercised, not merely permitted."""
    hydraulic = next(
        g for g in corpus_report.gaps if g.signature == "DMC-LA100-A-29-20-00-00A-520A-A"
    )
    assert hydraulic.owner == "Hydraulic Systems Authoring Cell"
    assert hydraulic.routed
    assert "not S1000D" in (hydraulic.owner_source or "")


def test_unknown_owner_surfaces_as_unknown_with_a_reason(corpus_report):
    """F-11: a fabricated owner routes work to someone who does not exist."""
    apu = next(g for g in corpus_report.gaps if g.signature.startswith("DMC-LA100-A-49"))
    assert apu.owner is None
    assert apu.routed is False
    assert "49" in (apu.owner_reason or "")


def test_missing_owner_map_is_stated_not_guessed(tmp_path):
    ref = OwnerMap.load(tmp_path).resolve("DMC-LA100-A-29-10-00-00A-520A-A")
    assert ref.owner is None
    assert ref.reason == NO_MAP


def test_owner_lookup_refuses_an_unparseable_dmc(tmp_path):
    (tmp_path / "owners.json").write_text(json.dumps({"by_system": {"29": "X"}}))
    ref = OwnerMap.load(tmp_path).resolve("not-a-dmc")
    assert ref.owner is None
    assert "SNS" in (ref.reason or "")


def test_sibling_admitted_package_satisfies_a_reference():
    """A reference resolved by another admitted package is not a knowledge gap."""
    both = collect_gaps([PKG_A, "samples/package-c"])
    assert both.admitted_gaps == []


def test_report_serialises_with_counts_per_kind(corpus_report):
    payload = corpus_report.to_dict()
    assert payload["counts"]["admitted_declared_missing"] == 0
    assert payload["counts"]["pre_admission_declared_missing"] == len(
        corpus_report.pre_admission_gaps
    )
    assert payload["gaps"][0]["signature"].startswith("DMC-")


def test_human_render_separates_the_two_classes(corpus_report):
    text = render_gaps(corpus_report)
    assert "Gaps in admitted knowledge (Arken pillar 4): 0" in text
    assert "Declared-missing in rejected packages (pre-admission): 2" in text


# --------------------------------------------------------------------------
# Pillar 1 — "Authorization constrains reasoning, not just retrieval" (/trust)
# --------------------------------------------------------------------------


def _classified(cid: str, classification: str | None) -> Chunk:
    return Chunk(
        chunk_id=cid,
        strategy="structure",
        dmc=f"DMC-LA100-A-29-10-00-00A-520A-{cid}",
        dm_title="Hydraulic pump",
        issue_info="001-00",
        chunk_type="step",
        source_path=f"/dmodule/content/procedure/mainProcedure/proceduralStep[{cid}]",
        text="Release the hydraulic pressure.",
        security_classification=classification,
    )


def test_clearance_admits_at_or_below_and_withholds_above():
    chunks = [_classified("a", "01"), _classified("b", "03")]
    admitted, withheld = partition(chunks, "02")
    assert [c.chunk_id for c in admitted] == ["a"]
    assert [w.chunk_id for w in withheld] == ["b"]
    assert withheld[0].reason == "authorisation"
    assert "exceeds clearance" in withheld[0].detail


def test_unlabelled_chunk_is_withheld_not_assumed_unclassified():
    """Fail closed: an unlabelled chunk is the malformed input the gate exists for."""
    admitted, withheld = partition([_classified("a", None)], "05")
    assert admitted == []
    assert "no securityClassification" in withheld[0].detail


def test_no_clearance_requested_means_no_filtering_and_no_claim():
    chunks = [_classified("a", "01"), _classified("b", None)]
    admitted, withheld = partition(chunks, None)
    assert len(admitted) == 2
    assert withheld == []


def test_unknown_clearance_is_rejected_not_coerced():
    with pytest.raises(ClearanceError, match="unknown clearance"):
        partition([_classified("a", "01")], "99")


def test_bm25_index_is_built_only_from_admitted_chunks(monkeypatch):
    """The offline arm: inadmissible text must never enter the index at all."""
    import learnarken.retrieval as retrieval

    indexed: dict = {}

    class _Recorder:
        def __init__(self, chunks):
            indexed["ids"] = [c.chunk_id for c in chunks]

        def search(self, query, k):
            return []

    monkeypatch.setattr(
        retrieval, "corpus_chunks", lambda *a, **k: [_classified("a", "01"), _classified("b", "04")]
    )
    monkeypatch.setattr(retrieval, "BM25Index", _Recorder)
    retrieval.search_package("samples/package-a", "pump", mode="bm25", clearance="02")
    assert indexed["ids"] == ["a"], "a chunk above clearance reached the BM25 index"


def test_clearance_lands_in_the_yql_before_nearest_neighbor(monkeypatch):
    """The engine arm: the constraint is in the query, not applied to results.

    This is the assertion red-team F-01 asked for — that retrieval itself never
    sees the inadmissible chunk, rather than that a filter ran early.
    """
    from learnarken.vespa import store

    captured: dict = {}

    def fake_request(url, payload=None, method="GET", timeout=30):
        captured.update(payload or {})
        return {"root": {"children": []}}

    monkeypatch.setattr(store, "_request", fake_request)
    store.search([0.0], clearance="02")
    yql = captured["yql"]
    assert 'security_classification contains "01"' in yql
    assert 'security_classification contains "02"' in yql
    assert 'security_classification contains "03"' not in yql
    where = yql.split(" where ", 1)[1]
    assert "nearestNeighbor" in where and "security_classification" in where


def test_engine_leak_above_clearance_fails_closed(monkeypatch):
    """If the engine-side constraint ever fails, the result set is refused."""
    from learnarken.vespa import store

    leaked = store._document_fields(_classified("c9", "05"), "package-a")
    leaked.pop("embedding", None)
    monkeypatch.setattr(
        store,
        "_request",
        lambda *a, **k: {"root": {"children": [{"fields": leaked, "relevance": 0.9}]}},
    )
    with pytest.raises(ClearanceError, match="did not hold"):
        store.search([0.0], clearance="02")


# --------------------------------------------------------------------------
# Pillar 3 — refusal as a routed action item (why / what would resolve / who)
# --------------------------------------------------------------------------


def test_every_gate_says_what_would_resolve_it():
    """A new gate cannot ship without resolution advice."""
    from learnarken.answer.models import AnswerResult

    documented = set(RESOLUTIONS)
    declared = {
        g.strip().strip('"')
        for g in (AnswerResult.model_fields["refusal_gate"].description or "").split("|")
        if g.strip()
    }
    # The engine's gate names, taken from the module that emits them.
    emitted = {"threshold", "llm", "llm-contract", "citation-validation"}
    assert emitted <= documented, f"gates without resolution advice: {emitted - documented}"
    assert declared <= documented or not declared


def test_refusal_without_a_named_module_does_not_route_an_owner():
    """The APU case: the corpus is silent, so there is nobody to route to."""
    action = route("APU automatic start sequence", "llm", [PKG_A, PKG_B])
    assert action.owner is None
    assert action.routed is False
    assert action.gap_signature is None
    assert "names no data module" in (action.owner_reason or "")
    assert action.what_would_resolve


def test_refusal_does_not_route_on_a_rejected_package_s_ownership_metadata():
    """Red-team P1 (2026-07-27): route only from *admitted* gaps.

    package-b was rejected at ingest, so its `owners.json` was never admitted
    either. Routing work on its authority would trust exactly the input the
    gate refused. The gap is still reported — it is just not routed.
    """
    action = route(
        "What does DMC-LA100-A-29-20-00-00A-520A-A say about the pump?",
        "threshold",
        [PKG_A, PKG_B],
    )
    assert action.owner is None
    assert action.routed is False
    assert "rejected" in (action.owner_reason or "")


def test_refusal_routes_when_an_admitted_gap_matches(monkeypatch):
    """Option A's routed path.

    Synthetic by necessity: an *admitted* declared-missing module cannot occur
    on this corpus, because a dangling reference is an ingest error and its
    package is rejected (the same structural boundary `gaps.py` documents). The
    routing code is still exercised rather than left dead.
    """
    import learnarken.gaps as gaps_mod

    gap = Gap(
        signature="DMC-LA100-A-29-20-00-00A-520A-A",
        kind=GapKind.ADMITTED_DECLARED_MISSING,
        declared_by="DMC-LA100-A-29-10-00-00A-040A-D_EN-CA.xml",
        declared_in_package=PKG_A,
        detected_via="dmRef",
        owner="Hydraulic Systems Authoring Cell",
        owner_source="owners.json (project-authored synthetic data, not S1000D)",
    )
    monkeypatch.setattr(
        gaps_mod, "collect_gaps", lambda dirs: GapReport(admitted_packages=[PKG_A], gaps=[gap])
    )
    action = route("What about DMC-LA100-A-29-20-00-00A-520A-A?", "threshold", [PKG_A])
    assert action.gap_signature == gap.signature
    assert action.owner == "Hydraulic Systems Authoring Cell"
    assert action.routed


def test_refusal_naming_a_present_module_is_not_treated_as_a_gap():
    action = route("Tell me about DMC-LA100-A-29-10-00-00A-520A-A", "llm", [PKG_A])
    assert action.owner is None
    assert action.gap_signature is None
    assert "not a declared-missing module" in (action.owner_reason or "")


def test_admitted_gap_with_no_registered_owner_names_the_gap_but_routes_nothing(monkeypatch):
    """A known gap whose owner is unknown must not borrow a plausible one."""
    import learnarken.gaps as gaps_mod

    gap = Gap(
        signature="DMC-LA100-A-49-00-00-00A-040A-D",
        kind=GapKind.ADMITTED_DECLARED_MISSING,
        declared_by="DML-LA100-LEARN-C-2026-00002.xml",
        declared_in_package=PKG_A,
        detected_via="dml-registration",
        owner=None,
        owner_reason="no owner registered for SNS system 49",
    )
    monkeypatch.setattr(
        gaps_mod, "collect_gaps", lambda dirs: GapReport(admitted_packages=[PKG_A], gaps=[gap])
    )
    action = route("status of DMC-LA100-A-49-00-00-00A-040A-D", "llm", [PKG_A])
    assert action.gap_signature == gap.signature
    assert action.owner is None
    assert "49" in (action.owner_reason or "")


def test_broken_owner_map_yields_unknown_owner_not_an_error(tmp_path):
    """Red-team P2: a malformed map must not turn a decided refusal into a crash."""
    (tmp_path / "owners.json").write_text("{ not json", encoding="utf-8")
    ref = OwnerMap.load(tmp_path).resolve("DMC-LA100-A-29-10-00-00A-520A-A")
    assert ref.owner is None
    assert "could not be read" in (ref.reason or "")


def test_unknown_gate_says_so_rather_than_inventing_advice():
    action = route("anything", "some-new-gate", None)
    assert "bug in the refusal router" in action.what_would_resolve


# --------------------------------------------------------------------------
# Pillar 2 — trace carries sources *excluded* and each source's *status*
# --------------------------------------------------------------------------


def test_trace_format_bumped_but_v1_still_readable(tmp_path):
    """F-16: a format bump must not retro-break an audit record already written.

    No v1 trace is committed (`eval/traces/` is git-ignored), so this
    reconstructs one rather than claiming to read a historical file.
    """
    v1 = tmp_path / "old.json"
    v1.write_text(
        json.dumps({"format": "learnarken-answer-trace/1", "trace_id": "t1", "question": "q"}),
        encoding="utf-8",
    )
    assert read_trace(v1)["trace_id"] == "t1"
    assert TRACE_FORMAT == "learnarken-answer-trace/2"
    assert "learnarken-answer-trace/1" in READABLE_FORMATS


def test_unknown_trace_format_fails_closed(tmp_path):
    """Reading an audit record under the wrong schema is a confident misreading."""
    future = tmp_path / "future.json"
    future.write_text(json.dumps({"format": "learnarken-answer-trace/99"}), encoding="utf-8")
    with pytest.raises(UnreadableTraceError, match="format"):
        read_trace(future)


def test_citation_status_is_confirmed_against_the_dml_registry():
    """`status` is re-derived from the registry, not assumed from ingest."""
    (status,) = statuses_for([("DMC-LA100-A-29-10-00-00A-520A-A", "001-00")], [PKG_A])
    assert status.state == CURRENT
    assert status.registered_issue == "001-00"
    # The basis names the gates that make the guarantee, so a reader can check
    # it rather than take "current" on faith.
    assert "XREF-003" in status.basis and "XREF-007" in status.basis


def test_unregistered_module_is_not_reported_as_current():
    """A module no DML registers cannot be confirmed — say so, don't assume."""
    (status,) = statuses_for([("DMC-LA100-A-99-99-00-00A-520A-A", "001-00")], [PKG_A])
    assert status.state == UNREGISTERED
    assert status.registered_issue is None


def test_status_lookup_failure_degrades_to_unknown_and_names_the_cause(monkeypatch):
    """A status lookup failing must not void an already-verified answer.

    Red-team P2: `unknown` without a stated cause is not auditable, so the
    basis names the exception class.
    """
    import learnarken.citation_status as cs

    def boom(dirs):
        raise OSError("disk gone")

    monkeypatch.setattr(cs, "_registry", boom)
    (status,) = cs.statuses_for([("DMC-X", "001-00")], [PKG_A])
    assert status.state == UNKNOWN
    assert "OSError" in status.basis


def test_programming_error_in_status_lookup_is_not_absorbed(monkeypatch):
    """The catch is narrow on purpose: a bug must surface, not become `unknown`."""
    import learnarken.citation_status as cs

    def boom(dirs):
        raise RuntimeError("bug")

    monkeypatch.setattr(cs, "_registry", boom)
    with pytest.raises(RuntimeError):
        cs.statuses_for([("DMC-X", "001-00")], [PKG_A])


def test_citation_status_flags_a_registry_mismatch_as_superseded():
    """Red-team P1: the first version never compared the issues and would have
    called a mismatch `current` — the exact bug consulting a registry prevents."""
    (status,) = statuses_for([("DMC-LA100-A-29-10-00-00A-520A-A", "000-00")], [PKG_A])
    assert status.state == SUPERSEDED
    assert status.registered_issue == "001-00"


def test_authorisation_exclusions_do_not_name_the_withheld_module(monkeypatch, tmp_path):
    """Red-team P2: the trace must not enumerate classified DMCs to a caller
    who was denied their content. `chunk_id` is an opaque digest and stays."""
    import learnarken.answer.engine as eng

    monkeypatch.chdir(tmp_path)
    (tmp_path / "eval" / "traces").mkdir(parents=True)
    withheld = [_classified("secret", "05")]
    monkeypatch.setattr(eng, "corpus_chunks", lambda *a, **k: [*withheld, _classified("ok", "01")])
    monkeypatch.setattr(eng, "verify_corpus", lambda *a, **k: None)
    monkeypatch.setattr(eng, "load_threshold", lambda *a, **k: 0.5)
    monkeypatch.setattr(eng, "_candidates", lambda q, c, mode, clearance=None: [])
    monkeypatch.setattr(eng, "rerank_scored", lambda *a, **k: [], raising=False)
    result = eng.answer_question("anything", package_dirs=[str(tmp_path)], clearance="02")
    trace = read_trace(Path("eval/traces") / f"{result.trace_id}.json")
    authorisation = [e for e in trace["sources_excluded"] if e["reason"] == "authorisation"]
    assert authorisation, "the withheld chunk should appear as an exclusion"
    assert authorisation[0]["dmc"] == "[redacted — above caller clearance]"
    assert authorisation[0]["chunk_id"] == "secret"
    assert trace["authorisation"] == {"clearance": "02", "enforced": True, "withheld": 1}


def test_trace_v2_carries_the_declared_span_set(monkeypatch, tmp_path):
    """A trace whose span set drifts silently is an audit record nobody can rely on."""
    from learnarken.answer.trace import write_trace

    monkeypatch.chdir(tmp_path)
    path = write_trace("t", {"question": "q", "sources_excluded": [], "outcome": {}})
    data = read_trace(path)
    assert data["format"] == TRACE_FORMAT
    assert {"question", "sources_excluded", "outcome"} <= set(data)


def test_schema_change_invalidates_the_index_manifest(tmp_path, monkeypatch):
    """Red-team P2 (2026-07-27). Failure-shaped, not claim-shaped: mutate the
    manifest's digest and assert `verify_corpus` actually refuses."""
    import learnarken.retrieval as retrieval
    from learnarken.embedding.providers import DEFAULT_PROVIDER, DIMENSIONS, REVISIONS
    from learnarken.vespa import store

    baseline = store.schema_digest()
    assert store.schema_digest() == baseline, "digest must be stable for identical content"
    # A different application package must produce a different digest.
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "chunk.sd").write_text("schema chunk { }", encoding="utf-8")
    assert store.schema_digest(tmp_path) != baseline

    chunk = _classified("c1", "01")
    monkeypatch.chdir(tmp_path)
    (tmp_path / retrieval.MANIFEST_PATH.name).write_text(
        json.dumps(
            {
                "packages": ["samples/package-a"],
                "strategy": "structure",
                "provider": DEFAULT_PROVIDER,
                "revision": REVISIONS[DEFAULT_PROVIDER],
                "dimension": DIMENSIONS[DEFAULT_PROVIDER],
                "chunk_ids": [chunk.chunk_id],
                "schema_digest": "0" * 16,  # fed under a different schema
            }
        ),
        encoding="utf-8",
    )
    import learnarken.vespa as vespa

    monkeypatch.setattr(vespa, "list_doc_ids", lambda: {chunk.chunk_id})
    with pytest.raises(ValueError, match="schema digest"):
        retrieval.verify_corpus([chunk], "structure")


def test_graph_facts_never_leak_a_withheld_neighbour():
    """Red-team P0 (2026-07-27): partitioning filters chunks, not graph edges,
    and graph refs are injected into the prompt."""
    from learnarken.clearance import redact_graph_facts
    from learnarken.graph import GraphFacts

    fact = GraphFacts(
        dmc="DMC-LA100-A-29-10-00-00A-520A-A",
        outbound_refs=["DMC-OK", "DMC-SECRET"],
        inbound_refs=["DMC-SECRET"],
    )
    (redacted,) = redact_graph_facts([fact], {"DMC-OK"}, "02")
    assert redacted.outbound_refs == ["DMC-OK"]
    assert redacted.inbound_refs == []
    assert redacted.withheld_refs == 2, "the redaction must be counted, not silent"
    # With no clearance enforced nothing is filtered and nothing is claimed.
    (untouched,) = redact_graph_facts([fact], {"DMC-OK"}, None)
    assert untouched.outbound_refs == ["DMC-OK", "DMC-SECRET"]


def test_citation_with_no_issue_is_unknown_not_current():
    """Red-team P2: missing metadata must not be laundered into a guarantee."""
    (status,) = statuses_for([("DMC-LA100-A-29-10-00-00A-520A-A", "")], [PKG_A])
    assert status.state == UNKNOWN
    assert "cannot be compared" in status.basis


def test_local_only_fence_blocks_an_external_judge(monkeypatch):
    """Red-team P2: the README claimed the fence covered the eval harness."""
    from learnarken.adversarial.judge import CLIJudge

    monkeypatch.setenv("LEARNARKEN_LOCAL_ONLY", "1")
    judge = CLIJudge(name="codex")
    with pytest.raises(ValueError, match="egress fence"):
        judge.score("q", "a", ["evidence"])


def test_security_classification_is_an_attribute_in_the_schema():
    """Summary-only made engine-side filtering impossible (F-01 root cause)."""
    schema = Path("src/learnarken/vespa/app/schemas/chunk.sd").read_text(encoding="utf-8")
    block = schema.split("field security_classification", 1)[1].split("}", 1)[0]
    assert "attribute" in block


def test_mixed_classification_corpus_cannot_be_evaluated_unscoped():
    """Red-team P1: eval writes committed artifacts, so an unscoped run over a
    mixed-class corpus would publish what the governed path withholds."""
    from learnarken.clearance import assert_uniform_or_scoped

    mixed = [_classified("a", "01"), _classified("b", "03")]
    with pytest.raises(ClearanceError, match="mixes security classifications"):
        assert_uniform_or_scoped(mixed, None)
    # Uniform corpus, and any explicitly-scoped run, are both fine.
    assert_uniform_or_scoped([_classified("a", "01"), _classified("b", "01")], None)
    assert_uniform_or_scoped(mixed, "05")


def test_figure_second_look_only_loads_the_citing_module_s_asset(tmp_path):
    """Red-team P1: resolving by ICN alone can load another package's image."""
    from learnarken.answer import figure_relook

    rec = type("R", (), {"icn_id": "ICN-X", "verified": True, "source_dm": "DMC-OTHER"})()
    monkey = [rec]
    original = figure_relook.ingest.load_records
    try:
        figure_relook.ingest.load_records = lambda pkg: monkey
        assert figure_relook._load_asset("ICN-X", [str(tmp_path)], "DMC-MINE") is None
    finally:
        figure_relook.ingest.load_records = original


def _probe():
    """The INV-6 retry probe, loaded the way the demo-trace checker is."""
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "tools" / "probe_retry_effectiveness.py"
    spec = importlib.util.spec_from_file_location("probe_retry_effectiveness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: A trace read back that recorded no contract event — all three fields
#: present and None. An empty dict is a *partial* reading, not a silent one.
_SILENT = {
    "recovered_after_contract_failure": None,
    "contract_error": None,
    "first_attempt_error": None,
}


def _sse(*frames: str) -> str:
    return "".join(frames)


def _client(body: str, status: int = 200, content_type: str = "text/event-stream"):
    response = type(
        "R", (), {"text": body, "status_code": status, "headers": {"content-type": content_type}}
    )()
    return type("C", (), {"post": lambda self, url, json: response})()


def test_the_retry_probe_counts_a_late_refusal_as_a_recovery():
    """A re-ask can succeed and the run still refuse at a *later* gate. Scoring
    that as a retry failure would understate the thing the probe measures, so
    only an `llm-contract` refusal after a restart counts against the re-ask."""
    probe = _probe()

    def result(gate, restarts):
        # `refused` and `refusal_gate` always agree in a coherent result.
        return {
            "saw_result": True,
            "stream_restarts": restarts,
            "refusal_gate": gate,
            "refused": gate is not None,
        }

    assert probe.classify(result("citation", 1)) == "retried_recovered"
    assert probe.classify(result(None, 1)) == "retried_recovered"
    assert probe.classify(result("llm-contract", 1)) == "retried_failed"
    # No restart: truncation refuses without a second ask, and that is not a
    # datum about recovery at all.
    assert probe.classify(result("llm-contract", 0)) == "not_retried"
    assert probe.classify(result(None, 0)) == "clean"


def test_the_retry_probe_never_scores_a_died_in_transport_retry_as_recovered():
    """Red-team P0: the re-ask fires, the second generation dies mid-stream, so
    there is no `result` and no refusal gate. Testing the restart first scored
    that as a recovery — a confidently wrong value of the one number this probe
    exists to produce."""
    probe = _probe()
    row = {"stream_restarts": 1, "saw_result": False, "stream_error": "connection reset"}
    assert probe.classify(row) == "retried_indeterminate"
    # And it is excluded from the denominator, not counted as a failure either.
    report, quotable = probe.tally(
        [_settled("retried_indeterminate", trace_llm=None, trace_outcome=None, trace_spans=None)]
    )
    assert "recovery metric withheld" in report
    assert quotable is False


def test_the_retry_probe_treats_a_non_sse_reply_as_a_non_observation():
    """Red-team P1: a 403 from the demo gate has no events at all, and an
    event-counting parser reads that as a flawless run."""
    probe = _probe()
    row = probe.run_once(
        _client('{"detail": "forbidden"}', status=403, content_type="application/json"), "q"
    )
    assert probe.classify(row) == "non_observation"
    assert row["http_status"] == 403


def test_the_retry_probe_refuses_to_quote_a_sample_with_holes():
    """INV-4: a missing second reading, a contradiction, or a paid run with no
    logged outcome does not make the number smaller — it makes it not a number."""
    probe = _probe()
    trace = {
        "recovered_after_contract_failure": "keys=[...]",
        "contract_error": None,
        "first_attempt_error": None,
    }
    sound = [
        _settled("retried_recovered", trace_llm=trace),
        _settled("clean"),
    ]
    report, quotable = probe.tally(sound)
    assert quotable is True and "recovered 1 of 1" in report
    # Same rows, but one has no trace read back.
    holed = [sound[0], _settled("clean", trace_llm=None)]
    report, quotable = probe.tally(holed)
    assert quotable is False and "UNQUOTABLE" in report
    # And a paid run that never logged an outcome blocks it too.
    report, quotable = probe.tally(sound, unfinished=1)
    assert quotable is False and "never finished" in report


def test_the_retry_probe_cross_checks_the_whole_outcome_matrix():
    """Red-team P2: a partial matrix passes the states it forgot as agreement,
    which defeats the point of taking a second reading."""
    probe = _probe()
    recovered = {
        "recovered_after_contract_failure": "keys=[...]",
        "contract_error": None,
        "first_attempt_error": None,
    }
    silent = {
        "recovered_after_contract_failure": None,
        "contract_error": None,
        "first_attempt_error": None,
    }
    ran = {"llm": True, "generation": True}
    assert (
        probe.disagrees(
            {"outcome": "retried_recovered", "trace_llm": recovered, "trace_spans": ran}
        )
        is False
    )
    assert probe.disagrees({"outcome": "clean", "trace_llm": recovered, "trace_spans": ran}) is True
    assert (
        probe.disagrees({"outcome": "retried_recovered", "trace_llm": silent, "trace_spans": ran})
        is True
    )
    # The state the first version omitted: stream saw no retry, trace did.
    assert (
        probe.disagrees({"outcome": "not_retried", "trace_llm": recovered, "trace_spans": ran})
        is True
    )
    # A missing trace is a gap in the second reading, not a contradiction.
    assert probe.disagrees({"outcome": "clean", "trace_llm": None}) is False
    # A reading with no raw span facts is not a reading at all.
    assert probe.disagrees({"outcome": "clean", "trace_llm": silent}) is True


def test_the_retry_probe_reads_a_restart_out_of_the_event_stream():
    """The restart event is the whole first reading; if the SSE parse misses it
    every count downstream is wrong while still looking well-formed."""
    probe = _probe()
    body = _sse(
        'event: status\ndata: {"stage": "generating"}\n\n',
        'event: token\ndata: {"text": "half an ans"}\n\n',
        'event: restart\ndata: {"reason": "llm-contract"}\n\n',
        'event: token\ndata: {"text": "the real one"}\n\n',
        'event: result\ndata: {"trace_id": "20260728T120007-000000a7",'
        ' "refused": false, "refusal_gate": null}\n\n',
        "event: done\ndata: {}\n\n",
    )
    row = probe.run_once(_client(body), "q")
    assert row["stream_restarts"] == 1
    assert row["token_events"] == 2
    assert row["trace_id"] == "20260728T120007-000000a7"
    assert probe.classify(row) == "retried_recovered"
    # No trace on disk for a synthetic id: reported as a gap in the second
    # reading, never silently treated as agreement.
    assert row["trace_llm"] is None and "not written" in row["trace_note"]


def test_the_retry_probe_parses_sse_by_frame_not_by_line():
    """A `data:` line belongs to the `event:` in its own frame. Attributing it
    to the last event seen anywhere in the body mis-reads a payload the moment
    the producer emits a multi-line or data-less frame."""
    probe = _probe()
    frames = probe.parse_sse(
        ": keep-alive\n\n"
        'event: restart\ndata: {\ndata:  "reason": "llm-contract"\ndata: }\n\n'
        "event: done\n\n"
    )
    assert frames == [("restart", '{\n "reason": "llm-contract"\n}'), ("done", "")]
    assert json.loads(frames[0][1])["reason"] == "llm-contract"


def test_the_retry_probe_reads_the_trace_schema_the_writer_actually_writes(tmp_path, monkeypatch):
    """Red-team P0, and the reason the first version's cross-check was no check
    at all: `write_trace` splats the spans into the trace *root*, so reading
    `spans.llm` always found nothing and every run agreed with silence. Written
    against a real artifact rather than a hand-built dict, because a hand-built
    dict is exactly what hid this."""
    from learnarken.answer import trace as trace_module

    probe = _probe()
    monkeypatch.setattr(trace_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)
    trace_module.write_trace(
        "20260728T120001-000000a1",
        {
            "llm": {"recovered_after_contract_failure": "keys=[...]"},
            "outcome": {"refused": False},
        },
    )

    second_reading = probe.read_back_trace("20260728T120001-000000a1")
    assert second_reading["trace_note"] is None
    assert second_reading["trace_llm"]["recovered_after_contract_failure"] == "keys=[...]"
    # A stream that claims nothing was re-asked now contradicts that trace.
    assert probe.disagrees({"outcome": "clean", **second_reading}) is True


def _start(number: int) -> str:
    """A `start` marker with the tag the cycle assigns for that run number."""
    return json.dumps(
        {"kind": "start", "run": number, "query": ["answer", "retraction"][(number - 1) % 2]}
    )


_TID = "20260728T120009-000000a9"
_RAN = {"llm": True, "generation": True}
_NO_MODEL = {"llm": False, "generation": False}


def _settled(outcome: str, **over) -> dict:
    """A tally row with a complete second reading — all three parts present."""
    row = {
        "outcome": outcome,
        "disagreement": False,
        "trace_llm": dict(_SILENT),
        "trace_outcome": {"refused": outcome != "clean", "gate": None},
        "trace_spans": dict(_NO_MODEL if outcome == "no_generation" else _RAN),
    }
    return {**row, **over}


_PLAN = [
    ["answer", "What safety precautions apply before removing the hydraulic pump?"],
    ["retraction", "APU automatic start sequence"],
]


def _log(tmp_path, *lines: str, version: str | None = "probe-retry/9"):
    log = tmp_path / "probe.jsonl"
    head = [json.dumps({"kind": "meta", "version": version, "queries": _PLAN})] if version else []
    log.write_text("\n".join([*head, *lines]) + "\n", encoding="utf-8")
    return log


def _run_row(number: int, **overrides) -> str:
    """A complete outcome row — every field the replay must be able to read."""
    row = {
        "kind": "run",
        "run": number,
        "query": ["answer", "retraction"][(number - 1) % 2],
        "saw_result": True,
        "token_events": 0,
        "stream_restarts": 0,
        "stream_error": None,
        "refusal_gate": None,
        "refused": False,
        "trace_id": f"20260728T12{number:04d}-{number:08x}",
        "trace_llm": dict(_SILENT),
        "trace_outcome": {"refused": False, "gate": None},
        "trace_spans": {"llm": True, "generation": True},
    }
    return json.dumps({**row, **overrides})


def test_the_retry_probe_log_refuses_a_double_counted_run(tmp_path):
    """Two shells appending to one log would double every count. De-duplicating
    silently would be a guess about which row is real."""
    probe = _probe()
    log = _log(tmp_path, _start(1), _run_row(1), _run_row(1))
    with pytest.raises(SystemExit, match="logged twice"):
        probe.load_prior(log)


def test_the_retry_probe_log_remembers_a_run_it_paid_for_but_never_saw_finish(tmp_path):
    """^C between the call and the outcome line: the money was spent and the
    observation is gone. A resumed sample must not look complete."""
    probe = _probe()
    log = _log(
        tmp_path,
        _start(1),
        _run_row(1),
        _start(2),
    )
    rows, unfinished, next_number = probe.load_prior(log)
    assert [r["run"] for r in rows] == [1]
    assert unfinished == 1
    # Red-team round 2 P0: allocating from the *finished* rows would hand out 2
    # again, and the next resume would see start/run pairs that balance — the
    # paid run erased by an accounting choice.
    assert next_number == 3


def test_the_retry_probe_refuses_to_resume_a_log_from_an_older_build(tmp_path):
    """Red-team round 2 P0: rows carry the verdicts of the logic that wrote
    them, and one shipped version's cross-check agreed with everything."""
    probe = _probe()
    stale = _log(tmp_path, version="probe-retry/1")
    with pytest.raises(SystemExit, match="probe-retry/1"):
        probe.load_prior(stale)
    unversioned = _log(tmp_path, _start(1), version=None)
    with pytest.raises(SystemExit, match="not the version meta"):
        probe.load_prior(unversioned)


def test_the_retry_probe_recomputes_stored_verdicts_rather_than_trusting_them(tmp_path):
    """A row's `outcome` is a conclusion, not an observation. Trusting the
    stored one lets a verdict from superseded logic survive into a new sample."""
    probe = _probe()
    log = _log(
        tmp_path,
        _start(1),
        _run_row(
            1,
            stream_restarts=1,
            refusal_gate="llm-contract",
            refused=True,
            trace_llm={
                "recovered_after_contract_failure": None,
                "contract_error": "keys=[...]",
                "first_attempt_error": "keys=[...]",
            },
            outcome="clean",
            disagreement=False,
        ),
    )
    rows, _, _ = probe.load_prior(log)
    assert rows[0]["outcome"] == "retried_failed"


def test_the_retry_probe_treats_an_all_clean_sample_as_no_reading_of_recovery(tmp_path):
    """Red-team round 2 P2: 24 runs where nothing went wrong measures the base
    rate and says nothing about the re-ask, so it must not exit success."""
    probe = _probe()
    report, quotable = probe.tally(
        [{"outcome": "clean", "disagreement": False, "trace_llm": _SILENT}] * 5
    )
    assert quotable is False
    assert "no denominator" in report


def test_the_retry_probe_survives_a_truncated_frame_without_inventing_a_reading(tmp_path):
    """A body cut mid-JSON must become a non-observation, not a crash that
    loses every run already logged this session."""
    probe = _probe()
    body = (
        'event: token\ndata: {"text": "a"}\n\n'
        'event: result\ndata: {"trace_id": "20260728T120007-000000a7"\n\n'
    )
    row = probe.run_once(_client(body), "q")
    assert probe.classify(row) == "non_observation"
    assert "undecodable" in row["transport_note"]


def test_the_retry_probe_parses_crlf_framing(tmp_path):
    """A proxy that rewrites line endings would otherwise merge every frame
    into one block and bury the restart inside it."""
    probe = _probe()
    frames = probe.parse_sse(
        'event: restart\r\ndata: {"reason": "llm-contract"}\r\n\r\nevent: done\r\ndata: {}\r\n\r\n'
    )
    assert frames == [("restart", '{"reason": "llm-contract"}'), ("done", "{}")]


def test_the_retry_probe_holds_its_lock_before_it_reads_the_log(tmp_path):
    """Red-team round 3 P0: locking after replay leaves a window where two
    probes derive the same next run number from the same stale state and each
    writes a report that omits the other's paid run."""
    probe = _probe()
    out = tmp_path / "probe.jsonl"
    first = probe.lock_log(out)
    assert first is not None
    try:
        assert probe.lock_log(out) is None
    finally:
        first.close()
    # Released with the handle, so the next session can take it.
    second = probe.lock_log(out)
    assert second is not None
    second.close()


def test_the_retry_probe_rejects_an_outcome_row_with_no_start(tmp_path):
    """Red-team round 3 P1: a `run` row with no matching `start` was never paid
    for by this accounting, so adopting it as evidence imports a stranger's
    number."""
    probe = _probe()
    log = _log(tmp_path, _run_row(1))
    with pytest.raises(SystemExit, match="no start"):
        probe.load_prior(log)


def test_the_retry_probe_rejects_a_row_whose_verdict_cannot_be_recomputed(tmp_path):
    """Red-team round 3 P1: `.get()` on a missing key returns None, and None is
    a *value* in this classification — a row without `refusal_gate` would come
    back as a recovery rather than as the unreadable row it is."""
    probe = _probe()
    row = json.loads(_run_row(1, stream_restarts=1))
    del row["refusal_gate"]
    log = _log(tmp_path, _start(1), json.dumps(row))
    with pytest.raises(SystemExit, match="missing refusal_gate"):
        probe.load_prior(log)


def test_the_retry_probe_rejects_an_unknown_record_kind(tmp_path):
    probe = _probe()
    log = _log(tmp_path, '{"kind": "note", "run": 1}')
    with pytest.raises(SystemExit, match="unknown record kind"):
        probe.load_prior(log)


def test_the_retry_probe_names_an_empty_log_for_what_it_is(tmp_path):
    """A crash between creating the file and writing meta leaves a stub. Failing
    closed is right; blaming it on an older build is not what happened."""
    probe = _probe()
    stub = tmp_path / "probe.jsonl"
    stub.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="abandoned log"):
        probe.load_prior(stub)


def test_the_retry_probe_treats_more_than_one_restart_as_no_reading(tmp_path):
    """The engine re-asks exactly once. Two restarts means the producer is not
    the one this classification was written against."""
    probe = _probe()
    row = {"saw_result": True, "stream_restarts": 2, "refusal_gate": None}
    assert probe.classify(row) == "retried_indeterminate"


def test_the_retry_probe_session_reserves_the_worst_case_before_each_run(tmp_path):
    """Red-team round 2 P1 / round 3 P2: admitting a run with one generation of
    budget left lets a re-ask overshoot the cap the fence advertises."""
    probe = _probe()
    body = _sse(
        'event: restart\ndata: {"reason": "llm-contract"}\n\n',
        'event: result\ndata: {"trace_id": "20260728T120008-000000a8",'
        ' "refused": false, "refusal_gate": null}\n\n',
    )
    log = (tmp_path / "probe.jsonl").open("w", encoding="utf-8")
    rows: list = []
    with log:
        charged = probe.run_session(_client(body), log, rows, 1, runs=5, budget=3)
    # Each run charges 2 (one generation plus the re-ask), so a budget of 3
    # admits exactly one — never a second that could overshoot to 4.
    assert charged == 2
    assert [r["run"] for r in rows] == [1]


def test_the_retry_probe_session_numbers_runs_from_where_the_log_left_off(tmp_path):
    """Run numbers continue above every id ever seen, including a paid run that
    never logged an outcome."""
    probe = _probe()
    body = _sse(
        'event: result\ndata: {"trace_id": "20260728T120008-000000a8",'
        ' "refused": false, "refusal_gate": null}\n\n'
    )
    log = (tmp_path / "probe.jsonl").open("w", encoding="utf-8")
    rows: list = []
    with log:
        probe.run_session(_client(body), log, rows, 7, runs=2, budget=10)
    assert [r["run"] for r in rows] == [7, 8]


def test_the_retry_probe_locks_by_canonical_path_not_by_alias(tmp_path):
    """Red-team round 4 P1: two symlinks to one log get two sibling locks, and
    each session appends to the same artifact while reporting only its own."""
    probe = _probe()
    real = tmp_path / "real.jsonl"
    real.write_text("", encoding="utf-8")
    alias = tmp_path / "alias.jsonl"
    alias.symlink_to(real)
    held = probe.lock_log(real.resolve())
    assert held is not None
    try:
        assert probe.lock_log(alias.resolve()) is None
    finally:
        held.close()


def test_the_retry_probe_rejects_a_meta_line_appended_after_the_rows(tmp_path):
    """Red-team round 4 P1: tacking the current version onto the end of an old
    log would launder its rows into a current measurement."""
    probe = _probe()
    log = tmp_path / "probe.jsonl"
    log.write_text(
        '{"kind": "start", "run": 1}\n{"kind": "meta", "version": "probe-retry/9"}\n',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="not the version meta"):
        probe.load_prior(log)


def test_the_retry_probe_rejects_a_count_that_is_not_a_count(tmp_path):
    """Red-team round 4 P1: `-1` is truthy, so a negative restart count would
    read as a re-ask that recovered."""
    probe = _probe()
    log = _log(tmp_path, _start(1), _run_row(1, stream_restarts=-1))
    with pytest.raises(SystemExit, match="not a count"):
        probe.load_prior(log)
    log2 = _log(tmp_path, _start(1), _run_row(1, saw_result="yes"))
    with pytest.raises(SystemExit, match="non-boolean saw_result"):
        probe.load_prior(log2)


def test_the_retry_probe_rejects_a_partial_second_reading(tmp_path):
    """Red-team round 4 P3: an empty `trace_llm` passes the cross-check as
    agreement while carrying no second reading at all."""
    probe = _probe()
    log = _log(tmp_path, _start(1), _run_row(1, trace_llm={}))
    with pytest.raises(SystemExit, match="missing the fields"):
        probe.load_prior(log)


def test_the_retry_probe_refuses_a_result_that_contradicts_itself(tmp_path):
    """Red-team round 4 P1: `refused` and `refusal_gate` are two statements
    about one decision; reading the gate alone scores a refusal as a recovery."""
    probe = _probe()
    row = {"saw_result": True, "stream_restarts": 1, "refused": True, "refusal_gate": None}
    assert probe.classify(row) == "incoherent_result"
    assert probe.classify({**row, "refused": False, "refusal_gate": "citation"}) == (
        "incoherent_result"
    )


def test_the_retry_probe_withholds_the_ratio_when_the_sample_is_unquotable(tmp_path):
    """Red-team round 4 P1: `recovered 1 of 1` printed beside a warning is the
    line that gets copied into the review."""
    probe = _probe()
    mixed = [
        _settled("retried_recovered"),
        _settled("retried_indeterminate", trace_llm=None, trace_outcome=None, trace_spans=None),
    ]
    report, quotable = probe.tally(mixed)
    assert quotable is False
    assert "recovered 1 of" not in report
    assert "recovery metric withheld" in report


def test_the_retry_probe_locks_the_log_inode_not_just_its_name(tmp_path):
    """Red-team round 5 P0: `resolve()` fixes symlinks, not hard links. Two hard
    links to one log get two different sibling locks."""
    probe = _probe()
    real = tmp_path / "probe.jsonl"
    real.write_text("", encoding="utf-8")
    hard = tmp_path / "probe-hard.jsonl"
    os.link(real, hard)
    held = real.open("a", encoding="utf-8")
    assert probe.take_flock(held) is True
    try:
        via_alias = hard.open("a", encoding="utf-8")
        try:
            assert probe.take_flock(via_alias) is False
        finally:
            via_alias.close()
    finally:
        held.close()


def test_the_retry_probe_refuses_a_result_object_it_cannot_read(tmp_path):
    """Red-team round 5 P1: `.get()` defaults turn a malformed refusal into a
    recovery. An empty-string gate is not a gate."""
    probe = _probe()
    assert (
        probe.malformed_result({"refused": False, "refusal_gate": None, "trace_id": _TID}) is None
    )
    assert "not a boolean" in probe.malformed_result({"refused": None, "trace_id": _TID})
    assert "gate name" in probe.malformed_result(
        {"refused": True, "refusal_gate": "", "trace_id": _TID}
    )
    body = _sse(
        'event: restart\ndata: {"reason": "llm-contract"}\n\n',
        'event: result\ndata: {"trace_id": "20260728T120008-000000a8",'
        ' "refused": true, "refusal_gate": ""}\n\n',
    )
    row = probe.run_once(_client(body), "q")
    assert probe.classify(row) == "non_observation"


def test_the_retry_probe_rejects_a_trace_value_that_is_not_a_reason(tmp_path):
    """Red-team round 5 P1: `disagrees` reads any non-None value as the event
    having happened, so `false` would be affirmative evidence."""
    probe = _probe()
    log = _log(
        tmp_path,
        _start(1),
        _run_row(1, trace_llm={**_SILENT, "recovered_after_contract_failure": False}),
    )
    with pytest.raises(SystemExit, match="neither null nor a reason"):
        probe.load_prior(log)


def test_the_retry_probe_withholds_the_failure_count_it_cannot_stand_behind(tmp_path):
    """Red-team round 5 P2: a retry that died mid-stream did observe an
    attempt-1 failure, so the determinate-only count understates it."""
    probe = _probe()
    report, quotable = probe.tally(
        [
            _settled("retried_recovered"),
            _settled("retried_indeterminate", trace_llm=None, trace_outcome=None, trace_spans=None),
        ]
    )
    assert quotable is False
    assert "attempt-1 contract failures" not in report


def test_the_retry_probe_charges_an_unreadable_run_at_the_worst_case(tmp_path):
    """Red-team round 5 P2: a run whose stream broke may already have funded a
    re-ask, so charging it as one generation understates the spend."""
    probe = _probe()
    log = (tmp_path / "probe.jsonl").open("w", encoding="utf-8")
    rows: list = []
    with log:
        charged = probe.run_session(
            _client("nope", status=500, content_type="application/json"),
            log,
            rows,
            1,
            runs=1,
            budget=4,
        )
    assert charged == 2
    assert rows[0]["outcome"] == "non_observation"


def test_the_retry_probe_rejects_a_blank_gate_on_replay_too(tmp_path):
    """Red-team round 6 P1: replay must apply the rule the live path applies, or
    a blank gate reads as a coherent non-contract refusal and scores recovered."""
    probe = _probe()
    log = _log(
        tmp_path,
        _start(1),
        _run_row(1, stream_restarts=1, refused=True, refusal_gate="", trace_id=_TID),
    )
    with pytest.raises(SystemExit, match="gate name"):
        probe.load_prior(log)


def test_the_retry_probe_accepts_a_run_whose_stream_died_before_any_result(tmp_path):
    """The mirror of the check above: a row with no result object must still
    replay. A validator that rejects the tool's own output breaks every resume."""
    probe = _probe()
    log = _log(
        tmp_path,
        _start(1),
        _run_row(
            1,
            saw_result=False,
            stream_restarts=1,
            refused=None,
            stream_error="connection reset",
            trace_llm=None,
            trace_outcome=None,
            trace_spans=None,
        ),
    )
    rows, _, _ = probe.load_prior(log)
    assert rows[0]["outcome"] == "retried_indeterminate"


def test_the_retry_probe_rejects_a_start_row_with_no_usable_number(tmp_path):
    """Red-team round 6 P2: `1.0` and `True` compare equal to `1` in a set, so
    an untyped start could satisfy the pairing for a run it does not name."""
    probe = _probe()
    log = _log(tmp_path, '{"kind": "start", "run": true}', _run_row(1))
    with pytest.raises(SystemExit, match="start row has no usable run number"):
        probe.load_prior(log)


def test_the_retry_probe_survives_a_frame_whose_payload_is_not_an_object(tmp_path):
    """Red-team round 6 P2: `[]` is valid JSON. Calling `.get()` on it raises
    after the call was paid for and its start line flushed."""
    probe = _probe()
    row = probe.run_once(_client("event: result\ndata: []\n\n"), "q")
    assert probe.classify(row) == "non_observation"
    assert "not an object" in row["transport_note"]


def test_the_retry_probe_tells_a_missing_llm_span_from_a_malformed_one(tmp_path, monkeypatch):
    """Red-team round 6 P1: `or {}` collapsed both into "nothing recorded", so a
    corrupt span passed as a valid second reading."""
    from learnarken.answer import trace as trace_module

    probe = _probe()
    monkeypatch.setattr(trace_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)

    # A gate that refuses before the model is called writes no llm span at all.
    trace_module.write_trace(
        "20260728T120003-000000a3", {"outcome": {"refused": True, "gate": "threshold"}}
    )
    absent = probe.read_back_trace("20260728T120003-000000a3")
    assert absent["trace_note"] is None
    assert absent["trace_llm"] == _SILENT

    # Red-team round 7 P1: but a run that *answered* must have written one, so a
    # trace without it is a hole, not a silent reading.
    trace_module.write_trace(
        "20260728T120006-000000a6", {"outcome": {"refused": False}, "generation": {}}
    )
    answered = probe.read_back_trace("20260728T120006-000000a6")
    assert answered["trace_llm"] is None
    assert "reached the model" in answered["trace_note"]

    trace_module.write_trace("20260728T120004-000000a4", {"llm": ["not", "an", "object"]})
    malformed = probe.read_back_trace("20260728T120004-000000a4")
    assert malformed["trace_llm"] is None
    assert "not an object" in malformed["trace_note"]


def test_the_retry_probe_refuses_an_error_frame_it_cannot_read(tmp_path):
    """Red-team round 7 P2: a non-string message produced a row `run_once` wrote
    and `validate_run_row` then refused — a log the tool could not resume."""
    probe = _probe()
    row = probe.run_once(_client('event: error\ndata: {"message": 123}\n\n'), "q")
    assert probe.classify(row) == "non_observation"
    assert "malformed error frame" in row["transport_note"]


def test_the_retry_probe_can_replay_every_row_it_writes(tmp_path):
    """Red-team round 8 P3: the round-7 bug was "the tool wrote a row its own
    replay refused". Asserting `run_once` returns non_observation does not prove
    that; only a round trip through the log does."""
    probe = _probe()
    bodies = [
        'event: error\ndata: {"message": 123}\n\n',  # malformed error frame
        "event: result\ndata: []\n\n",  # non-object payload
        'event: result\ndata: {"trace_id": "20260728T120008-000000a8",'
        ' "refused": true, "refusal_gate": ""}\n\n',
        'event: token\ndata: {"text": "x"}\n\nevent: error\ndata: {"message": "reset"}\n\n',
        'event: result\ndata: {"trace_id": "20260728T120008-000000a8",'
        ' "refused": false, "refusal_gate": null}\n\n',
    ]
    out = tmp_path / "probe.jsonl"
    with out.open("w", encoding="utf-8") as log:
        log.write(
            json.dumps({"kind": "meta", "version": probe.LOG_VERSION, "queries": _PLAN}) + "\n"
        )
        for i, body in enumerate(bodies, start=1):
            log.write(_start(i) + "\n")
            tag = probe.QUERIES[(i - 1) % len(probe.QUERIES)][0]
            row = {"kind": "run", "run": i, "query": tag, **probe.run_once(_client(body), "q")}
            row["outcome"] = probe.classify(row)
            row["disagreement"] = probe.disagrees(row)
            log.write(json.dumps(row) + "\n")
    rows, unfinished, next_number = probe.load_prior(out)
    assert len(rows) == len(bodies) and unfinished == 0 and next_number == len(bodies) + 1


def test_the_retry_probe_reads_a_missing_llm_span_structurally_not_by_gate_name(
    tmp_path, monkeypatch
):
    """Yi Xin's ruling 5: no hard-coded gate. Whether the model ran is decided
    by the trace's spans, so a gate this build has never heard of classifies
    correctly instead of failing closed."""
    from learnarken.answer import trace as trace_module

    probe = _probe()
    monkeypatch.setattr(trace_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)

    # A gate no build has seen: neither span, so the model was never called.
    trace_module.write_trace(
        "20260728T120005-000000a5", {"outcome": {"refused": True, "gate": "some-future-gate"}}
    )
    unheard = probe.read_back_trace("20260728T120005-000000a5")
    assert unheard["trace_note"] is None
    assert unheard["trace_spans"] == {"llm": False, "generation": False}

    # A `generation` span without `llm` is a trace that reached the model and
    # lost part of its record — still a hole, still refused.
    trace_module.write_trace(
        "20260728T120013-000000b3",
        {"generation": {}, "outcome": {"refused": True, "gate": "citation-validation"}},
    )
    holed = probe.read_back_trace("20260728T120013-000000b3")
    assert holed["trace_llm"] is None
    assert "reached the model" in holed["trace_note"]


def test_the_retry_probe_catches_a_trace_that_decided_differently(tmp_path, monkeypatch):
    """Red-team round 9 P2: a threshold refusal writes a legitimately silent llm
    span, so span-only agreement said nothing about what the run decided."""
    from learnarken.answer import trace as trace_module

    probe = _probe()
    monkeypatch.setattr(trace_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)
    trace_module.write_trace(
        "20260728T120002-000000a2",
        {
            "question": "What safety precautions apply before removing the hydraulic pump?",
            "outcome": {"refused": True, "gate": "threshold"},
        },
    )

    reading = probe.read_back_trace("20260728T120002-000000a2")
    assert reading["trace_llm"] == _SILENT  # the span itself is silent, and legitimately so
    assert reading["trace_spans"] == {"llm": False, "generation": False}

    def row(**stream):
        r = {"saw_result": True, "stream_restarts": 0, "token_events": 0, **stream, **reading}
        r["outcome"] = probe.classify(r)
        return r

    # A stream that says the run answered contradicts a trace that says it refused.
    answered = row(refused=False, refusal_gate=None)
    assert answered["outcome"] == "clean"
    assert probe.disagrees(answered) is True
    # And the gate must match too, not merely the boolean.
    elsewhere = row(refused=True, refusal_gate="citation")
    assert probe.disagrees(elsewhere) is True
    # The one that agrees: the stream also says threshold, so it never generated.
    agreeing = row(refused=True, refusal_gate="threshold")
    assert agreeing["outcome"] == "no_generation"
    assert probe.disagrees(agreeing) is False


def test_the_retry_probe_charges_an_unreadable_run_for_the_restarts_it_saw(tmp_path):
    """Red-team round 9 P3: two restarts then a broken frame is three
    generations, and a flat worst-case-of-2 would undercount it."""
    probe = _probe()
    body = _sse(
        'event: restart\ndata: {"reason": "llm-contract"}\n\n',
        'event: restart\ndata: {"reason": "llm-contract"}\n\n',
        'event: result\ndata: {"trace_id": "20260728T120008-000000a8"\n\n',
    )
    log = (tmp_path / "probe.jsonl").open("w", encoding="utf-8")
    rows: list = []
    with log:
        charged = probe.run_session(_client(body), log, rows, 1, runs=1, budget=10)
    assert charged == 3


@pytest.mark.parametrize(
    ("spans", "stream"),
    [
        # threshold: refuses before the model, so the llm span is legitimately absent
        (
            {"outcome": {"refused": True, "gate": "threshold"}},
            {"refused": True, "refusal_gate": "threshold"},
        ),
        # the model said it could not answer — llm span present, no contract event
        (
            {"llm": {"model": "m"}, "generation": {}, "outcome": {"refused": True, "gate": "llm"}},
            {"refused": True, "refusal_gate": "llm"},
        ),
        # re-ask recovered, then a later gate refused anyway
        (
            {
                "llm": {"recovered_after_contract_failure": "keys=[...]"},
                "generation": {},
                "outcome": {"refused": True, "gate": "citation-validation"},
            },
            {"refused": True, "refusal_gate": "citation-validation", "stream_restarts": 1},
        ),
        # re-ask recovered and the run answered
        (
            {
                "llm": {"recovered_after_contract_failure": "keys=[...]"},
                "generation": {},
                "outcome": {"refused": False},
            },
            {"refused": False, "refusal_gate": None, "stream_restarts": 1},
        ),
        # answered on the first attempt, no re-ask
        (
            {"llm": {"model": "m"}, "generation": {}, "outcome": {"refused": False}},
            {"refused": False, "refusal_gate": None},
        ),
        # truncation: a contract failure the engine does not re-ask
        (
            {
                "llm": {"contract_error": "finish_reason=length"},
                "outcome": {"refused": True, "gate": "llm-contract"},
            },
            {"refused": True, "refusal_gate": "llm-contract"},
        ),
        # a figure refusal, which happens after generation
        (
            {
                "llm": {"model": "m"},
                "generation": {},
                "outcome": {"refused": True, "gate": "figure-out-of-description"},
            },
            {"refused": True, "refusal_gate": "figure-out-of-description"},
        ),
        # re-ask fired and failed again
        (
            {
                "llm": {"contract_error": "keys=[...]", "first_attempt_error": "keys=[...]"},
                "outcome": {"refused": True, "gate": "llm-contract"},
            },
            {"refused": True, "refusal_gate": "llm-contract", "stream_restarts": 1},
        ),
    ],
)
def test_the_retry_probe_does_not_false_alarm_on_a_real_outcome(
    spans, stream, tmp_path, monkeypatch
):
    """A cross-check that flags legitimate runs makes every real session
    unquotable, which fails just as badly as one that flags nothing. Each case
    is a shape the engine actually writes."""
    from learnarken.answer import trace as trace_module

    probe = _probe()
    monkeypatch.setattr(trace_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)
    asked = "what this run actually asked"
    trace_module.write_trace("20260728T120008-000000a8", {"question": asked, **spans})

    reading = probe.read_back_trace("20260728T120008-000000a8", asked)
    # Bound to the question, so this matrix also proves the binding does not
    # false-alarm on a legitimate trace (red-team 2026-07-28 P3).
    assert reading["trace_note"] is None
    row = {"saw_result": True, "stream_restarts": 0, **stream, **reading}
    row["outcome"] = probe.classify(row)
    assert row["outcome"] not in probe.INDETERMINATE
    assert probe.disagrees(row) is False, f"false alarm on {row['outcome']}"


def test_the_retry_probe_does_not_count_a_run_that_never_reached_the_model():
    """Yi Xin's 2026-07-28 run: a third of the sample was a query the retrieval
    threshold refuses, so it could not have produced a contract failure however
    the model behaved — yet it counted as `clean` and inflated the denominator."""
    probe = _probe()
    row = {
        "saw_result": True,
        "stream_restarts": 0,
        "token_events": 0,
        "refused": True,
        "refusal_gate": "threshold",
        "trace_spans": dict(_NO_MODEL),
    }
    assert probe.classify(row) == "no_generation"
    # The model having run is what makes it a generation — not the gate's name.
    assert probe.classify({**row, "trace_spans": dict(_RAN)}) == "clean"
    # And with no second reading there is nothing to establish it, so the run
    # stays in the denominator rather than being excused out of it.
    assert probe.classify({**row, "trace_spans": None}) == "clean"


def test_the_retry_probe_reports_generations_apart_from_runs():
    """`runs=24` when 8 of them never called the model states a sample larger
    than the one that exists."""
    probe = _probe()
    rows = [_settled("no_generation") for _ in range(8)]
    rows += [_settled("clean") for _ in range(16)]
    report, quotable = probe.tally(rows)
    assert "runs=24  reached the model=16  refused before it=8" in report
    assert "could not have produced a contract failure" in report
    assert quotable is False  # still no denominator for recovery


def _threshold_body(trace_id: str = "20260728T120002-000000a2") -> str:
    return _sse(
        f'event: result\ndata: {{"trace_id": "{trace_id}", "refused": true, '
        '"refusal_gate": "threshold"}\n\n'
    )


def test_the_retry_probe_does_not_charge_for_a_generation_the_trace_says_never_happened(
    tmp_path, monkeypatch
):
    """The threshold gate refuses before the model is called, so nothing was
    billed. Charging one would overstate the spend while understating the
    sample — the same error in both directions at once. The stream's word alone
    is not enough: the trace must show no model span (red-team 2026-07-28 P1)."""
    from learnarken.answer import trace as trace_module

    probe = _probe()
    monkeypatch.setattr(trace_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)
    trace_module.write_trace(
        "20260728T120002-000000a2",
        {
            "question": "What safety precautions apply before removing the hydraulic pump?",
            "outcome": {"refused": True, "gate": "threshold"},
        },
    )

    rows: list = []
    with (tmp_path / "probe.jsonl").open("w", encoding="utf-8") as log:
        charged = probe.run_session(_client(_threshold_body()), log, rows, 1, runs=1, budget=4)
    assert rows[0]["outcome"] == "no_generation"
    assert rows[0]["disagreement"] is False
    assert charged == 0


def test_the_retry_probe_bills_a_run_whose_trace_shows_the_model_ran(tmp_path, monkeypatch):
    """If the trace records an llm span the run reached the model, whatever the
    gate says — so it is a generation, it is billed, and it is not excused out
    of the denominator."""
    from learnarken.answer import trace as trace_module

    probe = _probe()
    monkeypatch.setattr(trace_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)
    trace_module.write_trace(
        "20260728T120002-000000a2",
        {
            "question": "What safety precautions apply before removing the hydraulic pump?",
            "llm": {"model": "m"},
            "generation": {},
            "outcome": {"refused": True, "gate": "threshold"},
        },
    )

    rows: list = []
    with (tmp_path / "probe.jsonl").open("w", encoding="utf-8") as log:
        charged = probe.run_session(_client(_threshold_body()), log, rows, 1, runs=1, budget=4)
    # The trace proves the model ran, so this is a generation and is billed —
    # whatever the gate is called. Under the old gate-name rule this pair was a
    # contradiction; under ruling 5 the span is the authority and the gate name
    # is not consulted at all.
    assert rows[0]["outcome"] == "clean"
    assert rows[0]["disagreement"] is False
    assert charged == 1


def test_the_retry_probe_will_not_call_a_streamed_answer_a_no_generation(tmp_path):
    """Text on screen means the model ran, whatever gate the result names."""
    probe = _probe()
    row = {
        "saw_result": True,
        "stream_restarts": 0,
        "refused": True,
        "refusal_gate": "threshold",
        "token_events": 3,
    }
    assert probe.classify(row) == "clean"


def test_the_retry_probe_refuses_to_resume_a_log_sampled_from_another_query_mix(tmp_path):
    """The sampling plan is part of the measurement; pooling two plans under one
    number is the same error as pooling two corpora (ADR-0004's lesson)."""
    probe = _probe()
    log = tmp_path / "probe.jsonl"
    log.write_text(
        json.dumps({"kind": "meta", "version": probe.LOG_VERSION, "queries": [_PLAN[0]]}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="Start a fresh --out rather than mixing plans"):
        probe.load_prior(log)


def test_the_retry_probe_no_longer_spends_on_a_query_that_cannot_contribute():
    """The demo's coffee-maker question was removed from the mix: 8 of 8 of its
    runs were refused before generation."""
    probe = _probe()
    assert all("coffee" not in question.lower() for _, question in probe.QUERIES)
    assert [tag for tag, _ in probe.QUERIES] == ["answer", "retraction"]


def test_the_retry_probe_rejects_a_row_with_no_token_count(tmp_path):
    """Red-team 2026-07-28 P1: `no_generation` turns on "the stream showed no
    text", so an absent count would let replay read missing evidence as proof."""
    probe = _probe()
    row = json.loads(_run_row(1))
    del row["token_events"]
    log = _log(tmp_path, _start(1), json.dumps(row))
    with pytest.raises(SystemExit, match="missing token_events"):
        probe.load_prior(log)


def test_the_retry_probe_rejects_a_log_that_records_no_sampling_plan(tmp_path):
    """A `/8` log with no `queries` is a plan nobody wrote down; accepting it
    would let the guard be bypassed by omission."""
    probe = _probe()
    log = tmp_path / "probe.jsonl"
    log.write_text(
        json.dumps({"kind": "meta", "version": probe.LOG_VERSION}) + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="mixing plans"):
        probe.load_prior(log)


def test_the_retry_probe_rejects_a_reworded_question_under_the_same_tag(tmp_path):
    """The same tag over a different prompt is a different sample."""
    probe = _probe()
    reworded = [[_PLAN[0][0], "a different question entirely"], _PLAN[1]]
    log = tmp_path / "probe.jsonl"
    log.write_text(
        json.dumps({"kind": "meta", "version": probe.LOG_VERSION, "queries": reworded}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="mixing plans"):
        probe.load_prior(log)


def test_the_retry_probe_does_not_claim_an_unreadable_run_reached_the_model(tmp_path):
    """Red-team 2026-07-28 P2: an indeterminate run may or may not have called
    the model, and `runs - no_generation` quietly asserted that it did."""
    probe = _probe()
    rows = [_settled("clean") for _ in range(2)]
    rows += [
        _settled("non_observation", trace_llm=None, trace_outcome=None, trace_spans=None)
        for _ in range(3)
    ]
    rows += [_settled("no_generation")]
    report, quotable = probe.tally(rows)
    assert "runs=6  reached the model=2  refused before it=1  unknown=3" in report
    assert quotable is False


def test_the_retry_probe_flags_a_clean_run_whose_trace_shows_no_model_span(tmp_path, monkeypatch):
    """Red-team 2026-07-28 P1: a stray `token` frame before a threshold refusal
    made the run `clean`, and a trace showing no model span agreed with it.
    Every determinate outcome except `no_generation` asserts the model ran."""
    from learnarken.answer import trace as trace_module

    probe = _probe()
    monkeypatch.setattr(trace_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)
    trace_module.write_trace(
        "20260728T120002-000000a2",
        {
            "question": "What safety precautions apply before removing the hydraulic pump?",
            "outcome": {"refused": True, "gate": "threshold"},
        },
    )

    row = {
        "saw_result": True,
        "stream_restarts": 0,
        "token_events": 1,  # a token arrived, so this is not a no_generation run
        "refused": True,
        "refusal_gate": "threshold",
        **probe.read_back_trace("20260728T120002-000000a2"),
    }
    row["outcome"] = probe.classify(row)
    assert row["outcome"] == "clean"
    assert probe.disagrees(row) is True


def test_the_retry_probe_charges_a_retry_the_stream_missed_but_the_trace_recorded(
    tmp_path, monkeypatch
):
    """Red-team 2026-07-28 P2: the spend trusted the stream's restart count, so
    a dropped `restart` frame bought a free generation."""
    from learnarken.answer import trace as trace_module

    probe = _probe()
    monkeypatch.setattr(trace_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)
    trace_module.write_trace(
        "20260728T120008-000000a8",
        {
            "question": "What safety precautions apply before removing the hydraulic pump?",
            "llm": {"recovered_after_contract_failure": "keys=[...]"},
            "generation": {},
            "outcome": {"refused": False},
        },
    )
    body = _sse(
        'event: result\ndata: {"trace_id": "20260728T120008-000000a8",'
        ' "refused": false, "refusal_gate": null}\n\n'
    )
    rows: list = []
    with (tmp_path / "probe.jsonl").open("w", encoding="utf-8") as log:
        charged = probe.run_session(_client(body), log, rows, 1, runs=1, budget=4)
    assert rows[0]["stream_restarts"] == 0  # the stream saw no restart
    assert charged == 2  # ...but the trace proves two generations were spent
    # And the two readings disagreeing is itself a blocker.
    assert rows[0]["disagreement"] is True


def test_the_retry_probe_will_not_follow_a_trace_id_into_a_path(tmp_path, monkeypatch):
    """Red-team 2026-07-28 P2: the id becomes a filename, so a path-like value
    would let a result point the second reading at an unrelated trace and
    collect it as corroboration for a run it says nothing about."""
    probe = _probe()
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)
    for hostile in ("../../etc/passwd", "/tmp/fake", "T", "", "20260728T120000-nothex!"):
        assert probe.read_back_trace(hostile)["trace_llm"] is None
        assert "trace id" in probe.read_back_trace(hostile)["trace_note"]
    assert "could have produced" in probe.malformed_result(
        {"refused": False, "refusal_gate": None, "trace_id": "/tmp/fake"}
    )


def test_the_retry_probe_will_not_accept_another_runs_trace_as_this_ones(tmp_path, monkeypatch):
    """A trace whose own id is not the one the result named is a different
    run's evidence wearing this run's name."""
    from learnarken.answer import trace as trace_module

    probe = _probe()
    monkeypatch.setattr(trace_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)
    # Write a valid trace, then rename the file so it answers to another id.
    trace_module.write_trace("20260728T120010-000000b0", {"outcome": {"refused": False}})
    (tmp_path / "20260728T120010-000000b0.json").rename(tmp_path / "20260728T120011-000000b1.json")

    reading = probe.read_back_trace("20260728T120011-000000b1")
    assert reading["trace_llm"] is None
    assert "the result named" in reading["trace_note"]


def test_the_retry_probe_will_not_take_a_stale_trace_for_another_question(tmp_path, monkeypatch):
    """Red-team 2026-07-28 P1: an id match alone let a *stale* trace for a
    different question — one that happens to record a recovered re-ask — be
    collected as this run's corroboration."""
    from learnarken.answer import trace as trace_module

    probe = _probe()
    monkeypatch.setattr(trace_module, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(probe, "TRACE_DIR", tmp_path)
    trace_module.write_trace(
        "20260728T120012-000000b2",
        {
            "question": "an entirely different question",
            "llm": {"recovered_after_contract_failure": "keys=[...]"},
            "generation": {},
            "outcome": {"refused": False},
        },
    )
    reading = probe.read_back_trace("20260728T120012-000000b2", "the question this run asked")
    assert reading["trace_llm"] is None
    assert "different question" in reading["trace_note"]
    # The same trace is a valid reading for the run that did ask it.
    ok = probe.read_back_trace("20260728T120012-000000b2", "an entirely different question")
    assert ok["trace_llm"]["recovered_after_contract_failure"] == "keys=[...]"


def test_the_retry_probe_charges_the_worst_case_for_a_stream_that_just_stopped(tmp_path):
    """Red-team 2026-07-28 P2: an SSE body that ends with no `result` and no
    `error` carries no transport note, so it charged one — while the call may
    already have funded a re-ask."""
    probe = _probe()
    rows: list = []
    with (tmp_path / "probe.jsonl").open("w", encoding="utf-8") as log:
        charged = probe.run_session(
            _client("event: status\ndata: {}\n\n"), log, rows, 1, runs=1, budget=4
        )
    assert rows[0]["outcome"] == "transport_error"
    assert rows[0].get("transport_note") is None
    assert charged == 2
