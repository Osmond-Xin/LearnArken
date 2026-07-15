"""Day 3 chunking tests: structure/recursive strategies, metadata, storage sanity."""

from pathlib import Path

import pytest

from learnarken.chunking import chunk_package
from learnarken.chunking.base import Chunk, applies_to
from learnarken.package import NotAPackageError

SAMPLES = Path(__file__).parent.parent / "samples"
PUMP_REMOVE = "DMC-LA100-A-29-10-00-00A-520A-A"


class TestStructureChunking:
    def test_pump_remove_boundaries(self):
        chunks = [c for c in chunk_package(SAMPLES / "package-a") if c.dmc == PUMP_REMOVE]
        types = [c.chunk_type for c in chunks]
        # one reqSafety warning + three procedural steps
        assert types == ["warning", "step", "step", "step"]

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
