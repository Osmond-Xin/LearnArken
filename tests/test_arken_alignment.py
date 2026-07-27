"""Arken pillar alignment — Phase 1 (docs/specs/arken-alignment-2026-07-26.md).

Acceptance criteria quote the pinned source snapshot
(docs/research/arken-source-snapshot-2026-07-26.md), not a paraphrase, per
red-team finding F-05.
"""

from __future__ import annotations

import json
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
