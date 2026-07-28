"""Authorisation before reasoning (Arken pillar 1).

Their wording, quoted from the pinned snapshot
(docs/research/arken-source-snapshot-2026-07-26.md §3.1):

    "Authorization constrains reasoning, not just retrieval."

and, from `/architecture`:

    "Access controls operate *prior* to any reasoning step, scoping sources by
    role, region, and admission status before the model engages."

That sentence excludes the shape this repo had: the Vespa-backed modes
*retrieved first and filtered after* (red-team F-01). A chunk the caller may not
see would already have been in the candidate set, and a candidate set is what
the reranker and the model reason over. So the filter has to move into the
retrieval call itself — into BM25 corpus construction on the offline path, and
into the YQL `where` clause ahead of `nearestNeighbor` on the engine path.

S1000D supplies the source of truth: `security/@securityClassification` on
`dmStatus`, which this repo already carries all the way to `Chunk`. Clearance is
therefore a real attribute of the corpus, not invented metadata.

**Fail closed on ambiguity.** A chunk whose classification is missing or
unparseable is *not* admitted when a clearance is being enforced. The
alternative — defaulting an unlabelled chunk to unclassified — makes the
authorisation gate fail open on exactly the malformed input it exists to catch.
With no clearance requested, nothing is filtered and nothing is claimed.
"""

from __future__ import annotations

from pydantic import BaseModel

from learnarken.chunking.base import Chunk

#: S1000D security classifications, least to most restrictive. `01` is
#: unclassified. The corpus in this repo uses `01` throughout; the ordering is
#: what makes "clearance ≥ classification" decidable.
CLASSIFICATIONS: tuple[str, ...] = ("01", "02", "03", "04", "05")

UNLABELLED = "chunk carries no securityClassification — not admissible under an enforced clearance"
UNKNOWN_LABEL = "chunk classification {value!r} is outside the known set {known}"


class ClearanceError(ValueError):
    """The requested clearance is not a value this vocabulary knows."""


class Exclusion(BaseModel):
    """A source withheld before reasoning, and why. Feeds the trace."""

    chunk_id: str
    dmc: str
    reason: str = "authorisation"
    detail: str


def normalise(clearance: str) -> str:
    value = str(clearance).strip()
    if value not in CLASSIFICATIONS:
        raise ClearanceError(
            f"unknown clearance {clearance!r}; choose from {list(CLASSIFICATIONS)}"
        )
    return value


def admissible_classifications(clearance: str) -> list[str]:
    """Every classification a holder of `clearance` may see, least-restrictive first."""
    ceiling = normalise(clearance)
    return [c for c in CLASSIFICATIONS if c <= ceiling]


def _verdict(chunk: Chunk, allowed: set[str]) -> str | None:
    """`None` if admissible, else the reason it is withheld."""
    raw = (chunk.security_classification or "").strip()
    if not raw:
        return UNLABELLED
    if raw not in CLASSIFICATIONS:
        return UNKNOWN_LABEL.format(value=raw, known=list(CLASSIFICATIONS))
    if raw not in allowed:
        return f"classification {raw} exceeds clearance {max(allowed)}"
    return None


def partition(chunks: list[Chunk], clearance: str | None) -> tuple[list[Chunk], list[Exclusion]]:
    """Split a corpus into what may be reasoned over and what was withheld.

    Called *before* any retrieval, so the withheld chunks never reach an index,
    a candidate list, a reranker, or a prompt.
    """
    if clearance is None:
        return list(chunks), []
    allowed = set(admissible_classifications(clearance))
    admitted: list[Chunk] = []
    withheld: list[Exclusion] = []
    for chunk in chunks:
        reason = _verdict(chunk, allowed)
        if reason is None:
            admitted.append(chunk)
        else:
            withheld.append(Exclusion(chunk_id=chunk.chunk_id, dmc=chunk.dmc, detail=reason))
    return admitted, withheld


def assert_uniform_or_scoped(chunks: list[Chunk], clearance: str | None) -> None:
    """Refuse to evaluate a mixed-classification corpus without a declared scope.

    The eval and repair harnesses answer over the whole corpus and write their
    output to committed artifacts. If the corpus carried more than one
    classification and no clearance were declared, those artifacts would publish
    answers and citations drawn from classified material — the governed query
    path would be bypassed by the very tooling that measures it
    (red-team P1, 2026-07-27).

    Inert on today's uniformly-`01` corpus, and deliberately so: the guard is
    computed, not assumed, so it starts working the moment the corpus stops
    being uniform.
    """
    if clearance is not None:
        return
    levels = {(c.security_classification or "").strip() for c in chunks}
    if len(levels) > 1:
        raise ClearanceError(
            f"corpus mixes security classifications {sorted(levels)} but no clearance "
            "was declared — refusing to evaluate, because the results would publish "
            "material the governed query path would withhold (fail closed)"
        )


def redact_graph_facts(facts: list, admitted_dmcs: set[str], clearance: str | None) -> list:
    """Drop graph neighbours the caller may not see.

    Partitioning the corpus filters *chunks*. It does not filter the dependency
    graph, whose `REFS` edges point at data modules by DMC — and those DMCs are
    injected into the model's prompt and written to the trace. A caller denied a
    module's content could therefore still learn the module exists, what it is
    called, and what references it, straight out of the reasoning context
    (red-team P0, 2026-07-27).

    "Authorisation constrains reasoning" is the property being implemented, and
    a prompt is reasoning. Neighbours outside the admitted corpus are removed
    and counted, so the trace records that redaction happened rather than
    silently showing a shorter list.
    """
    if clearance is None:
        return facts
    out = []
    for fact in facts:
        kept_out = [d for d in fact.outbound_refs if d in admitted_dmcs]
        kept_in = [d for d in fact.inbound_refs if d in admitted_dmcs]
        withheld = (len(fact.outbound_refs) - len(kept_out)) + (
            len(fact.inbound_refs) - len(kept_in)
        )
        out.append(
            fact.model_copy(
                update={
                    "outbound_refs": kept_out,
                    "inbound_refs": kept_in,
                    "withheld_refs": withheld,
                }
            )
        )
    return out


def assert_documents_admissible(documents: list, clearance: str | None) -> None:
    """Same check over LangChain `Document`s, read straight from metadata.

    Reconstructing a full `Chunk` just to inspect one field would couple this
    guard to the whole chunk schema and fail on any partial document — the
    guard must be cheaper and more robust than the thing it guards.
    """
    if clearance is None:
        return
    allowed = set(admissible_classifications(clearance))
    leaked = []
    for doc in documents:
        meta = getattr(doc, "metadata", {}) or {}
        raw = (meta.get("security_classification") or "").strip()
        if raw not in allowed:
            leaked.append(meta.get("chunk_id"))
    if leaked:
        raise ClearanceError(
            f"chunk(s) above clearance {clearance} survived retrieval {leaked[:3]} — "
            "authorisation filter did not hold (fail closed)"
        )


def assert_admissible(chunks: list[Chunk], clearance: str | None) -> None:
    """Fail closed if anything inadmissible survived into a result set.

    The engine-side filter is the enforcement; this is the check that the
    enforcement held, in the same spirit as the existing package-scope
    assertion in `vespa.store.search`.
    """
    if clearance is None:
        return
    allowed = set(admissible_classifications(clearance))
    leaked = [c.chunk_id for c in chunks if _verdict(c, allowed) is not None]
    if leaked:
        raise ClearanceError(
            f"chunk(s) above clearance {clearance} survived retrieval {leaked[:3]} — "
            "authorisation filter did not hold (fail closed)"
        )
