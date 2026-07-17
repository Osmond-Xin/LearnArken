"""Incremental `answer`-field extraction from a streaming M3 reply (Day 6).

The model streams `<think>…</think>` followed by the JSON envelope
(`is_answerable` → `answer` → `citations`, key order fixed by the prompt
contract). The demo must stream only the *answer text* — never the think
block or the JSON scaffolding — so this state machine skips the think
prefix, locates the `"answer": "` key, and decodes the string value as its
characters arrive, escape sequences included, even when a delta boundary
splits an escape (or a surrogate pair) in half.

Everything emitted here is pre-verification by design: the citation gate
can only run on the complete JSON, and a later `retract` event voids the
stream (SPEC day6 decision 3).
"""

from __future__ import annotations

import re

_KEY = re.compile(r'"answer"\s*:\s*"')
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_SIMPLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


class AnswerFieldExtractor:
    """Feed raw content deltas in; get newly decoded answer text out."""

    def __init__(self) -> None:
        self._buf = ""  # unconsumed raw text, or a pending partial escape
        self._state = "prelude"  # prelude → think → seek → string → done

    @property
    def done(self) -> bool:
        return self._state == "done"

    def feed(self, delta: str) -> str:
        if self._state == "done" or not delta:
            return ""
        self._buf += delta
        if self._state == "prelude":
            self._prelude()
        if self._state == "think":
            self._skip_think()
        if self._state == "seek":
            self._seek()
        if self._state == "string":
            return self._consume_string()
        return ""

    def _prelude(self) -> None:
        """Decide whether the stream opens with a think block."""
        head = self._buf.lstrip()
        if not head:
            return
        probe = head[: len(_THINK_OPEN)]
        if probe != _THINK_OPEN[: len(probe)]:
            self._state = "seek"  # no think block: seek over the full buffer
            return
        if len(probe) < len(_THINK_OPEN):
            return  # could still become "<think>" — wait for more bytes
        self._buf = head[len(_THINK_OPEN) :]
        self._state = "think"

    def _skip_think(self) -> None:
        end = self._buf.find(_THINK_CLOSE)
        if end == -1:
            # Inside the think block: discard, keeping only a tail long
            # enough to recognise a close tag split across deltas.
            self._buf = self._buf[-(len(_THINK_CLOSE) - 1) :]
            return
        self._buf = self._buf[end + len(_THINK_CLOSE) :]
        self._state = "seek"

    def _seek(self) -> None:
        match = _KEY.search(self._buf)
        if match is None:
            return
        self._buf = self._buf[match.end() :]
        self._state = "string"

    def _consume_string(self) -> str:
        text, self._buf = self._buf, ""
        out: list[str] = []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == '"':
                self._state = "done"
                break
            if ch != "\\":
                out.append(ch)
                i += 1
                continue
            decoded, consumed = self._decode_escape(text, i)
            if consumed == 0:  # escape split across deltas — wait for the rest
                self._buf = text[i:]
                break
            out.append(decoded)
            i += consumed
        return "".join(out)

    @staticmethod
    def _decode_escape(text: str, i: int) -> tuple[str, int]:
        """Decode one backslash escape at `text[i:]`; ("", 0) = incomplete."""
        if i + 1 >= len(text):
            return "", 0
        esc = text[i + 1]
        if esc != "u":
            return _SIMPLE_ESCAPES.get(esc, esc), 2
        if i + 6 > len(text):
            return "", 0
        try:
            code = int(text[i + 2 : i + 6], 16)
        except ValueError:
            return "�", 6
        if 0xD800 <= code <= 0xDBFF:  # high surrogate: need the \uXXXX pair
            if i + 12 > len(text):
                return "", 0
            if text[i + 6 : i + 8] == "\\u":
                try:
                    low = int(text[i + 8 : i + 12], 16)
                except ValueError:
                    return "�", 12
                if 0xDC00 <= low <= 0xDFFF:
                    pair = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                    return chr(pair), 12
            return "�", 6  # lone high surrogate: never emit (breaks UTF-8)
        if 0xDC00 <= code <= 0xDFFF:
            return "�", 6  # lone low surrogate
        return chr(code), 6
