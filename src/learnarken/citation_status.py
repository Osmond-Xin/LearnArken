"""Current status of a cited source (Arken pillar 2, the `status` field).

Their trace definition, quoted from the pinned snapshot
(docs/research/arken-source-snapshot-2026-07-26.md §2):

    Trace — "question, decision, sources used/excluded, review path, and
    **status**".

For a technical publication, "status" means: is the module I just cited the
current issue, or has it been superseded? S1000D answers that with a registry —
the **DML** records each module with an issue number — so the check is against
declared data, not inference.

## What this found, stated rather than assumed

On an *admitted* corpus every citation is current **by construction**, because
the ingest gate already rejected the alternatives:

- `XREF-003` (error) — a DM whose `issueInfo` disagrees with its DML
  registration rejects the package.
- `XREF-007` (warning) — where duplicate issues of one DMC exist, the **newest
  wins the index** and the older copies are reported.

So the answer layer inherits a guarantee that a system with a permissive ingest
would have to re-check at query time. That is worth *reporting* rather than
assuming: this module re-derives the status from the registry on every answered
query and says which registration backs it, so the guarantee is evidence in the
trace instead of a claim in a README.

The honest residual: a module that no DML registers cannot be confirmed by the
registry at all. It is reported as `unregistered`, not silently as current.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel

from learnarken.package import NotAPackageError

logger = logging.getLogger(__name__)

CURRENT = "current"
SUPERSEDED = "superseded"
UNREGISTERED = "unregistered"
UNKNOWN = "unknown"

BASIS_CURRENT = (
    "DML registration matches the module's issueInfo; ingest rejects a mismatch "
    "(XREF-003) and indexes only the newest of duplicate issues (XREF-007)"
)
BASIS_UNREGISTERED = (
    "no DML in the package registers this module, so its currency cannot be "
    "confirmed against a registry"
)
BASIS_SUPERSEDED = (
    "the cited issue {issue} does not match the DML registration {registered} — "
    "the registry and the module disagree, so this citation is not current"
)
BASIS_UNKNOWN = "the package model could not be loaded ({error}), so status is not asserted"
BASIS_NO_ISSUE = (
    "the citation carries no issue number, so it cannot be compared with the "
    "DML registration — currency is unknown, not assumed"
)


class CitationStatus(BaseModel):
    dmc: str
    issue: str | None = None
    registered_issue: str | None = None
    state: str = UNKNOWN
    basis: str = ""


def _registry(package_dirs: list[str | Path]) -> dict[str, str]:
    """DMC -> issue as registered by any DML across the admitted packages."""
    from learnarken.validation import analyze_package

    registered: dict[str, str] = {}
    for directory in package_dirs:
        _report, package = analyze_package(directory)
        for dml in package.dmls:
            for entry in dml.entries:
                if entry.issue_info is not None:
                    registered[entry.dm_code.as_str()] = entry.issue_info.as_str()
    return registered


def statuses_for(
    cited: list[tuple[str, str]],
    package_dirs: list[str | Path],
) -> list[CitationStatus]:
    """Status per cited (dmc, issue). Never raises into the answer path.

    A status lookup failing is not a reason to void a verified answer — the
    citation itself was already validated against the chunk. The failure is
    reported as `unknown` rather than swallowed or escalated.
    """
    try:
        registered = _registry(package_dirs)
    except (NotAPackageError, OSError, ValueError, KeyError, AttributeError) as exc:
        # Degrade to `unknown` with the cause named, never silently: an audit
        # record that says "unknown" without saying why is not auditable
        # (red-team P2, 2026-07-27). Narrow enough that a programming error
        # still surfaces instead of being absorbed.
        logger.warning("citation status unavailable: %s: %s", type(exc).__name__, exc)
        basis = BASIS_UNKNOWN.format(error=type(exc).__name__)
        return [CitationStatus(dmc=dmc, issue=issue or None, basis=basis) for dmc, issue in cited]

    out: list[CitationStatus] = []
    for dmc, issue in cited:
        reg = registered.get(dmc)
        if reg is None:
            out.append(
                CitationStatus(
                    dmc=dmc, issue=issue or None, state=UNREGISTERED, basis=BASIS_UNREGISTERED
                )
            )
        elif not issue:
            # A citation with no issue metadata cannot be confirmed current;
            # calling it current would launder missing data into a guarantee
            # (red-team P2, 2026-07-27).
            out.append(
                CitationStatus(
                    dmc=dmc,
                    issue=None,
                    registered_issue=reg,
                    state=UNKNOWN,
                    basis=BASIS_NO_ISSUE,
                )
            )
        elif issue != reg:
            # The whole point of consulting a registry is to catch this. Ingest
            # rejects it (XREF-003), so reaching here means something upstream
            # changed after admission — report it, never call it current
            # (red-team P1, 2026-07-27: the first version skipped this compare
            # and would have reported a mismatch as `current`).
            out.append(
                CitationStatus(
                    dmc=dmc,
                    issue=issue,
                    registered_issue=reg,
                    state=SUPERSEDED,
                    basis=BASIS_SUPERSEDED.format(issue=issue, registered=reg),
                )
            )
        else:
            out.append(
                CitationStatus(
                    dmc=dmc,
                    issue=issue or None,
                    registered_issue=reg,
                    state=CURRENT,
                    basis=BASIS_CURRENT,
                )
            )
    return out
