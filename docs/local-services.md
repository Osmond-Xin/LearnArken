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
# start (already done on 2026-07-14)
docker run -d --name learnarken-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/learnarken neo4j:latest

docker start learnarken-neo4j
docker stop  learnarken-neo4j

# verify auth + Cypher path
docker exec learnarken-neo4j cypher-shell -u neo4j -p learnarken 'RETURN 1 AS ok;'
```

> The `learnarken` password is a throwaway local-dev credential, safe to
> keep in this doc. If Neo4j is ever exposed beyond localhost, move it to
> `.env` and pass `NEO4J_AUTH` from there.

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
