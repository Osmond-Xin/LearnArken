"""A refusal as a routed action item (Arken pillar 3).

Their definition, quoted from the pinned snapshot
(docs/research/arken-source-snapshot-2026-07-26.md §2):

    Refusal — "A routed action item indicating **why** evidence is insufficient,
    **what would resolve it**, and **who should act**."

`why` already existed: every refusal names the gate that fired. This module adds
the other two.

## Why `who should act` is usually `None`, and why that is the honest answer

A gap has a key: the corpus itself declares a DMC that is absent, and that DMC
yields an SNS system code to look up. A refusal has no such key. When the system
refuses "APU automatic start sequence" there is no cited module, and nothing in
the corpus declares that an APU module should exist — the corpus is simply
silent. Producing an owner would mean inferring a DMC from free text ("APU is
usually ATA 49"), which is precisely the fabrication gate 10 exists to prevent.

So (ruling 2026-07-27, option A): **a refusal routes an owner only when it links
to an existing gap signature** — the question literally names a DMC that the
corpus declares and does not contain. Then the owner is the gap's owner, and the
link is a string identity, not an inference. In every other case the owner is
`None` with a stated reason.

That keeps the two output classes distinct in the way Arken separates them: a
gap says "this domain is declared and missing, here is who supplies it"; a
refusal says "the evidence here cannot support an answer" and only borrows an
owner when a gap is demonstrably the cause.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

#: A DMC as it appears in text. Deliberately strict: this is an identity match
#: used to route work to a human, not a fuzzy search.
DMC_IN_TEXT = re.compile(r"\bDMC-[A-Z0-9]+(?:-[A-Z0-9]+)+\b", re.IGNORECASE)

NO_DMC_IN_QUESTION = (
    "the question names no data module, so no declared-missing module can be "
    "linked to it — the corpus is silent rather than incomplete in a named place"
)
DMC_NOT_A_GAP = (
    "{dmc} is not a declared-missing module in this corpus, so this refusal "
    "does not identify a knowledge gap to route"
)
PRE_ADMISSION_NOT_ROUTABLE = (
    "{dmc} is declared-missing only in a package the ingest gate rejected; that "
    "package's ownership metadata was never admitted either, so it is reported "
    "but not routed"
)

#: What would resolve each fail-closed gate. Keyed by the gate names the answer
#: engine emits; every gate must have an entry, so a new gate cannot ship
#: without saying what would resolve it.
RESOLUTIONS: dict[str, str] = {
    "threshold": (
        "no indexed chunk scored above the measured refusal threshold — supply a "
        "data module covering this topic and re-run `learnarken index`, or "
        "confirm the topic is genuinely outside this publication"
    ),
    "llm": (
        "the model judged the retrieved evidence insufficient to answer — supply "
        "a data module that states the answer, then re-index"
    ),
    "llm-contract": (
        "the generation service returned a malformed response; this is an "
        "infrastructure fault, not a knowledge gap — check the model endpoint "
        "and retry"
    ),
    "citation-validation": (
        "the model produced text it could not ground in a retrieved chunk — the "
        "answer was withdrawn; no action is required of a domain expert, but a "
        "recurring pattern here is a prompt or model issue worth investigating"
    ),
    "figure-out-of-description": (
        "the claim went beyond what the verified figure description supports — "
        "re-describe the figure, or supply a data module that states the detail "
        "in text"
    ),
}

UNKNOWN_GATE = (
    "no resolution advice is registered for gate {gate!r} — this is a bug in the "
    "refusal router, not a statement about the corpus"
)


class RefusalAction(BaseModel):
    """The three parts Arken's definition asks for."""

    gate: str
    why: str
    what_would_resolve: str
    owner: str | None = None
    owner_reason: str | None = None
    gap_signature: str | None = None

    @property
    def routed(self) -> bool:
        return self.owner is not None


def route(
    question: str,
    gate: str,
    package_dirs: list[str | Path] | None = None,
) -> RefusalAction:
    """Build the routed action item for a refusal.

    Gap collection is only attempted when the question literally names a DMC:
    without one there is nothing that could match a gap signature, and running
    the validator on every refusal would be cost for a foregone conclusion.
    """
    action = RefusalAction(
        gate=gate,
        why=f"refused at the {gate} gate",
        what_would_resolve=RESOLUTIONS.get(gate, UNKNOWN_GATE.format(gate=gate)),
    )

    mentioned = [m.group(0).upper() for m in DMC_IN_TEXT.finditer(question)]
    if not mentioned:
        action.owner_reason = NO_DMC_IN_QUESTION
        return action
    if not package_dirs:
        action.owner_reason = "no package scope available to check for declared-missing modules"
        return action

    from learnarken.gaps import collect_gaps

    try:
        report = collect_gaps(list(package_dirs))
    except Exception as exc:  # noqa: BLE001 — a routing lookup must not void a decided refusal
        action.owner_reason = f"gap lookup failed ({type(exc).__name__}), so no owner was resolved"
        return action
    # **Admitted gaps only.** A pre-admission gap comes from a package the gate
    # rejected, and its `owners.json` was never admitted either — routing work
    # on the authority of a rejected package's metadata would trust exactly the
    # input the ingest gate refused (red-team P1, 2026-07-27).
    by_signature = {g.signature.upper(): g for g in report.admitted_gaps}
    pre_admission = {g.signature.upper() for g in report.pre_admission_gaps}
    for dmc in mentioned:
        gap = by_signature.get(dmc)
        if gap is None:
            continue
        action.gap_signature = gap.signature
        action.owner = gap.owner
        action.owner_reason = gap.owner_reason
        return action

    if pre_admission & set(mentioned):
        named = sorted(pre_admission & set(mentioned))[0]
        action.owner_reason = PRE_ADMISSION_NOT_ROUTABLE.format(dmc=named)
        return action
    action.owner_reason = DMC_NOT_A_GAP.format(dmc=mentioned[0])
    return action
