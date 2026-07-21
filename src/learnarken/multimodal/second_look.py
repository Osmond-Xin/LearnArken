"""Query-time second-look = multi-sample consensus read (Day 12, §4, Decision 2).

Yi Xin's ruling (2026-07-20): a **single** VLM read is not trusted, because the
MiniMax channel is empirically unreliable (a part number dropped a char once,
empty 1/3). So when the ingest-time description does not cover a question, the
agent re-reads the actual image with **multiple independent VLM calls** and
accepts a reading only when the samples **reach consensus** AND agree with the
deterministic anchors (declared part numbers). This is inference-time
self-consistency — the "repeat-test an unreliable generator, report only the
robust result" discipline (Day 8) applied to reading.

Fail-closed (G15): divergence / no-consensus / a 429 ceiling all raise
`FigureRefusal`, which the answer layer maps to `refuse("figure-out-of-
description")`. A single arbitrarily-chosen read is never returned.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from learnarken.multimodal.vlm import (
    FigureDescription,
    VLMError,
    VLMRateLimited,
    VLMUnavailable,
    describe_figure,
)

# Defaults; set from the T5 small-test-set instability rate (INV-5 provenance,
# eval/results/day12-resolution.json) — how many agreeing reads convergence needs.
VLM_CONSENSUS_K = 2
VLM_MAX_SAMPLES = 5


class FigureRefusal(RuntimeError):
    """No reliable reading was obtained — the answer layer must G15-refuse
    (`figure-out-of-description`), never guess (Decision 7)."""


class ConsensusReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reading: FigureDescription
    agreement: int  # how many samples agreed on the accepted signature
    samples: int  # total VLM calls made (including flaky misses)


def _signature(desc: FigureDescription) -> tuple:
    """Canonical, order-independent signature of a read for consensus voting —
    the hotspot-id set plus the part-number set the read claims."""
    return (
        tuple(sorted(desc.hotspot_ids())),
        tuple(sorted(p.part_number for p in desc.parts if p.part_number)),
    )


def _corroborated(desc: FigureDescription, part_numbers: list[str]) -> bool:
    """Do the declared part numbers reappear as whole tokens in the read TEXT?
    OCR text only — NOT the model's own `parts` list (red-team P1: no
    self-corroboration) — and token-boundary not substring, so `LA-24-500`
    cannot spuriously corroborate `LA-24-5001-2`."""
    if not part_numbers:
        return True
    from learnarken.multimodal.ingest import _tokenize

    tokens = _tokenize(desc.reads_text)
    return all(pn in tokens for pn in part_numbers)


def consensus_read(
    png_bytes: bytes,
    declared_hotspots: set[str],
    part_numbers: list[str],
    question: str,
    *,
    describe: Callable[..., FigureDescription] = describe_figure,
    k: int = VLM_CONSENSUS_K,
    max_samples: int = VLM_MAX_SAMPLES,
) -> ConsensusReading:
    """Sample the VLM until `k` reads agree (early stop) and the agreed reading
    is anchor-corroborated. Raises FigureRefusal on 429, divergence, or
    exhaustion. Each sample is one independent call (no per-call retry — the
    consensus loop IS the robustness mechanism)."""
    if k < 1 or max_samples < k:
        raise ValueError(f"need 1 <= k <= max_samples, got k={k} max_samples={max_samples}")
    reads: list[FigureDescription] = []
    votes: Counter[tuple] = Counter()
    attempts = 0
    while attempts < max_samples:
        attempts += 1
        try:
            desc = describe(png_bytes, declared_hotspots, question=question, max_retries=1)
        except VLMRateLimited as exc:
            raise FigureRefusal("VLM 429 ceiling during second-look") from exc
        except VLMUnavailable:
            continue  # a flaky miss consumes an attempt but casts no vote
        except VLMError as exc:
            # transport / malformed-200 during query-time second-look must fail
            # CLOSED (refuse), never propagate as an engine error (red-team R2 P2)
            raise FigureRefusal(f"VLM error during second-look: {exc}") from exc
        if desc.refused:
            continue  # an explicit VLM refusal is not a positive reading
        if desc.hotspot_ids() != declared_hotspots:
            # a read that invents or misses a hotspot is not a valid positive
            # reading — it may not vote (red-team R2 P2: no invented-id consensus)
            continue
        reads.append(desc)
        sig = _signature(desc)
        votes[sig] += 1
        if votes[sig] >= k:
            agreed = next(r for r in reads if _signature(r) == sig)
            if not _corroborated(agreed, part_numbers):
                raise FigureRefusal(
                    f"consensus reached but not anchor-corroborated (parts {part_numbers})"
                )
            return ConsensusReading(reading=agreed, agreement=votes[sig], samples=attempts)
    raise FigureRefusal(
        f"no {k}-way consensus after {attempts} samples "
        f"(distinct signatures: {len(votes)}) — reading not reliably obtained"
    )
