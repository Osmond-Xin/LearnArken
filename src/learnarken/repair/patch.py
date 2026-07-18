"""Apply structured, minimal XML edits to a data module (Day 7).

Only four bounded ops are allowed (see `EditOp`): set an attribute, set element
text, remove an element, or insert one element fragment. Each op anchors on an
XPath that must match exactly one node — that single-node requirement is what
makes a patch "minimal-diff" and keeps it auditable. Free-form markup rewriting
is deliberately impossible.

Parsing uses a hardened lxml parser (no entity resolution, no network, no DTD),
matching the Day 2 loader's posture — an uploaded module cannot smuggle an
entity bomb through the repair path either.
"""

from __future__ import annotations

from io import BytesIO

from lxml import etree

from learnarken.repair.models import EditOp

_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False
)


class PatchError(ValueError):
    """An edit could not be applied unambiguously (bad xpath, wrong cardinality)."""


def _one(nodes: list, xpath: str) -> etree._Element:
    if len(nodes) != 1:
        raise PatchError(f"xpath {xpath!r} matched {len(nodes)} nodes, need exactly 1")
    node = nodes[0]
    if not isinstance(node, etree._Element):
        raise PatchError(f"xpath {xpath!r} did not select an element")
    return node


def apply_edits(xml_bytes: bytes, edits: list[EditOp]) -> bytes:
    """Return a new XML document with the edits applied. Pure; raises PatchError."""
    tree = etree.parse(BytesIO(xml_bytes), _PARSER)
    root = tree.getroot()
    for edit in edits:
        nodes = root.xpath(edit.xpath)
        if edit.op == "set_attr":
            if not edit.attr or edit.value is None:
                raise PatchError("set_attr needs attr and value")
            _one(nodes, edit.xpath).set(edit.attr, edit.value)
        elif edit.op == "set_text":
            if edit.value is None:
                raise PatchError("set_text needs value")
            _one(nodes, edit.xpath).text = edit.value
        elif edit.op == "remove_element":
            node = _one(nodes, edit.xpath)
            parent = node.getparent()
            if parent is None:
                raise PatchError("cannot remove the document root")
            parent.remove(node)
        elif edit.op == "insert_element":
            if not edit.xml:
                raise PatchError("insert_element needs an xml fragment")
            anchor = _one(nodes, edit.xpath)
            try:
                fragment = etree.fromstring(edit.xml.encode("utf-8"), _PARSER)
            except etree.XMLSyntaxError as exc:
                raise PatchError(f"insert fragment is not well-formed: {exc}") from exc
            if edit.position == "append-child":
                anchor.append(fragment)
            elif edit.position in ("before", "after"):
                parent = anchor.getparent()
                if parent is None:
                    raise PatchError("cannot insert as sibling of the document root")
                index = parent.index(anchor) + (1 if edit.position == "after" else 0)
                parent.insert(index, fragment)
            else:
                raise PatchError(f"unknown insert position {edit.position!r}")
        else:
            raise PatchError(f"unknown edit op {edit.op!r}")
    return etree.tostring(tree, xml_declaration=True, encoding=tree.docinfo.encoding or "UTF-8")
