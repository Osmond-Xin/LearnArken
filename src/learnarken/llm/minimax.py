"""MiniMax-M3 chat-completions client (Day 5, docs/specs/day5.md).

Shape verified by live probe (spec "Probe findings", 2026-07-16):
OpenAI-compatible `/chat/completions`, success = HTTP 200 AND
`base_resp.status_code == 0`, auth = Bearer + `X-Proxy-Token`.

**M3 always emits a `<think>…</think>` prefix in `content`** — even at
temperature 0 with `response_format: json_object` — and there is no separate
reasoning field, so the think block is stripped before JSON parsing. Any
parse failure raises: the answer layer treats an unparseable LLM response as
a refusal condition, never as prose to pass through (INV-4).
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from learnarken.config import load_minimax_config

logger = logging.getLogger("learnarken")

_THINK = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)
_RETRIES = 3
_BACKOFF_S = 2.0


class LLMError(RuntimeError):
    """Transport failure: unreachable, HTTP error, upstream status. Exit 1."""


class LLMContractError(LLMError):
    """The model replied but violated the JSON contract (unparseable / wrong
    shape). This is a *refusal* condition, not a transport error — the answer
    layer maps it to `refuse("llm-contract")`, exit 3 (red-team day5 #3)."""


@dataclass
class ChatResult:
    parsed: dict  # the post-think JSON object
    raw_content: str  # exact content as returned (think block included)
    model: str
    usage: dict
    request_payload: dict  # exact payload sent (for the answer trace)


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _strip_think(content: str) -> str:
    """Remove the <think> block and any markdown code fence around the JSON.

    Both observed live: the think prefix always; the ```json fence appears on
    longer prompts even with response_format json_object set.
    """
    stripped = _THINK.sub("", content, count=1)
    fenced = _FENCE.match(stripped)
    return fenced.group(1) if fenced else stripped


def chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    timeout: int = 120,
) -> ChatResult:
    """One chat call constrained to a JSON object. Raises LLMError on any failure."""
    config = load_minimax_config()
    payload = {
        "model": config["MINIMAX_MODEL_NAME"],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    url = config["MINIMAX_API_URL"].rstrip("/") + "/chat/completions"
    request = urllib.request.Request(  # noqa: S310 — https enforced by the config loader
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['MINIMAX_API_KEY']}",
            "X-Proxy-Token": config["MINIMAX_API_PROXY_TOKEN"],
        },
        method="POST",
    )
    body: dict | None = None
    for attempt in range(1, _RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                body = json.loads(response.read())
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == _RETRIES:
                raise LLMError(f"MiniMax chat unreachable ({_RETRIES} attempts): {exc}") from exc
            logger.warning("MiniMax chat attempt %d failed (%s); retrying", attempt, exc)
            time.sleep(_BACKOFF_S * attempt)
        except urllib.error.HTTPError as exc:
            # 4xx is not transient; response bodies are truncated and never logged
            # with headers (they could echo the request).
            raise LLMError(f"MiniMax chat HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    assert body is not None
    status = body.get("base_resp", {}).get("status_code")
    if status != 0:
        raise LLMError(f"MiniMax base_resp.status_code={status}: {body.get('base_resp')}")
    # From here down the service answered; a bad shape/JSON is a *contract*
    # violation (refusal), not a transport error (red-team day5 #3).
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMContractError(f"unexpected response shape: keys={sorted(body)}") from exc
    stripped = _strip_think(content)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise LLMContractError(f"post-think content is not JSON: {stripped[:120]!r}") from exc
    if not isinstance(parsed, dict):
        raise LLMContractError(f"expected a JSON object, got {type(parsed).__name__}")
    return ChatResult(
        parsed=parsed,
        raw_content=content,
        model=body.get("model", config["MINIMAX_MODEL_NAME"]),
        usage=body.get("usage", {}),
        request_payload=payload,
    )
