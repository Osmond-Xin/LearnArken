"""Day 3 chunking tests: structure/recursive strategies, metadata, storage sanity."""

from pathlib import Path

import pytest

from learnarken.chunking import PartialPackageError, chunk_package
from learnarken.chunking.base import Chunk, _values_match, applies_to
from learnarken.package import NotAPackageError

SAMPLES = Path(__file__).parent.parent / "samples"
PUMP_REMOVE = "DMC-LA100-A-29-10-00-00A-520A-A"


class TestStructureChunking:
    def test_pump_remove_boundaries(self):
        chunks = [c for c in chunk_package(SAMPLES / "package-a") if c.dmc == PUMP_REMOVE]
        types = [c.chunk_type for c in chunks]
        # preconditions (reqCondGroup + reqSupportEquips), one reqSafety warning,
        # three procedural steps, one closeout — no procedural content dropped
        assert types == [
            "precondition",
            "precondition",
            "warning",
            "step",
            "step",
            "step",
            "closeout",
        ]

    def test_hazard_flags_follow_content(self):
        chunks = {
            c.source_path: c for c in chunk_package(SAMPLES / "package-a") if c.dmc == PUMP_REMOVE
        }
        warning = next(c for c in chunks.values() if c.chunk_type == "warning")
        assert warning.has_warning is True
        # step[2] embeds a residual-pressure warning; step[1] does not
        step2 = chunks["/dmodule/content/procedure/mainProcedure/proceduralStep[2]"]
        step1 = chunks["/dmodule/content/procedure/mainProcedure/proceduralStep[1]"]
        assert step2.has_warning is True
        assert step1.has_warning is False

    def test_fault_description_is_chunked(self):
        chunks = [
            c
            for c in chunk_package(SAMPLES / "package-a")
            if c.dmc == "DMC-LA100-A-29-10-00-00A-421A-A"
        ]
        symptom = next((c for c in chunks if "below 2400 psi" in c.text), None)
        assert symptom is not None and symptom.chunk_type == "fault"

    def test_graph_hooks_populated(self):
        chunks = [c for c in chunk_package(SAMPLES / "package-a") if c.dmc == PUMP_REMOVE]
        step3 = next(c for c in chunks if c.source_path.endswith("proceduralStep[3]"))
        assert step3.outbound_dm_refs == ["DMC-LA100-A-29-10-00-00A-941A-D"]

    def test_ipd_folds_in_part_numbers(self):
        ipd = next(c for c in chunk_package(SAMPLES / "package-a") if c.chunk_type == "ipd")
        assert "LA-29-4711-1" in ipd.text  # attribute value folded into searchable text

    def test_applicability_inherited(self):
        chunks = chunk_package(SAMPLES / "package-c")
        damper = next(c for c in chunks if c.dmc == "DMC-LA100-A-32-20-00-00A-040A-D")
        assert damper.applicability is not None
        assert any(a.property_ident == "variant" for a in damper.applicability.assertions)


class TestRecursiveWindows:
    # Day 4a (D13): the splitter is LangChain's RecursiveCharacterTextSplitter;
    # the red-team R4 termination/param concerns of the retired hand-rolled
    # _windows now live in the framework. What remains OURS to verify is the
    # configuration contract: bounded window size and forward progress.
    def test_windows_bounded_and_terminating(self):
        from learnarken.chunking.recursive import _SPLITTER, WINDOW

        wins = _SPLITTER.split_text(("word " * 400).strip())
        assert 0 < len(wins) < 10_000
        assert all(len(w) <= WINDOW for w in wins)

    def test_overlap_smaller_than_window(self):
        from learnarken.chunking.recursive import OVERLAP, WINDOW

        assert 0 <= OVERLAP < WINDOW


class TestRecursiveChunking:
    def test_windows_produced_with_dm_metadata(self):
        chunks = [
            c
            for c in chunk_package(SAMPLES / "package-a", strategy="recursive")
            if c.dmc == PUMP_REMOVE
        ]
        assert chunks and all(c.chunk_type == "recursive" for c in chunks)
        assert all(c.source_path.startswith(f"/dmodule[{PUMP_REMOVE}]#win") for c in chunks)
        assert all(c.has_warning for c in chunks)  # DM-level aggregate flag


class TestStorageSanity:
    def test_chunk_id_deterministic_across_runs(self):
        a = {c.chunk_id for c in chunk_package(SAMPLES / "package-a")}
        b = {c.chunk_id for c in chunk_package(SAMPLES / "package-a")}
        assert a == b
        assert len(a) == len(chunk_package(SAMPLES / "package-a"))  # ids unique

    def test_metadata_round_trips_lossless(self):
        for c in chunk_package(SAMPLES / "package-c"):
            assert Chunk.model_validate(c.model_dump()) == c

    def test_count_reconciliation_no_content_dropped(self):
        # every procedural step in the pump-remove DM yields exactly one step chunk
        steps = [
            c
            for c in chunk_package(SAMPLES / "package-a")
            if c.dmc == PUMP_REMOVE and c.chunk_type == "step"
        ]
        assert len(steps) == 3

    def test_not_a_package_raises(self, tmp_path):
        with pytest.raises(NotAPackageError):
            chunk_package(tmp_path)


class TestFailClosed:
    def _pkg_with_bad_file(self, tmp_path):
        (tmp_path / "DMC-LA100-A-99-99-99-99A-040A-D_EN-CA.xml").write_text(
            "<dmodule><unclosed>", encoding="utf-8"
        )
        return tmp_path

    def test_unparseable_module_refused_by_default(self, tmp_path):
        with pytest.raises(PartialPackageError):
            chunk_package(self._pkg_with_bad_file(tmp_path))

    def test_skip_bad_opts_into_partial_index(self, tmp_path):
        # only a broken file present -> skip_bad yields an empty (not crashing) index
        assert chunk_package(self._pkg_with_bad_file(tmp_path), skip_bad=True) == []


class TestExclusionFilter:
    def _damper(self, chunks):
        return next(c for c in chunks if c.dmc == "DMC-LA100-A-32-20-00-00A-040A-D")

    def test_variant_b_chunk_kept_for_b_excluded_for_a(self):
        damper = self._damper(chunk_package(SAMPLES / "package-c"))
        assert applies_to(damper, {"variant": "B"}) is True
        assert applies_to(damper, {"variant": "A"}) is False

    def test_absent_property_is_applicable(self):
        damper = self._damper(chunk_package(SAMPLES / "package-c"))
        assert applies_to(damper, {"serialNumber": "0001"}) is True  # no assertion on this property


class TestValueMatching:
    def test_numeric_range_matches_inside(self):
        assert _values_match("0032", "0001~0050") is True
        assert _values_match("0051", "0001~0050") is False

    def test_lexical_range_no_longer_false_matches(self):
        # red-team #5: "A2" must not match inside "A10~A20" via string comparison
        assert _values_match("A2", "A10~A20") is False

    def test_comma_list_exact(self):
        assert _values_match("B", "A,B,C") is True
        assert _values_match("D", "A,B,C") is False
