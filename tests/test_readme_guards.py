"""README link and anchor guards (Phase 0.3, red-team F-14).

The reading router in README.md points at in-page anchors. A router whose
anchors do not resolve is worse than no router, and nothing in the suite
checked that before: the existing doc guards cover EVIDENCE.md and the
benchmark tables, not README cross-references.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
READMES = [REPO / "README.md", REPO / "README.zh-CN.md"]

# [text](target) where target is not an external URL, mailto, or bare fragment.
LINK = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<target>[^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$", re.MULTILINE)


def _slug(title: str) -> str:
    """GitHub's heading -> anchor rule, for the subset of syntax used here."""
    text = re.sub(r"`([^`]*)`", r"\1", title)  # code spans keep their content
    text = re.sub(r"\*\*?([^*]*)\*\*?", r"\1", text)  # strip bold/italic
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links keep their text
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    # One hyphen per space, not per run: "a — b" drops the dash and keeps both
    # spaces, which is why GitHub anchors contain doubled hyphens.
    return re.sub(r"\s", "-", text)


def _anchors(markdown: str) -> set[str]:
    return {_slug(m.group("title")) for m in HEADING.finditer(markdown)}


@pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
def test_in_page_anchors_resolve(readme: Path) -> None:
    body = readme.read_text(encoding="utf-8")
    available = _anchors(body)
    broken = [
        m.group("target")
        for m in LINK.finditer(body)
        if m.group("target").startswith("#") and m.group("target")[1:] not in available
    ]
    assert not broken, f"{readme.name}: unresolved in-page anchors {broken}"


@pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
def test_relative_links_point_at_real_paths(readme: Path) -> None:
    body = readme.read_text(encoding="utf-8")
    missing = []
    for match in LINK.finditer(body):
        target = match.group("target")
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path, _, fragment = target.partition("#")
        if not path:
            continue
        resolved = (REPO / path).resolve()
        if not resolved.exists():
            missing.append(target)
            continue
        if (
            fragment
            and resolved.suffix == ".md"
            and fragment not in _anchors(resolved.read_text(encoding="utf-8"))
        ):
            missing.append(target)
    assert not missing, f"{readme.name}: links to missing paths/anchors {missing}"


def test_reading_router_is_present_and_early() -> None:
    """The router only helps a triaging reader if it is above the fold."""
    body = (REPO / "README.md").read_text(encoding="utf-8")
    head = "\n".join(body.splitlines()[:60])
    assert "How to read this in the time you have" in head


def test_the_demo_gif_claims_hold_against_their_traces() -> None:
    """README §1 says the refusal happened before the model was called, and that
    the retraction withdrew nothing visible. Both are settled by the traces
    committed beside those GIFs — so CI settles them too, rather than leaving
    another hand-written claim free to drift (the test count in this same README
    drifted twice on one branch)."""
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "tools" / "verify_demo_traces.py"
    spec = importlib.util.spec_from_file_location("verify_demo_traces", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.check() == []
