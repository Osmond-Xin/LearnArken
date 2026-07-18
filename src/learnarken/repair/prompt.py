"""ReAct prompt contract for the repair agent (Day 7).

Structured-JSON ReAct rather than native function-calling: M3 always emits a
`<think>` prefix and the repo already has hardened JSON parsing for it, so each
turn the model returns exactly one action object. The observation history is
fed back verbatim (bounded) as the next user turn.
"""

from __future__ import annotations

import json

from learnarken.validation.report import Finding

SYSTEM_PROMPT = """\
You are a repair agent for S1000D-like XML data modules. You fix ONE validation
finding at a time by proposing a minimal, structured patch and verifying it with
the deterministic validator.

Reply with EXACTLY ONE JSON object per turn, no prose outside it:
  {"thought": "<brief reasoning>", "tool": "<tool name>", "args": {<tool args>}}

Tools (the only ones that exist):
- search_corpus   {"query": str, "k": int}   find how sibling modules encode the right pattern
- read_module     {"file": str}              read a data module's XML
- query_xml       {"file": str, "xpath": str}   read-only XPath query
- run_validator   {}                         re-run the validator; returns current findings
- exec_sandbox    {"kind": "python"|"shell", "code": str}   jailed helper (XML/DMC only)
- propose_patch   {"file": str, "target_key": str, "edits": [<edit>...]}   apply + verify a fix

An <edit> is one of:
  {"op": "set_attr", "xpath": str, "attr": str, "value": str}
  {"op": "set_text", "xpath": str, "value": str}
  {"op": "remove_element", "xpath": str}
  {"op": "insert_element", "xpath": str, "position": "before|after|append-child", "xml": "<el/>"}

Rules:
- Keep the patch MINIMAL — touch only the node the finding points at.
- A patch is accepted only when the validator confirms the target finding is
  cleared AND no new finding appeared. If propose_patch returns accepted=false,
  read the delta and try a different edit — do not repeat the same one.
- When you believe the finding is fixed, your last action is the accepted
  propose_patch. Do not fabricate content you cannot ground in the module or corpus.
"""


def render_user(finding: Finding, history: list[dict], target_key: str) -> str:
    """The per-turn user message: the target finding + bounded observation trail."""
    header = {
        "target_finding": {
            "key": target_key,
            "rule_id": finding.rule_id,
            "layer": str(finding.layer),
            "file": finding.file,
            "line": finding.line,
            "path": finding.path,
            "message": finding.message,
            "fix_hint": finding.fix_hint,
        }
    }
    # Only the last few observations to keep the prompt bounded (and cheap).
    trail = history[-6:]
    body = {"observations": trail} if trail else {"observations": "none yet — start investigating"}
    return json.dumps({**header, **body}, ensure_ascii=False, default=str, indent=1)
