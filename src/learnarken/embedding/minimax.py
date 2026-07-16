"""MiniMax embedding client (Day 4a, docs/specs/day4.md).

Written from a live probe of the endpoint (2026-07-15), not from documentation
— the published descriptions disagreed with each other. Measured facts:

- shape is MiniMax-native `{model, texts, type}`, NOT OpenAI's `{model, input}`;
- the response carries a top-level `vectors` array, and HTTP 200 does not mean
  success — `base_resp.status_code == 0` does;
- `embo-01`, 1536 dimensions, vectors arrive L2-normalized;
- both `Authorization: Bearer` and the non-standard `X-Proxy-Token` are
  required (the base URL is a proxy; `GroupId` is handled upstream);
- `type` really does change the vector — the same text as "db" vs "query"
  gives cosine 0.860, not 1.0.

**Known defect, measured 2026-07-16** (docs/notes/day4-embedding-length-bias.md):
this model is strongly length-biased. Repeating a sentence verbatim — meaning
unchanged, length doubled — drops its similarity to a query from 0.76 to 0.58,
and an irrelevant 12-word chunk out-scores the correct 20-word answer (0.45 vs
0.29). The vendor-documented pairing (index=db, search=query) also measures
*worse* than using "query" for both. Callers must not read a low dense score as
low relevance without accounting for chunk length; the callers' fix is the
hybrid path, not this module.

Fail-closed (INV-4): every failure raises. Nothing here ever returns a
zero vector, a partial batch, or a silently-degraded result.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Literal

import requests

from learnarken.config import load_env

logger = logging.getLogger("learnarken")

MODEL = "embo-01"
DIMENSION = 1536

# The API rejects oversized batches; the probe ran singles. Keep batches modest
# and let the caller chunk large corpora.
MAX_BATCH = 32
TIMEOUT = 30
RETRIES = 3
BACKOFF = 2.0

EmbedMode = Literal["db", "query"]


class EmbeddingError(RuntimeError):
    """The embedding call failed. Callers must not proceed without vectors."""


class MiniMaxEmbedder:
    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        proxy_token: str | None = None,
        model: str = MODEL,
    ) -> None:
        load_env()
        self.api_url = (api_url or os.getenv("MINIMAX_API_URL") or "").rstrip("/")
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY")
        # Non-standard header a stock OpenAI SDK would omit; our base URL is a proxy.
        self.proxy_token = proxy_token or os.getenv("MINIMAX_API_PROXY_TOKEN")
        self.model = model

        missing = [
            name
            for name, value in (
                ("MINIMAX_API_URL", self.api_url),
                ("MINIMAX_API_KEY", self.api_key),
            )
            if not value
        ]
        if missing:
            raise EmbeddingError(
                f"missing MiniMax configuration: {', '.join(missing)}. "
                "Set them in your local .env (never commit values)."
            )

    @property
    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.proxy_token:
            headers["X-Proxy-Token"] = self.proxy_token
        return headers

    def embed(self, texts: list[str], mode: EmbedMode) -> list[list[float]]:
        """Embed texts. `mode` picks the asymmetric encoding — see module docstring."""
        if mode not in ("db", "query"):
            raise ValueError(f'mode must be "db" or "query", got {mode!r}')
        if not texts:
            return []
        if any(not t.strip() for t in texts):
            raise EmbeddingError("refusing to embed blank text (fail-closed, INV-4)")

        vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH):
            batch = texts[start : start + MAX_BATCH]
            vectors.extend(self._post(batch, mode))
        return vectors

    def _post(self, batch: list[str], mode: EmbedMode) -> list[list[float]]:
        payload = {"model": self.model, "texts": batch, "type": mode}
        url = f"{self.api_url}/embeddings"
        last_error = ""

        for attempt in range(1, RETRIES + 1):
            try:
                response = requests.post(url, headers=self._headers, json=payload, timeout=TIMEOUT)
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                last_error = self._error_of(response)
                if not last_error:
                    return self._vectors_of(response.json(), len(batch))
            if attempt < RETRIES:
                delay = BACKOFF ** (attempt - 1)
                logger.warning(
                    "MiniMax embed attempt %d failed (%s); retrying in %.0fs",
                    attempt,
                    last_error,
                    delay,
                )
                time.sleep(delay)

        raise EmbeddingError(f"MiniMax embed failed after {RETRIES} attempts: {last_error}")

    @staticmethod
    def _error_of(response: requests.Response) -> str:
        """Return an error string, or "" when the call really succeeded.

        HTTP 200 is not success on its own: MiniMax reports failures in
        `base_resp.status_code`, so a 200 with status_code != 0 is an error.
        """
        if response.status_code != 200:
            return f"HTTP {response.status_code}: {response.text[:200]}"
        try:
            body = response.json()
        except ValueError:
            return f"non-JSON response: {response.text[:200]}"
        base = body.get("base_resp") or {}
        if base.get("status_code", 0) != 0:
            return f"base_resp {base.get('status_code')}: {base.get('status_msg')}"
        return ""

    @staticmethod
    def _vectors_of(body: dict, expected: int) -> list[list[float]]:
        vectors = body.get("vectors")
        if not isinstance(vectors, list) or len(vectors) != expected:
            got = len(vectors) if isinstance(vectors, list) else type(vectors).__name__
            raise EmbeddingError(f"expected {expected} vectors, got {got}")
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != DIMENSION:
                raise EmbeddingError(
                    f"expected {DIMENSION}-dim vectors, got "
                    f"{len(vector) if isinstance(vector, list) else type(vector).__name__}"
                )
        return vectors


def embed(texts: list[str], mode: EmbedMode) -> list[list[float]]:
    """Convenience wrapper building an embedder from the environment."""
    return MiniMaxEmbedder().embed(texts, mode)
