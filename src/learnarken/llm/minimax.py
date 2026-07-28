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

import http.client
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass

from learnarken.config import load_minimax_config

logger = logging.getLogger("learnarken")

_THINK = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)
_RETRIES = 3
_BACKOFF_S = 2.0

#: Completion budget for one answer call. It covers the think block *and* the
#: JSON, and M3's think block is the dominant term: measured live on the day-6
#: query path (2026-07-27, `samples/package-{a,c}`), one question alone ranged
#: over 1888 / 1467 / 3464 / 7305 completion tokens across repeats at
#: temperature 0 — think blocks of 497 to 27,102 characters. The former 2048
#: truncated mid-think, and truncation surfaced as `post-think content is not
#: JSON: ''` — a refusal the operator could not distinguish from a genuine
#: model failure. 16384 covers every observed run with headroom; billing is on
#: tokens actually produced, so the headroom is only spent when it is used.
_MAX_TOKENS = 16384

#: Socket timeout for one completion. Tied to `_MAX_TOKENS`: the measured
#: 7305-token run took 89 s wall-clock on the day-6 query path (2026-07-27), so
#: the full budget needs roughly 200 s. At the old 120 s a slow-but-valid
#: completion timed out — and in the non-streaming client a timeout is retried,
#: so the same generation would have been paid for up to three times.
_TIMEOUT_S = 300

#: Cap on a non-streaming response body. A full 16384-token completion is well
#: under 1 MiB of JSON; the cap exists so an endless HTTP 200 body cannot be
#: read into memory (round 8 P1). Over the cap the body is truncated and fails
#: the contract parse — fail closed, not OOM.
_MAX_BODY_BYTES = 8 * 1024 * 1024

#: Cap on the content a single streamed completion may accumulate. `max_tokens`
#: bounds what the *model* produces; this bounds what the *transport* will hold
#: if the peer ignores that (round 9 P1). Comfortably above a 16384-token
#: completion, which measured under 30 k characters.
_MAX_CONTENT_CHARS = 4 * 1024 * 1024


class LLMError(RuntimeError):
    """Transport failure: unreachable, HTTP error, upstream status. Exit 1."""


class LLMContractError(LLMError):
    """The model replied but violated the JSON contract (unparseable / wrong
    shape). This is a *refusal* condition, not a transport error — the answer
    layer maps it to `refuse("llm-contract")`, exit 3 (red-team day5 #3).

    `retryable` marks a failure worth asking again. Here that is one thing: M3
    closing its think block a token late, which leaves the body unparseable and
    recurs at about 2 runs in 24. It is **not** set for a completion the service
    cut short (`length`) or declined (`content_filter`, any non-`stop` reason),
    nor for an *envelope* of the wrong shape — more than one choice, a non-object
    body — because re-asking those spends a second full generation on an outcome
    that will not change, or asks again after upstream already declined
    (red-team 2026-07-28 P1).

    The answer layer raises its own retryable `LLMContractError` when the
    *answer object* is malformed (a key with stray whitespace, say); that is a
    generation glitch rather than an upstream verdict. See
    `answer/engine.py::generate_well_shaped`.
    """

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class ChatResult:
    parsed: dict  # the post-think JSON object
    raw_content: str  # exact content as returned (think block included)
    model: str
    usage: dict
    request_payload: dict  # exact payload sent (for the answer trace)


def _remaining(deadline: float) -> float:
    """Seconds left before the whole-call deadline, never zero or negative.

    `timeout` is a per-socket idle timeout, so with retries the wall-clock cost
    of one call was `_RETRIES × timeout` — up to 15 minutes holding a demo
    concurrency slot (red-team round 5 P2). Attempts now share one deadline.
    """
    return max(1.0, deadline - time.monotonic())


#: HTTP statuses worth another attempt: overload and rate limiting. Everything
#: else 4xx is a client/auth fault that will fail identically on a retry.
_RETRYABLE_HTTP = frozenset({408, 429, 500, 502, 503, 504})


def _http_error(exc: urllib.error.HTTPError) -> LLMError:
    """Turn an HTTP error into an LLMError naming the status and nothing else.

    The error body is **not read at all**. Reading it capped the bytes but not
    the wall clock — a peer trickling 199 bytes over many minutes would hold
    the generation slot right through the shared deadline (round 9 P1) — and
    the excerpt was never usable anyway: an upstream body can echo the request
    (prompt, evidence, auth diagnostics) and the API forwards LLMError text to
    the demo visitor (round 8 P2). The status is the actionable part.
    """
    exc.close()
    return LLMError(f"MiniMax chat HTTP {exc.code}")


def _sleep_within(deadline: float, seconds: float) -> None:
    """Back off, but never past the deadline the attempts share (round 6 P3)."""
    time.sleep(max(0.0, min(seconds, deadline - time.monotonic())))


@contextmanager
def _closed_at(response, deadline: float):
    """Close `response` when the deadline passes, whatever it is doing.

    A socket timeout is an *idle* timeout and the per-line deadline check only
    runs between lines, so a peer trickling bytes without a newline could hold
    the read — and a demo concurrency slot — indefinitely (round 8 P1). Closing
    the response from a watchdog thread makes the blocked read raise, which the
    caller already treats as a transport failure.
    """
    watchdog = threading.Timer(max(0.0, deadline - time.monotonic()), response.close)
    watchdog.daemon = True
    watchdog.start()
    try:
        yield
    finally:
        watchdog.cancel()


def _check_finish_reason(reason: str | None, max_tokens: int) -> None:
    """A completion the service cut short is a contract failure, and must say
    why — the truncated remainder is otherwise reported as unparseable JSON.

    Checked before the empty-content test, so a terminal chunk that carries the
    reason but no deltas still reports the actionable half (red-team round 4
    P2). The completion must *positively* report `stop`: a missing terminal
    reason means the stream ended without the service saying it was finished,
    which is indistinguishable from a truncated one (round 6 P1). Verified live
    2026-07-27 — both the streaming and non-streaming paths report `'stop'`.
    """
    if reason == "length":
        raise LLMContractError(
            f"completion truncated at the max_tokens budget ({max_tokens}) before "
            "the JSON contract was complete — raise the budget or shorten the prompt"
        )
    if reason != "stop":
        # Logged as well as raised: if a proxy upgrade starts reporting a
        # synonym for "done", this is the signal that says so — the allowlist
        # is widened after seeing it live, never pre-emptively (round 5 P3).
        logger.warning("unexpected terminal finish_reason=%r (refusing)", reason)
        raise LLMContractError(f"completion ended with finish_reason={reason!r}, not 'stop'")


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _strip_think(content: str) -> str:
    """Remove the <think> block and any markdown code fence around the JSON.

    Both observed live: the think prefix always; the ```json fence appears on
    longer prompts even with response_format json_object set.
    """
    stripped = _THINK.sub("", content, count=1)
    fenced = _FENCE.match(stripped)
    return fenced.group(1) if fenced else stripped


def _build_payload(
    system: str, user: str, *, temperature: float, max_tokens: int, stream: bool
) -> dict:
    payload = {
        "model": load_minimax_config()["MINIMAX_MODEL_NAME"],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if stream:
        payload["stream"] = True
    return payload


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


def _parse_contract(content: str) -> dict:
    """Shared contract tail: strip think/fence, require a JSON object.

    M3 sometimes closes `</think>` a token late, stranding the JSON's opening
    brace inside the block. A salvage that re-spliced the object across that
    boundary was written and then **removed**: three review rounds each broke
    the narrowing (rounds 5, 8 and 9, twice with working payloads), because the
    reasoning text is attacker-reachable — an uploaded data module becomes
    evidence in the prompt — and any rule that reconstructs a contract from it
    is a rule an attacker can satisfy. Measured, the salvage rescued about one
    run in forty. Refusing that run is the cheaper trade, and it is what INV-4
    asks for anyway.
    """
    stripped = _strip_think(content)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        # The one retryable class: a late `</think>` swallows the start of the
        # body, so it does not parse. Asking again usually lands a clean one.
        raise LLMContractError(
            f"post-think content is not JSON: {stripped[:120]!r}", retryable=True
        ) from exc
    if not isinstance(parsed, dict):
        raise LLMContractError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = _MAX_TOKENS,
    timeout: int = _TIMEOUT_S,
) -> ChatResult:
    """One chat call constrained to a JSON object. Raises LLMError on any failure.

    A read timeout here is retried up to `_RETRIES` times, so a completion that
    is merely *slow* is billed once per attempt — which is why `_TIMEOUT_S`
    tracks the completion budget rather than staying at the old 120 s, and why
    all attempts share one wall-clock deadline.
    """
    config = load_minimax_config()
    payload = _build_payload(
        system, user, temperature=temperature, max_tokens=max_tokens, stream=False
    )
    request = _build_request(payload)
    body: dict | None = None
    deadline = time.monotonic() + timeout
    for attempt in range(1, _RETRIES + 1):
        try:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=_remaining(deadline)
            ) as response:
                with _closed_at(response, deadline):
                    raw = response.read(_MAX_BODY_BYTES)
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError as exc:
                    # HTTP 200 carrying a WAF/proxy HTML page: the service
                    # answered, so this is a contract failure like any other
                    # unparseable response, not a transport error (round 7 P2).
                    raise LLMContractError("response body is not JSON") from exc
                if not isinstance(body, dict):
                    # A JSON array/string/number would sail past every
                    # `body.get(...)` below as an opaque internal error
                    # instead of a refusal (round 8 P2).
                    raise LLMContractError(
                        f"expected a JSON object body, got {type(body).__name__}"
                    )
            break
        # HTTPError subclasses URLError, so it must be caught first or the
        # retry clause swallows it and a 401 is reported as "unreachable"
        # after three attempts (round 6 P2). Only overload/rate-limit statuses
        # are worth another attempt; an auth or request fault will fail the
        # same way three times (round 7 P2).
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRYABLE_HTTP or attempt == _RETRIES:
                raise _http_error(exc) from exc
            logger.warning("MiniMax chat HTTP %d (attempt %d); retrying", exc.code, attempt)
            if time.monotonic() >= deadline:
                raise _http_error(exc) from exc
            _sleep_within(deadline, _BACKOFF_S * attempt)
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            if attempt == _RETRIES or time.monotonic() >= deadline:
                raise LLMError(f"MiniMax chat unreachable ({attempt} attempts): {exc}") from exc
            logger.warning("MiniMax chat attempt %d failed (%s); retrying", attempt, exc)
            _sleep_within(deadline, _BACKOFF_S * attempt)
    assert body is not None
    status = body.get("base_resp", {}).get("status_code")
    if status != 0:
        # The diagnostic object can echo the request (prompt, evidence, auth
        # detail) and the API forwards LLMError text to the demo visitor, so
        # only the status code travels (round 9 P2).
        logger.warning("MiniMax base_resp: %r", body.get("base_resp"))
        raise LLMError(f"MiniMax base_resp.status_code={status}")
    # From here down the service answered; a bad shape/JSON is a *contract*
    # violation (refusal), not a transport error (red-team day5 #3).
    choices = body.get("choices")
    # The payload never asks for n>1, so anything but exactly one choice is a
    # response we did not request and cannot attribute (round 7 P3).
    if not isinstance(choices, list) or len(choices) != 1:
        raise LLMContractError(f"expected exactly one choice, got {len(choices or [])}")
    try:
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMContractError(f"unexpected response shape: keys={sorted(body)}") from exc
    _check_finish_reason(choices[0].get("finish_reason"), max_tokens)
    return ChatResult(
        parsed=_parse_contract(content),
        raw_content=content,
        model=body.get("model", config["MINIMAX_MODEL_NAME"]),
        usage=body.get("usage", {}),
        request_payload=payload,
    )


def _iter_stream_deltas(lines: Iterable[bytes], deadline: float) -> Iterable[tuple[str, dict]]:
    """Yield (delta_text, chunk) from OpenAI-style SSE lines.

    Probe findings (2026-07-17, docs/specs/day6.md): `text/event-stream`
    with `data: {chunk}` lines, content deltas in `choices[0].delta.content`
    (think block included), termination = `finish_reason: "stop"` then EOF —
    no `[DONE]` sentinel observed, but tolerated. `usage` is null in stream
    mode. A MiniMax-native error may still arrive as a `base_resp` object.

    `deadline` is checked per *raw line*, not per yielded chunk: an upstream
    that trickles SSE comments (`: ping`) forever keeps the socket busy and
    yields nothing, so a check further out never runs and the call would hold a
    demo concurrency slot indefinitely (red-team round 7 P1).
    """
    for raw in lines:
        if time.monotonic() >= deadline:
            raise LLMError("MiniMax chat stream exceeded its deadline mid-stream")
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if data == "[DONE]":
            return
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError as exc:
            raise LLMContractError(f"unparseable stream chunk: {data[:120]!r}") from exc
        status = chunk.get("base_resp", {}).get("status_code")
        if status not in (None, 0):
            logger.warning("MiniMax base_resp: %r", chunk.get("base_resp"))
            raise LLMError(f"MiniMax base_resp.status_code={status}")
        # The payload never asks for n>1, so a chunk carrying anything but one
        # choice is a response we did not request (round 8 P2 — the
        # non-streaming path already required this).
        choices = chunk.get("choices")
        if choices is None:
            yield ("", chunk)  # usage-only / keepalive chunk
            continue
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise LLMContractError(f"expected exactly one choice per chunk, got {choices!r:.80}")
        delta = choices[0].get("delta", {}).get("content")
        yield (delta or "", chunk)


def chat_json_stream(
    system: str,
    user: str,
    *,
    on_delta: Callable[[str], None],
    temperature: float = 0.0,
    max_tokens: int = _MAX_TOKENS,
    timeout: int = _TIMEOUT_S,
) -> ChatResult:
    """Streaming chat call: `on_delta` receives each raw content delta as it
    arrives; the completed content then goes through the exact same contract
    parse as `chat_json`. Retries cover connection setup only — once the
    first chunk has been forwarded, a mid-stream failure raises LLMError
    (fail closed) rather than silently re-asking and double-streaming.
    """
    config = load_minimax_config()
    payload = _build_payload(
        system, user, temperature=temperature, max_tokens=max_tokens, stream=True
    )
    deadline = time.monotonic() + timeout
    for attempt in range(1, _RETRIES + 1):
        request = _build_request(payload)
        started = False
        pieces: list[str] = []
        streamed = 0
        model = config["MINIMAX_MODEL_NAME"]
        usage: dict = {}
        finish_reason: str | None = None
        try:
            with (
                urllib.request.urlopen(  # noqa: S310
                    request, timeout=_remaining(deadline)
                ) as response,
                _closed_at(response, deadline),
            ):
                for delta, chunk in _iter_stream_deltas(response, deadline):
                    choices = chunk.get("choices")
                    if choices is None:
                        # A usage/keepalive frame carries no completion. It must
                        # not mark generation as started (that would disable the
                        # retry a connection reset still deserves) nor rename the
                        # model in the trace (round 9 P2).
                        continue
                    started = True
                    model = chunk.get("model", model)
                    usage = chunk.get("usage") or usage
                    reason = choices[0].get("finish_reason")
                    if delta:
                        # Content after the service said it was done is not part
                        # of a completion we can vouch for (round 7 P2).
                        if finish_reason is not None:
                            raise LLMContractError(
                                f"content delta arrived after finish_reason={finish_reason!r}"
                            )
                        pieces.append(delta)
                        streamed += len(delta)
                        if streamed > _MAX_CONTENT_CHARS:
                            # Bounded before any gate runs: an upstream feeding
                            # deltas until the deadline would otherwise be an
                            # out-of-memory path (round 9 P1).
                            raise LLMContractError(
                                f"stream exceeded {_MAX_CONTENT_CHARS} content characters"
                            )
                        on_delta(delta)
                    if reason is not None:
                        finish_reason = reason
            _check_finish_reason(finish_reason, max_tokens)
            content = "".join(pieces)
            if not content:
                raise LLMContractError("stream ended with no content deltas")
            return ChatResult(
                parsed=_parse_contract(content),
                raw_content=content,
                model=model,
                usage=usage,
                request_payload=payload,
            )
        except urllib.error.HTTPError as exc:
            if started or exc.code not in _RETRYABLE_HTTP or attempt == _RETRIES:
                raise _http_error(exc) from exc
            logger.warning("MiniMax stream HTTP %d (attempt %d); retrying", exc.code, attempt)
            if time.monotonic() >= deadline:
                raise _http_error(exc) from exc
            _sleep_within(deadline, _BACKOFF_S * attempt)
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            if started or attempt == _RETRIES or time.monotonic() >= deadline:
                where = "mid-stream" if started else f"({attempt} attempts)"
                raise LLMError(f"MiniMax chat stream failed {where}: {exc}") from exc
            logger.warning("MiniMax stream attempt %d failed (%s); retrying", attempt, exc)
            _sleep_within(deadline, _BACKOFF_S * attempt)
    raise AssertionError("unreachable")  # pragma: no cover
