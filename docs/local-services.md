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
| Query / feed port | `8080` |
| Config-server port | `19071` |
| Auth | none (local dev) |

```bash
# start (already done on 2026-07-14)
docker run -d --name learnarken-vespa --hostname vespa-container \
  -p 8080:8080 -p 19071:19071 vespaengine/vespa

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

## MiniMax API (embeddings — Day 4)

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

**Open technical item for Day 4** (not resolved today): the reference client
only implements **chat completions** (`{api_url}/chat/completions`) — it has
**no embedding endpoint**. So the embedding call must be written fresh. Two
shapes to verify against the live endpoint before Day 4 implementation:

1. OpenAI-compatible `POST {api_url}/embeddings` with `{model, input}` — if
   the proxy exposes it.
2. MiniMax-native embeddings (historically `POST /v1/embeddings` with a
   `GroupId` query param and body `{model, texts, type: "db"|"query"}`,
   where `db` vs `query` distinguishes indexing vs search vectors).

Which one applies is a Day 4 spec question; recorded here so the decision
(MiniMax as the embedding provider) is not lost. Day 3 makes **no** embedding
calls (BM25 only — see day3 spec Out of Scope).
