"""Ownership lookup: who should act on a gap or a refusal.

Arken defines a refusal as "a routed action item indicating why evidence is
insufficient, what would resolve it, and **who should act**"
(docs/research/arken-source-snapshot-2026-07-26.md §2). The `who` needs a
source of ownership data.

S1000D carries one natively — `responsiblePartnerCompany` — but the synthetic
corpus in this repo does not populate it (it appears only under
`samples/s1000d/`, which is reference-only and must not be copied), and adding
it to a sample DM would change that file's bytes and therefore every chunk id
derived from it (`chunking.base.make_chunk_id`), invalidating the corpus
manifest.

So ownership lives outside the XML, in a per-package `owners.json` keyed by SNS
system code. **This is project-authored synthetic governance data, not an
S1000D-native field** — a Toy-scale mechanism, labelled as such wherever the
capability is claimed. Ruling D5, 2026-07-26.

Unknown ownership resolves to `None` with a stated reason. It never guesses: a
fabricated owner is worse than an absent one, because it routes work to someone
who does not exist.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

OWNERS_FILENAME = "owners.json"

NO_MAP = "no owners.json in the package — ownership is not modelled here"
UNREADABLE_MAP = "owners.json could not be read ({error}) — ownership is unknown, not guessed"
NO_ENTRY = "no owner registered for SNS system {system}"
UNPARSEABLE_DMC = "DMC {dmc!r} does not expose an SNS system code"


class OwnerRef(BaseModel):
    """Who should act, or an explicit reason why that is unknown."""

    owner: str | None
    reason: str | None = None
    source: str = "owners.json (project-authored synthetic data, not S1000D)"

    @property
    def routed(self) -> bool:
        return self.owner is not None


class OwnerMap(BaseModel):
    """SNS system code -> responsible party."""

    by_system: dict[str, str] = {}
    present: bool = True
    unreadable: str | None = None

    @classmethod
    def load(cls, package_dir: str | Path) -> OwnerMap:
        path = Path(package_dir) / OWNERS_FILENAME
        if not path.is_file():
            return cls(by_system={}, present=False)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            systems = raw["by_system"] if isinstance(raw, dict) else {}
            if not isinstance(systems, dict):
                raise TypeError("by_system must be an object")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # A broken owner map must not turn an already-decided refusal into
            # an error. Unknown ownership is a valid answer; a crash is not
            # (red-team P2, 2026-07-27).
            logger.warning("unreadable %s: %s: %s", path, type(exc).__name__, exc)
            return cls(by_system={}, present=False, unreadable=type(exc).__name__)
        return cls(by_system={str(k): str(v) for k, v in systems.items()}, present=True)

    def resolve(self, dmc: str) -> OwnerRef:
        if not self.present:
            reason = (
                NO_MAP if self.unreadable is None else UNREADABLE_MAP.format(error=self.unreadable)
            )
            return OwnerRef(owner=None, reason=reason)
        system = _sns_system(dmc)
        if system is None:
            return OwnerRef(owner=None, reason=UNPARSEABLE_DMC.format(dmc=dmc))
        owner = self.by_system.get(system)
        if owner is None:
            return OwnerRef(owner=None, reason=NO_ENTRY.format(system=system))
        return OwnerRef(owner=owner)


def _sns_system(dmc: str) -> str | None:
    """The SNS system code from a DMC, e.g. `29` in DMC-LA100-A-29-10-00-00A-520A-A.

    Positional, matching `models.DmCode`: after the DMC- prefix come the model
    identification code and the system difference code, then the system.
    """
    parts = dmc.split("-")
    if parts and parts[0].upper() == "DMC":
        parts = parts[1:]
    if len(parts) < 3:
        return None
    system = parts[2]
    return system if system.isdigit() else None
