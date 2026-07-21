"""The repair agent's restricted tool set (Day 7, Decision 5).

No general-purpose toolbox. Tools are limited to: re-retrieval / matching over
the document context and the agent's own content, reading and querying XML,
running the deterministic validator (the closed-loop verifier), proposing a
minimal structured patch, and the sandboxed code executor. Every tool operates
inside the jail — none can touch the live corpus.

`propose_patch` is the crux and the safety net: it applies the edits to the jail
copy, re-runs the validator, and **accepts only if the targeted finding is
cleared with zero new findings** (over-repair / semantic-drift guard, research
§5.2). On failure it reverts the file and hands the validator delta back so the
agent can try again.
"""

from __future__ import annotations

import difflib
from collections import Counter

from lxml import etree

from learnarken.repair.models import EditOp, ValidatorDelta
from learnarken.repair.patch import PatchError, apply_edits
from learnarken.repair.sandbox import Sandbox, SandboxViolation
from learnarken.validation import DEFAULT_ACCEPTED_MODELS, analyze_package
from learnarken.validation.report import Finding

_QUERY_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False
)


def finding_key(f: Finding) -> str:
    """Stable identity for a finding across validator runs.

    Includes line, severity and message so a finding *mutated in place* (same
    rule/file/path, different offending value) reads as a new finding rather
    than hiding from the over-repair guard (red-team #9).
    """
    return f"{f.rule_id}@{f.file}@{f.path or ''}@L{f.line}@{f.severity}@{f.message}"


class ToolError(RuntimeError):
    """A tool call failed in a recoverable way — reported as an observation."""


class Toolbox:
    """Stateful tool registry bound to one sandbox + validation config."""

    _MAX_K = 20  # cap search fan-out (red-team #12)
    _MAX_XPATH = 2000  # cap XPath length so a pathological expression can't burn CPU

    def __init__(
        self,
        sandbox: Sandbox,
        accepted_models: tuple[str, ...] = DEFAULT_ACCEPTED_MODELS,
    ) -> None:
        self.sandbox = sandbox
        self.accepted_models = accepted_models

    # -- validation --------------------------------------------------------
    def validate(self) -> list[Finding]:
        report, _ = analyze_package(self.sandbox.root, self.accepted_models)
        return report.findings

    # -- dispatch ----------------------------------------------------------
    def call(self, name: str, args: dict) -> dict:
        handler = {
            "search_corpus": self._search_corpus,
            "read_module": self._read_module,
            "query_xml": self._query_xml,
            "run_validator": self._run_validator,
            "propose_patch": self._propose_patch,
            "exec_sandbox": self._exec_sandbox,
        }.get(name)
        if handler is None:
            return {"error": f"unknown tool {name!r}"}
        try:
            return handler(args)
        except (ToolError, PatchError, SandboxViolation, KeyError, ValueError, OSError) as exc:
            # OSError (e.g. FileNotFoundError) covers a hallucinated filename in
            # read_module/query_xml: it must become an observation the agent can
            # recover from, never crash the run (fail closed, INV-4). Day 13 ToT
            # exposed this — 3 candidates at temperature>0 hallucinate filenames
            # far more often than the single temp-0 baseline did.
            return {"error": f"{type(exc).__name__}: {exc}"}

    # -- individual tools --------------------------------------------------
    def _search_corpus(self, args: dict) -> dict:
        """BM25 over the package's own chunks — find how sibling modules encode
        the correct pattern. Offline (no services), Day 3 path."""
        from learnarken.retrieval import search_package

        query = str(args["query"])
        k = max(1, min(int(args.get("k", 3)), self._MAX_K))
        try:
            hits = search_package(self.sandbox.root, query, mode="bm25", k=k)
        except Exception as exc:  # noqa: BLE001 — surfaced as an observation, not raised
            raise ToolError(f"search failed: {exc}") from exc
        return {
            "hits": [
                {"chunk_id": h.chunk.chunk_id, "dmc": h.chunk.dmc, "text": h.chunk.text[:400]}
                for h in hits
            ]
        }

    def _read_module(self, args: dict) -> dict:
        name = str(args["file"])
        return {"file": name, "content": self.sandbox.read(name)[:6000]}

    def _query_xml(self, args: dict) -> dict:
        name = str(args["file"])
        xpath = str(args["xpath"])
        if len(xpath) > self._MAX_XPATH:
            raise ToolError("xpath too long")
        tree = etree.parse(str(self.sandbox.resolve(name)), _QUERY_PARSER)
        try:
            nodes = tree.xpath(xpath)
        except etree.XPathError as exc:
            raise ToolError(f"bad xpath: {exc}") from exc
        out = []
        for n in nodes[:20]:
            if isinstance(n, etree._Element):
                out.append(
                    {"tag": n.tag, "attrib": dict(n.attrib), "text": (n.text or "").strip()[:200]}
                )
            else:
                out.append({"value": str(n)[:200]})
        return {"matches": out, "count": len(nodes)}

    def _run_validator(self, _args: dict) -> dict:
        findings = self.validate()
        return {
            "finding_count": len(findings),
            "findings": [
                {"rule_id": f.rule_id, "layer": str(f.layer), "file": f.file, "message": f.message}
                for f in findings
            ],
        }

    def _exec_sandbox(self, args: dict) -> dict:
        kind = str(args.get("kind", "python"))
        code = str(args["code"])
        result = self.sandbox.exec_code(kind, code)
        return {
            "ok": result.ok,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def _propose_patch(self, args: dict) -> dict:
        """Apply edits to the jail copy, re-validate, accept only a clean fix.

        The target finding and its file are **bound server-side** (red-team
        #4/#5): the LLM cannot retarget a different finding or patch a different
        file to fake a fix. The patch is kept only if the bound target is gone
        AND no new finding appeared (multiset diff — red-team #9); otherwise the
        file is reverted and the delta is returned for another attempt.
        """
        if self.sandbox.target_key is None or self.sandbox.target_file is None:
            raise ToolError("no target finding bound — propose_patch is not available")
        name = str(args["file"])
        if name != self.sandbox.target_file:
            raise ToolError(
                f"patch file {name!r} != the finding's file {self.sandbox.target_file!r} "
                "— a patch may only touch the finding's own module"
            )
        edits = [EditOp(**e) for e in args["edits"]]
        for e in edits:
            if len(e.xpath) > self._MAX_XPATH:
                raise ToolError("edit xpath too long")

        before = self.validate()
        before_keys = Counter(finding_key(f) for f in before)
        original = self.sandbox.resolve(name).read_bytes()

        patched = apply_edits(original, edits)
        self.sandbox.resolve(name).write_bytes(patched)

        try:
            after = self.validate()
        except Exception:
            # A failure after the write (e.g. an OSError re-reading a truncated
            # file) must not leave the jail in a half-mutated state that later
            # tools see as real: restore the original and fail closed (red-team P2).
            self.sandbox.resolve(name).write_bytes(original)
            raise
        after_keys = Counter(finding_key(f) for f in after)

        cleared = sorted((before_keys - after_keys).elements())
        introduced = sorted((after_keys - before_keys).elements())
        delta = ValidatorDelta(
            findings_before=len(before),
            findings_after=len(after),
            cleared=cleared,
            introduced=introduced,
        )

        # Accept only when the *bound* target is among the cleared and nothing
        # new appeared (over-repair / generator-verifier guard).
        accepted = self.sandbox.target_key in cleared and not introduced
        if not accepted:
            self.sandbox.resolve(name).write_bytes(original)  # revert — no partial state
        diff = "".join(
            difflib.unified_diff(
                original.decode("utf-8", "replace").splitlines(keepends=True),
                patched.decode("utf-8", "replace").splitlines(keepends=True),
                fromfile=f"a/{name}",
                tofile=f"b/{name}",
            )
        )
        return {
            "accepted": accepted,
            "diff": diff if accepted else "",
            "delta": delta.model_dump(),
            "reason": (
                "clean fix"
                if accepted
                else f"target_cleared={self.sandbox.target_key in cleared}, introduced={introduced}"
            ),
        }
