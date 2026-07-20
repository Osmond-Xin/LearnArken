"""Day 11 entity linker: deterministic, lexicon-gated, no LLM (spec §1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from learnarken.chunking import chunk_package
from learnarken.retrieval.entity_link import build_lexicon, link_entities

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGES = [REPO_ROOT / "samples" / "package-a", REPO_ROOT / "samples" / "package-c"]


@pytest.fixture(scope="module")
def lexicon():
    chunks = []
    for pkg in PACKAGES:
        chunks.extend(chunk_package(pkg))
    return build_lexicon(chunks)


def test_lexicon_from_corpus(lexicon) -> None:
    assert "DMC-LA100-A-29-10-00-00A-520A-A" in lexicon.dmcs
    # Parts harvested from IPD chunk text only (where partNumberValue is folded in).
    assert set(lexicon.parts) == {"LA-29-0025-4", "LA-29-4711-1", "LA-29-4711-9"}
    assert lexicon.parts["LA-29-4711-9"] == ("DMC-LA100-A-29-10-00-00A-941A-D",)
    # Title phrases with ≥2 tokens; a bare "description" must never be linkable.
    assert "main battery" in lexicon.tasks
    assert "fault isolation" in lexicon.tasks
    assert "description" not in lexicon.tasks


def test_full_dmc_links_exactly(lexicon) -> None:
    (entity,) = link_entities("show DMC-LA100-A-29-10-00-00A-520A-A steps", lexicon)
    assert entity.kind == "dmc"
    assert entity.dmcs == ("DMC-LA100-A-29-10-00-00A-520A-A",)


def test_bare_dmc_suffix_links_and_is_case_insensitive(lexicon) -> None:
    entities = link_entities("fault tree for 29-10-00-00a-421a-a please", lexicon)
    assert ("DMC-LA100-A-29-10-00-00A-421A-A",) in [e.dmcs for e in entities if e.kind == "dmc"]


def test_unknown_codes_link_nothing(lexicon) -> None:
    """Fail closed (INV-4): syntactically valid but out-of-corpus → no entity."""
    assert link_entities("what is DMC-ZZ999-X-11-22-33-44B-555C-Z", lexicon) == []
    assert link_entities("torque for part LA-99-9999-9", lexicon) == []
    assert link_entities("check 99-99-99-99Z-999Z-Z now", lexicon) == []


def test_part_number_needs_lexicon_membership(lexicon) -> None:
    (entity,) = link_entities("order LA-29-4711-1 for the pump", lexicon)
    assert (entity.kind, entity.dmcs) == ("part", ("DMC-LA100-A-29-10-00-00A-941A-D",))
    # Part-shaped free text that is not a corpus part number links nothing.
    assert link_entities("see section A-1-2 of the intro", lexicon) == []


def test_task_phrase_links_all_carrying_dms(lexicon) -> None:
    (entity,) = link_entities("hydraulic pump maintenance overview", lexicon)
    assert entity.kind == "task"
    assert entity.dmcs == (
        "DMC-LA100-A-29-10-00-00A-520A-A",
        "DMC-LA100-A-29-10-00-00A-720A-A",
        "DMC-LA100-A-29-10-00-00A-941A-D",
    )


def test_longest_task_phrase_wins(lexicon) -> None:
    """'nose gear steering damper' must not additionally link a shorter
    contained phrase for the same span."""
    entities = link_entities("calibrate the nose gear steering damper", lexicon)
    assert [e.surface for e in entities] == ["nose gear steering damper"]


def test_no_entities_no_output(lexicon) -> None:
    assert link_entities("what is the meaning of life", lexicon) == []


def test_linking_is_deterministic(lexicon) -> None:
    query = "fault isolation for 29-10-00-00A-421A-A with LA-29-0025-4"
    first = [e.model_dump() for e in link_entities(query, lexicon)]
    second = [e.model_dump() for e in link_entities(query, lexicon)]
    assert first == second and first  # identical, and non-empty


def test_linking_path_imports_no_llm() -> None:
    """Spec acceptance 1: zero LLM involvement on the linking/expansion path."""
    for module in ("entity_link.py", "graph_expand.py"):
        source = (REPO_ROOT / "src" / "learnarken" / "retrieval" / module).read_text(
            encoding="utf-8"
        )
        assert "learnarken.llm" not in source
        assert "minimax" not in source.lower()
