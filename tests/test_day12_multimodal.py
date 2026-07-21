"""Day 12 multimodal ingest & second-look (docs/specs/day12.md).

No live VLM in CI: `vlm._one_call` is monkeypatched, and ingest/second-look take
an injectable `describe`. Determinism, fail-closed, and the mechanical
hotspot-diff are all asserted with mocks reproducing the channel's instability.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from lxml import etree

from learnarken.loader import load_data_module, load_package
from learnarken.multimodal import figures as figs
from learnarken.multimodal import ingest, vlm
from learnarken.multimodal.second_look import (
    FigureRefusal,
    consensus_read,
)
from learnarken.multimodal.vlm import (
    FigureDescription,
    Hotspot,
    Part,
    VLMError,
    VLMRateLimited,
    VLMUnavailable,
    describe_figure,
)

REPO = Path(__file__).resolve().parent.parent
PUMP_DM = REPO / "samples" / "package-a" / "DMC-LA100-A-29-10-00-00A-941A-D_EN-CA.xml"
PUMP_PKG = REPO / "samples" / "package-a"
PUMP_ICN = "ICN-LA100-29-001-01"
PUMP_HOTSPOTS = {"01", "02", "03"}
PUMP_PARTS = ["LA-29-4711-1", "LA-29-4711-9", "LA-29-0025-4"]


def _desc(
    hotspots=("01", "02", "03"), parts=PUMP_PARTS, summary="pump", warnings=("W",), refused=False
):
    return FigureDescription(
        summary=summary,
        parts=[Part(part_number=p, name="") for p in parts],
        hotspots=[Hotspot(id=h, label="") for h in hotspots],
        safety_warnings=list(warnings),
        reads_text=list(parts),
        refused=refused,
    )


# --- figures.py ---------------------------------------------------------------


def test_png_deterministic_within_process() -> None:
    spec = figs.FIGURES[PUMP_ICN]
    assert figs.to_png(spec) == figs.to_png(spec)


def test_declared_hotspots_and_whitelist() -> None:
    spec = figs.FIGURES[PUMP_ICN]
    assert figs.declared_hotspots(spec) == PUMP_HOTSPOTS
    assert set(PUMP_PARTS) <= figs.text_whitelist(spec)


def test_svg_carries_hotspot_ids() -> None:
    svg = figs.to_svg(figs.FIGURES[PUMP_ICN])
    for hid in PUMP_HOTSPOTS:
        assert f">{hid}</text>" in svg


def test_figures_match_dm_declared_set() -> None:
    """Drift guard: the render spec and the DM XML canonical set must agree."""
    package = load_package(PUMP_PKG)
    dm = next(d for d in package.data_modules if d.dmc.endswith("941A-D"))
    xml_set = {h.hotspot_id for h in dm.hotspots if h.icn_ident == PUMP_ICN}
    assert xml_set == figs.declared_hotspots(figs.FIGURES[PUMP_ICN])


# --- vlm.py fail-closed contract ---------------------------------------------


def _mock_one_call(content: str):
    return lambda payload, timeout: vlm._RawCall(content=content, usage={}, model="m")


def test_vlm_valid_json_parses(monkeypatch) -> None:
    monkeypatch.setattr(vlm, "_one_call", _mock_one_call('{"hotspots":[{"id":"01"}]}'))
    out = describe_figure(b"png", {"01"})
    assert out.hotspot_ids() == {"01"}


def test_vlm_empty_retries_then_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(vlm, "_one_call", _mock_one_call(""))
    monkeypatch.setattr(vlm.time, "sleep", lambda *_: None)
    with pytest.raises(VLMUnavailable):
        describe_figure(b"png", {"01"}, max_retries=3)


def test_vlm_no_image_prose_is_flaky(monkeypatch) -> None:
    monkeypatch.setattr(vlm, "_one_call", _mock_one_call("I don't see an image attached"))
    monkeypatch.setattr(vlm.time, "sleep", lambda *_: None)
    with pytest.raises(VLMUnavailable):
        describe_figure(b"png", {"01"}, max_retries=2)


def test_vlm_valid_json_mentioning_no_image_is_kept(monkeypatch) -> None:
    """Host red-team H1: a real description whose summary says 'no image of the
    interior' must NOT be discarded as a flaky miss."""
    monkeypatch.setattr(
        vlm,
        "_one_call",
        _mock_one_call('{"summary":"there is no image of the interior","hotspots":[{"id":"02"}]}'),
    )
    out = describe_figure(b"png", {"02"})
    assert out.hotspot_ids() == {"02"}


def test_vlm_429_is_terminal(monkeypatch) -> None:
    def boom(payload, timeout):
        raise VLMRateLimited("429")

    monkeypatch.setattr(vlm, "_one_call", boom)
    with pytest.raises(VLMRateLimited):
        describe_figure(b"png", {"01"}, max_retries=3)


def test_vlm_returns_raw_hotspots_for_diff(monkeypatch) -> None:
    """Client does NOT filter invented ids — ingest needs the raw set to diff."""
    monkeypatch.setattr(vlm, "_one_call", _mock_one_call('{"hotspots":[{"id":"01"},{"id":"99"}]}'))
    out = describe_figure(b"png", {"01"})
    assert out.hotspot_ids() == {"01", "99"}


# --- ingest.py describe-then-index -------------------------------------------


@pytest.fixture(scope="module")
def pump_dm():
    root = etree.parse(str(PUMP_DM)).getroot()
    return load_data_module(PUMP_DM, root)


def test_ingest_verified_figure_indexed(pump_dm) -> None:
    recs = ingest.describe_dm_figures(
        pump_dm, PUMP_PKG, describe=lambda *a, **k: _desc(), repo_root=REPO
    )
    assert len(recs) == 1 and recs[0].verified
    chunks = ingest.figure_chunks(pump_dm, recs, "structure", PUMP_PKG, repo_root=REPO)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "figure"
    assert chunks[0].icn_refs == [PUMP_ICN]
    assert "Hotspot 02" in chunks[0].text


def test_ingest_hotspot_mismatch_degrades(pump_dm) -> None:
    """A read missing a declared hotspot => mechanical conflict => withheld."""
    recs = ingest.describe_dm_figures(
        pump_dm, PUMP_PKG, describe=lambda *a, **k: _desc(hotspots=("01", "02")), repo_root=REPO
    )
    assert not recs[0].verified and "mismatch" in recs[0].degraded_reason
    assert ingest.figure_chunks(pump_dm, recs, "structure", PUMP_PKG, repo_root=REPO) == []


def test_ingest_uncorroborated_degrades(pump_dm) -> None:
    """Hotspots match but a declared part number never appears in the read."""
    recs = ingest.describe_dm_figures(
        pump_dm, PUMP_PKG, describe=lambda *a, **k: _desc(parts=[], summary="pump"), repo_root=REPO
    )
    assert not recs[0].verified and "corroborat" in recs[0].degraded_reason


def test_ingest_sha256_binds_committed_png(pump_dm) -> None:
    png = (PUMP_PKG / "icn" / f"{PUMP_ICN}.png").read_bytes()
    recs = ingest.describe_dm_figures(
        pump_dm, PUMP_PKG, describe=lambda *a, **k: _desc(), repo_root=REPO
    )
    assert recs[0].sha256 == hashlib.sha256(png).hexdigest()


# --- second_look.py consensus ------------------------------------------------


class _Scripted:
    """Yields successive scripted reads / exceptions to model the flaky channel."""

    def __init__(self, script):
        self.script = list(script)
        self.i = 0

    def __call__(self, *a, **k):
        item = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        if isinstance(item, Exception):
            raise item
        return item


def test_consensus_agrees_and_returns() -> None:
    describe = _Scripted([_desc(), _desc()])
    cr = consensus_read(
        b"png", PUMP_HOTSPOTS, PUMP_PARTS, "q", describe=describe, k=2, max_samples=5
    )
    assert cr.agreement == 2 and cr.reading.hotspot_ids() == PUMP_HOTSPOTS


def test_consensus_divergence_refuses() -> None:
    describe = _Scripted(
        [_desc(hotspots=("01",)), _desc(hotspots=("02",)), _desc(hotspots=("03",))]
    )
    with pytest.raises(FigureRefusal):
        consensus_read(b"png", PUMP_HOTSPOTS, [], "q", describe=describe, k=2, max_samples=3)


def test_consensus_all_flaky_refuses() -> None:
    describe = _Scripted([VLMUnavailable("x")])
    with pytest.raises(FigureRefusal):
        consensus_read(b"png", PUMP_HOTSPOTS, [], "q", describe=describe, k=2, max_samples=4)


def test_consensus_429_refuses() -> None:
    describe = _Scripted([_desc(), VLMRateLimited("429")])
    with pytest.raises(FigureRefusal):
        consensus_read(
            b"png", PUMP_HOTSPOTS, PUMP_PARTS, "q", describe=describe, k=2, max_samples=5
        )


def test_consensus_agreed_but_uncorroborated_refuses() -> None:
    """Two reads agree on the same (wrong) signature but the declared part
    number is absent from the read text — anchor corroboration must veto it."""
    bad = _desc(parts=[], summary="pump")
    describe = _Scripted([bad, bad])
    with pytest.raises(FigureRefusal):
        consensus_read(
            b"png", PUMP_HOTSPOTS, PUMP_PARTS, "q", describe=describe, k=2, max_samples=5
        )


# --- red-team fix regressions ------------------------------------------------


def test_ingest_refused_read_degrades(pump_dm) -> None:
    """red-team P1: refused=true (even with evidence) is never a positive read."""
    poisoned = _desc(refused=True)  # hotspots + parts present, but refused
    recs = ingest.describe_dm_figures(
        pump_dm, PUMP_PKG, describe=lambda *a, **k: poisoned, repo_root=REPO
    )
    assert not recs[0].verified and recs[0].degraded_reason == "vlm refused"


def test_ingest_selfreported_parts_do_not_corroborate(pump_dm) -> None:
    """red-team P1: corroboration uses OCR reads_text ONLY — the model's own
    parts list must not corroborate itself."""
    only_parts = FigureDescription(
        hotspots=[Hotspot(id=h) for h in ("01", "02", "03")],
        parts=[Part(part_number=p) for p in PUMP_PARTS],
        reads_text=[],  # nothing actually OCR'd
    )
    recs = ingest.describe_dm_figures(
        pump_dm, PUMP_PKG, describe=lambda *a, **k: only_parts, repo_root=REPO
    )
    assert not recs[0].verified and "corroborat" in recs[0].degraded_reason


def test_index_reverify_rejects_tampered_sha(pump_dm) -> None:
    """red-team P1: a hand-edited record whose SHA no longer matches the PNG is
    skipped at index time (the binding is enforced, not just stored)."""
    recs = ingest.describe_dm_figures(
        pump_dm, PUMP_PKG, describe=lambda *a, **k: _desc(), repo_root=REPO
    )
    recs[0].sha256 = "deadbeef" * 8  # tamper
    assert ingest.figure_chunks(pump_dm, recs, "structure", PUMP_PKG, repo_root=REPO) == []


def test_png_path_rejects_traversal() -> None:
    """red-team P2: a crafted ICN id cannot escape the icn/ dir."""
    with pytest.raises(ValueError, match="unsafe ICN id"):
        ingest.png_path(PUMP_PKG, "../../etc/passwd")


# --- round-2 red-team fix regressions ----------------------------------------


def test_reverify_rejects_declared_map_edit(pump_dm) -> None:
    """R2 P1: editing a part number in a record (not the hotspot id) is caught —
    the declared mapping must still match the DM XML, else the figure is skipped
    AND its chunk id would have changed."""
    recs = ingest.describe_dm_figures(
        pump_dm, PUMP_PKG, describe=lambda *a, **k: _desc(), repo_root=REPO
    )
    good = ingest.figure_chunks(pump_dm, recs, "structure", PUMP_PKG, repo_root=REPO)
    assert len(good) == 1
    recs[0].declared_map = ["02|pump body|LA-99-9999-9"] + recs[0].declared_map[1:]  # tamper part
    assert ingest.figure_chunks(pump_dm, recs, "structure", PUMP_PKG, repo_root=REPO) == []


def test_chunk_id_binds_declared_map(pump_dm) -> None:
    """R2 P1: the chunk id changes when the declared mapping changes (so a stale
    Vespa doc under the old id fails corpus verification)."""
    from learnarken.multimodal.ingest import _declared_map, _map_digest

    base = _map_digest(_declared_map(pump_dm.hotspots))
    edited = list(pump_dm.hotspots)
    edited[0] = edited[0].model_copy(update={"part_number": "LA-99-9999-9"})
    assert _map_digest(_declared_map(edited)) != base


def test_consensus_vlm_error_refuses() -> None:
    """R2 P2: a transport/malformed VLMError during second-look fails CLOSED
    (FigureRefusal), never propagates as an engine error."""
    describe = _Scripted([VLMError("http 500")])
    with pytest.raises(FigureRefusal):
        consensus_read(b"png", PUMP_HOTSPOTS, [], "q", describe=describe, k=2, max_samples=3)


def test_consensus_rejects_invented_hotspots() -> None:
    """R2 P2: reads whose hotspot set != declared never reach consensus."""
    invented = _desc(hotspots=("01", "99"))
    describe = _Scripted([invented, invented])
    with pytest.raises(FigureRefusal):
        consensus_read(b"png", PUMP_HOTSPOTS, [], "q", describe=describe, k=2, max_samples=4)


def test_figure_ref_ambiguous_quote_has_no_hotspot() -> None:
    """R2 P2: a quote naming two hotspots must not guess one."""
    from learnarken.answer.engine import _figure_ref
    from learnarken.chunking.base import Chunk

    fig = Chunk(
        chunk_id="f",
        strategy="structure",
        dmc="D",
        dm_title="",
        issue_info="",
        chunk_type="figure",
        source_path="figure/ICN-X",
        text="",
        icn_refs=["ICN-X"],
    )
    assert _figure_ref(fig, "Hotspot 01: inlet. Hotspot 02: body.") == "[ICN-X]"
    assert _figure_ref(fig, "Hotspot 02: body — part P.") == "[ICN-X, Hotspot 02]"


def test_ungrounded_figure_tokens_blocks_freetext_and_concrete() -> None:
    """R2 P1 (Yi Xin ruling): a figure answer must not assert ANY content —
    free-text (colour/material) or concrete (part/measurement) — that isn't in
    the cited quote or the question. Numbers/counts + question-echo pass."""
    from learnarken.answer.engine import _ungrounded_figure_tokens

    quote = "Figure ICN-X. Hotspot 02: pump body — part LA-29-4711-9."
    # legitimate: value in quote, question-echo, count
    assert (
        _ungrounded_figure_tokens("The part is LA-29-4711-9.", quote, "what part at hotspot 02")
        == []
    )
    assert (
        _ungrounded_figure_tokens(
            "Three hotspots are called out: 01, 02, 03.", quote, "how many hotspots are called out"
        )
        == []
    )
    # free-text hallucination: colour not in quote/question → blocked
    assert _ungrounded_figure_tokens(
        "The pump body is blue.", quote, "what colour is the pump body"
    ) == ["blue"]
    assert "steel" in _ungrounded_figure_tokens("It is made of steel.", quote, "what material")
    # concrete fabrication still blocked
    assert "LA-99-9999-9" in _ungrounded_figure_tokens("It is LA-99-9999-9.", quote, "what part")
    # referencing the ICN id (grounded in the cited chunk text) must NOT flag
    assert _ungrounded_figure_tokens("Three, in figure ICN-X.", "Figure ICN-X. …", "how many") == []


def test_tokenize_strips_trailing_punctuation() -> None:
    """R2 P3: `LA-24-5001-2.` corroborates `LA-24-5001-2`."""
    assert "LA-24-5001-2" in ingest._tokenize(["reads LA-24-5001-2."])
    assert "A-1" not in ingest._tokenize(["A-10"])  # still no substring false-positive


# --- G15 answer-engine wiring (hermetic; no live VLM) ------------------------


def test_g15_figure_out_of_description(monkeypatch, tmp_path) -> None:
    """A figure is the evidence but its declared description can't answer the
    question → G15 refuse `figure-out-of-description`, with a second-look
    recorded (mocked)."""
    from langchain_core.documents import Document

    import learnarken.graph as graph_module
    import learnarken.retrieval.hybrid as hybrid
    from learnarken.answer import engine, figure_relook
    from learnarken.chunking.base import Chunk
    from learnarken.chunking.documents import to_document
    from learnarken.graph import GraphFacts
    from learnarken.llm.minimax import ChatResult

    monkeypatch.chdir(tmp_path)
    fig = Chunk(
        chunk_id="f1",
        strategy="structure",
        dmc="DMC-LA100-A-29-10-00-00A-941A-D",
        dm_title="Pump",
        issue_info="001-00",
        chunk_type="figure",
        source_path=f"figure/{PUMP_ICN}",
        text=f"Figure {PUMP_ICN}.\nHotspot 01: inlet port — part LA-29-4711-1.",
        icn_refs=[PUMP_ICN],
    )
    monkeypatch.setattr(engine, "corpus_chunks", lambda pkg, strategy: [fig])
    monkeypatch.setattr(engine, "verify_corpus", lambda c, s: None)
    monkeypatch.setattr(engine, "load_threshold", lambda: 0.5)
    monkeypatch.setattr(
        engine,
        "_candidates",
        lambda q, c, mode: [Document(page_content=fig.text, metadata={"chunk_id": fig.chunk_id})],
    )
    monkeypatch.setattr(hybrid, "rerank_scored", lambda q, docs, k=10: [(to_document(fig), 0.9)])
    monkeypatch.setattr(
        graph_module,
        "facts",
        lambda dmcs: [GraphFacts(dmc=d, title="Pump") for d in dict.fromkeys(dmcs)],
    )
    monkeypatch.setattr(
        engine,
        "chat_json",
        lambda system, user: ChatResult(
            parsed={"is_answerable": False, "answer": "", "citations": []},
            raw_content="",
            model="m",
            usage={},
            request_payload={},
        ),
    )
    monkeypatch.setattr(
        figure_relook,
        "figure_second_look",
        lambda q, fc, pkgs: {
            "icn_id": PUMP_ICN,
            "attempted": True,
            "consensus": True,
            "samples": 2,
        },
    )
    result = engine.answer_question("what colour is the pump?", package_dirs=["p"])
    assert result.refused and result.refusal_gate == "figure-out-of-description"
