# Local Services — Dev Environment Reference

> Connection and operation info for the docker services this project depends
> on, plus the external MiniMax API config. **No secrets in this file** —
> credential *values* live only in your local `.env` (git-ignored). This
> documents variable names, ports, and how to start/verify each service.
> Set up 2026-07-14 (Day 3 environment prep; see docs/specs/day3.md Q4).

## Vespa (vector database — Day 4 dense/hybrid retrieval)

| | |
| --- | --- |
| Container | `learnarken-vespa` |
| Image | `vespaengine/vespa:latest` |
| Query / feed port | `127.0.0.1:8080` |
| Config-server port | `127.0.0.1:19071` |
| Auth | none — which is why the ports are loopback-bound (red-team day4 #8) |

```bash
# start (recreated 2026-07-16 loopback-only: Vespa has no auth, so a 0.0.0.0
# bind would let any LAN process query, poison, or clear the index)
docker run -d --name learnarken-vespa --hostname vespa-container \
  -p 127.0.0.1:8080:8080 -p 127.0.0.1:19071:19071 vespaengine/vespa

# start / stop an existing container
docker start learnarken-vespa
docker stop  learnarken-vespa

# verify the config server is up
curl -s http://localhost:19071/state/v1/health   # -> {"status":{"code":"up"}}
```

> Note: port `8080` does **not** answer queries until an application package
> (schema) is deployed. That deployment is Day 4 work — today only the
> config server needs to be up. The `19071` health check is the readiness
> signal for Day 3 environment prep.

## Neo4j (graph store — Day 4 checkpoint, triple export)

| | |
| --- | --- |
| Container | `learnarken-neo4j` |
| Image | `neo4j:latest` (community 2026.06.0) |
| HTTP / Browser UI | `7474` → http://localhost:7474 |
| Bolt (drivers) | `7687` → `bolt://localhost:7687` |
| Credentials (local dev) | user `neo4j`, password `learnarken` |

```bash
# start (recreated 2026-07-16 loopback-only: Day 5 injects graph facts into
# the LLM prompt, so an open Neo4j is a prompt-poisoning surface — red-team
# day5 #7)
docker run -d --name learnarken-neo4j \
  -p 127.0.0.1:7474:7474 -p 127.0.0.1:7687:7687 \
  -e NEO4J_AUTH=neo4j/learnarken neo4j:latest

docker start learnarken-neo4j
docker stop  learnarken-neo4j

# verify auth + Cypher path
docker exec learnarken-neo4j cypher-shell -u neo4j -p learnarken 'RETURN 1 AS ok;'
```

> Credentials are read from the repo-root `.env` (`NEO4J_USER` /
> `NEO4J_PASSWORD`, see `.env.example`), falling back to the documented
> `neo4j/learnarken` dev pair. The ports are loopback-bound because Neo4j has
> no network auth beyond that password; treat the graph as writable-by-anyone
> who reaches the port.

## MiniMax API — chat (Day 5 answer generation, ACTIVE)

> Day 5 ruling (docs/specs/day5.md decision 2): **MiniMax-M3 is the answer
> LLM**. The Day 4 adjudication retired MiniMax as an *embedding* provider
> only; chat/generation was not covered by that ruling.

Config: the same four `MINIMAX_*` variables below, in the **repo-root**
`.env` (git-ignored). The loader (`src/learnarken/config.py`) is hardened
per red-team day4 #7: repo-root only (never cwd), `MINIMAX_*` allowlist,
https enforced for any off-box host.

### Local-only mode — no data egress (added 2026-07-25, F-02)

The endpoint is OpenAI-compatible, so any loopback model server can replace the
remote provider. Before 2026-07-25 this was impossible in practice: the
https-only rule rejected `http://127.0.0.1:PORT/v1`, which is the URL every
local server has. The policy is now **https off-box, plaintext on loopback
only**, with the host parsed rather than prefix-matched.

```bash
# 1. serve any OpenAI-compatible chat model on loopback, e.g. llama.cpp:
llama-server -m <model>.gguf --port 8080 --host 127.0.0.1

# 2. point the repo-root .env at it (any placeholder key/token; a local
#    server ignores them, and the allowlist still requires the four keys)
#    MINIMAX_API_URL=http://127.0.0.1:8080/v1
#    MINIMAX_MODEL_NAME=<whatever the server reports>

# 3. arm the egress fence — a non-loopback endpoint now raises instead of
#    being called, on every path that resolves config (chat, VLM, eval,
#    API health, demo preflight)
export LEARNARKEN_LOCAL_ONLY=1
```

Verify the fence without a model (it fails before any network call):

```bash
LEARNARKEN_LOCAL_ONLY=1 uv run python -c \
  "from learnarken.config import load_minimax_config; load_minimax_config()"
# ConfigError: LEARNARKEN_LOCAL_ONLY=1 forbids the non-loopback endpoint ...
```

**What this does and does not buy.** With the fence armed and a loopback model
served, no repository content leaves the machine — that is the property the
"sovereignty" row in the README claims, and it is covered by tests in
`tests/test_day5_answer.py::TestConfigHardening` (loopback accepted; userinfo,
suffix and decimal-IP spoofs rejected; remote blocked under the fence). What is
**not** included: this repo bundles no local chat or VLM model, and no
end-to-end generation against a local server has been benchmarked here. The
fence is the guarantee; supplying the model is the deployment step.

**Chat endpoint facts** (live probe 2026-07-16, spec "Probe findings"):
OpenAI-compatible `/chat/completions`; success = HTTP 200 **and**
`base_resp.status_code == 0`; auth = Bearer + `X-Proxy-Token`. **M3 always
prefixes `content` with a `<think>…</think>` block**, and on longer prompts
wraps the JSON in a ```json fence even with `response_format: json_object` —
the client strips both before parsing.

## MiniMax API (embeddings — RETIRED 2026-07-16)

> **Retired from the architecture** by the Day 4 adjudication
> (docs/reviews/day4.md Part 2): the bake-off measured a length bias strong
> enough to invert relevance (docs/notes/day4-embedding-length-bias.md), and
> Qwen3-Embedding-8B (local) is now the sole dense provider. The client code
> lives at commit `b414fa4`; `tools/probe_length_bias.py` remains runnable
> stand-alone. Section kept for the historical record.

Provider for **embeddings** (Day 4 dense retrieval / semantic chunking).
Config pattern is reused from the FollowTheBig project
(`/Users/osmond/Documents/project/FollowTheBig`), whose MiniMax client is the
reference implementation.

**Environment variables** (values go in your local `.env`, never committed):

```bash
MINIMAX_API_URL=<base url, e.g. https://api.minimax.chat/v1>
MINIMAX_MODEL_NAME=<model name>
MINIMAX_API_KEY=<secret>
MINIMAX_API_PROXY_TOKEN=<secret; sent as the X-Proxy-Token header>
```

**The "special implementation" to carry over** (from FollowTheBig
`src/followthebig/utils/llm.py`):

- OpenAI-compatible HTTP client (`requests.post`), **plus a non-standard
  `X-Proxy-Token` header** carrying `MINIMAX_API_PROXY_TOKEN` alongside the
  usual `Authorization: Bearer <MINIMAX_API_KEY>`. This proxy-token header is
  the piece a stock OpenAI SDK would omit — it must be added manually.
- Retry with backoff (3 attempts, exponential) around the POST.

### Embedding endpoint — RESOLVED by live probe, 2026-07-15

The Day 3 open item ("the reference client only does chat completions; the
embedding call is new code, and its shape is unverified") is **closed**. A
probe against the live endpoint measured the following — these are facts, not
documentation claims:

| | |
| --- | --- |
| Shape | **MiniMax-native**, *not* OpenAI-compatible |
| Request | `POST {MINIMAX_API_URL}/embeddings` · body `{model, texts: [...], type: "db"｜"query"}` |
| Response | top-level **`vectors`** array (not `data[].embedding`); success = `base_resp.status_code == 0` |
| Model | **`embo-01`** — note `MINIMAX_MODEL_NAME` holds the *chat* model (`MiniMax-M3`); embeddings need their own model name, so a separate env var or constant is required |
| Dimension | **1536** |
| Vectors | **L2-normalized** (\|v\| = 1.000) ⇒ Vespa `distance-metric: prenormalized-angular`; cosine ≡ inner product |
| Auth | `Authorization: Bearer {MINIMAX_API_KEY}` **and** `X-Proxy-Token: {MINIMAX_API_PROXY_TOKEN}` — both required |
| `GroupId` | **not needed** — the proxy handles it (upstream MiniMax CN requires it as a query param; our base URL is a proxy) |

**`type` is a real asymmetric-encoding switch** (measured): embedding the same
string with `type="db"` vs `type="query"` yields vectors at **cosine 0.860**,
not 1.0. Index with `db`, search with `query` — mixing them degrades recall
silently, with no error. This is the single highest-value finding of the Day 4
probe.
