"""VLM figure-description client (Day 12, docs/specs/day12.md, Interfaces §1).

Reuses the MiniMax proxy transport (llm/minimax.py: Bearer + X-Proxy-Token,
`<think>` strip, `base_resp.status_code == 0` success) but sends the OpenAI
**multimodal** `content` array (`{type:image_url,image_url:{url:data:image/png;
base64,…}}`).

**Probe finding (docs/specs/day12.md, 2026-07-20).** The proxy at
`MINIMAX_API_URL` accepts image content and returns real vision output, but the
channel is **unstable at temperature 0** — featureless images and intermittent
calls come back empty or as prose like "I don't see an image". So every call is
fail-closed with **two distinct stop conditions** (Decision 1):

- (i) empty / "no image" / unparseable / schema-invalid ⇒ a *flaky-channel* miss,
  retried up to `VLM_MAX_RETRIES`; on exhaustion → `VLMUnavailable`;
- (ii) HTTP **429** ⇒ the subscription ceiling (Yi Xin runs a flat subscription,
  not per-token metering), a **terminal** stop → `VLMRateLimited`, never retried.

Temperature 0, structured output, one image per call. Hotspot ids are prompted
as an **enum closed over the declared set** (the first hallucination lever); the
raw parsed hotspots are returned unchanged so the ingest mechanical diff can see
any divergence (Decision 3a).
"""

from __future__ import annotations

import base64
import json
import logging
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from learnarken.config import load_minimax_config

logger = logging.getLogger("learnarken")

VLM_MAX_RETRIES = 3  # flaky-channel retries (stop condition i); a 429 never retries
_BACKOFF_S = 2.0
_JITTER_S = 0.5  # de-synchronise bulk describe runs (red-team P3)
_THINK = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class VLMError(RuntimeError):
    """Transport failure: unreachable, HTTP error, upstream status. Fail closed."""


class VLMUnavailable(VLMError):
    """Flaky-channel misses exhausted the retry budget with no usable read.
    Ingest marks the figure undescribed; query second-look refuses (G15)."""


class VLMRateLimited(VLMError):
    """HTTP 429 — the subscription ceiling (Decision 1 ii). Terminal, no retry."""


class Part(BaseModel):
    part_number: str
    name: str = ""


class Hotspot(BaseModel):
    id: str
    label: str = ""


class FigureDescription(BaseModel):
    """Controlled structured description (部件清单 / Hotspot 标号 / 安全警告).

    `extra` is left tolerant on purpose: this models the OUTPUT of an external,
    uncontrolled VLM channel — a chatty model adding a stray key should not turn
    a good read into a flaky miss. Our own committed records (FigureRecord) are
    strict (`extra='forbid'`)."""

    summary: str = ""
    parts: list[Part] = []
    hotspots: list[Hotspot] = []
    safety_warnings: list[str] = []
    reads_text: list[str] = []
    refused: bool = False

    def hotspot_ids(self) -> set[str]:
        return {h.id for h in self.hotspots}


@dataclass
class _RawCall:
    content: str
    usage: dict
    model: str


def _system_prompt(declared_hotspots: set[str]) -> str:
    enum = ", ".join(sorted(declared_hotspots)) or "(none declared)"
    return (
        "You are a maintenance-illustration reader for S1000D technical figures. "
        "Read ONLY what is visibly present in the image. Return a single JSON "
        "object with exactly these keys: "
        '"summary" (string), '
        '"parts" (array of {"part_number","name"}), '
        '"hotspots" (array of {"id","label"}), '
        '"safety_warnings" (array of strings), '
        '"reads_text" (array of the exact text strings you can read in the image), '
        '"refused" (boolean). '
        f"Hotspot ids MUST be drawn only from this closed set: [{enum}]. Do not "
        "invent hotspot ids. If you cannot read the image, set refused=true and "
        "leave the arrays empty. Output JSON only, no prose."
    )


def _build_payload(
    system: str, question: str | None, png_bytes: bytes, *, temperature: float, max_tokens: int
) -> dict:
    data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode()
    user_text = (
        f"Question to answer from the figure: {question}" if question else "Describe this figure."
    )
    return {
        "model": load_minimax_config()["MINIMAX_MODEL_NAME"],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
    }


def _build_request(payload: dict) -> urllib.request.Request:
    config = load_minimax_config()
    url = config["MINIMAX_API_URL"].rstrip("/") + "/chat/completions"
    return urllib.request.Request(  # noqa: S310 — https enforced by the config loader
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['MINIMAX_API_KEY']}",
            "X-Proxy-Token": config["MINIMAX_API_PROXY_TOKEN"],
        },
        method="POST",
    )


def _strip(content: str) -> str:
    stripped = _THINK.sub("", content, count=1)
    fenced = _FENCE.match(stripped)
    return fenced.group(1) if fenced else stripped


def _one_call(payload: dict, timeout: int) -> _RawCall:
    """A single HTTP round-trip. Raises VLMRateLimited on 429 (terminal),
    VLMError on transport/upstream failure. Returns raw content otherwise."""
    request = _build_request(payload)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise VLMRateLimited("VLM subscription ceiling (HTTP 429)") from exc
        raise VLMError(f"VLM HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise VLMError(f"VLM unreachable: {exc}") from exc
    except json.JSONDecodeError as exc:
        # A malformed HTTP-200 body (HTML, truncated JSON) must fail closed as a
        # transport error, never crash the caller (red-team P2).
        raise VLMError(f"VLM 200 body is not JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise VLMError(f"VLM 200 body is not a JSON object: {type(body).__name__}")
    status = body.get("base_resp", {}).get("status_code")
    if status not in (0, None):
        # Some proxies signal rate limiting via base_resp rather than HTTP 429.
        if status in (1002, 1008, 429):
            raise VLMRateLimited(f"VLM rate limited (base_resp.status_code={status})")
        raise VLMError(f"VLM base_resp.status_code={status}: {body.get('base_resp')}")
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VLMError(f"unexpected VLM response shape: keys={sorted(body)}") from exc
    return _RawCall(content=content, usage=body.get("usage", {}), model=body.get("model", ""))


def _parse(content: str) -> FigureDescription | None:
    """Parse one raw content into a FigureDescription, or None if it is a
    flaky-channel miss.

    JSON is attempted FIRST: the unstable channel's "I don't see an image" reply
    is prose, not JSON, so it fails to parse and is correctly treated as a miss —
    while a *valid* description whose summary happens to contain the words "no
    image" is NOT discarded (host red-team: a phrase check over the whole payload
    would drop legitimate reads)."""
    stripped = _strip(content).strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None  # non-JSON prose (incl. the "no image" reply) = flaky miss
    if not isinstance(parsed, dict):
        return None
    try:
        return FigureDescription.model_validate(parsed)
    except ValidationError:
        return None


def describe_figure(
    png_bytes: bytes,
    declared_hotspots: set[str],
    *,
    question: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    timeout: int = 120,
    max_retries: int = VLM_MAX_RETRIES,
) -> FigureDescription:
    """One schema-constrained VLM read of a figure, fail-closed.

    Retries flaky-channel misses up to `max_retries`; a 429 is terminal. Returns
    the raw parsed description (hotspot ids NOT filtered — ingest diffs them).
    Raises VLMUnavailable if every attempt was a flaky miss, VLMRateLimited on
    429, VLMError on transport/upstream failure.
    """
    payload = _build_payload(
        _system_prompt(declared_hotspots),
        question,
        png_bytes,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    for attempt in range(1, max_retries + 1):
        raw = _one_call(payload, timeout)  # VLMRateLimited / VLMError propagate (terminal)
        parsed = _parse(raw.content)
        if parsed is not None:
            return parsed
        if attempt < max_retries:
            logger.warning("VLM flaky read (attempt %d/%d); retrying", attempt, max_retries)
            time.sleep(_BACKOFF_S * attempt + random.uniform(0, _JITTER_S))  # noqa: S311
    raise VLMUnavailable(f"no usable VLM read after {max_retries} attempts (flaky channel)")
