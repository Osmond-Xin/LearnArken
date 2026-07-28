# Vespa 调试请求集（VS Code REST Client）

用 REST Client 插件（`humao.rest-client`）直接点 **Send Request** 打 Vespa，
不用背 `curl` 参数。所有请求都对着本地 docker 容器 `learnarken-vespa`
（端口见 [local-services.md](../local-services.md)）。

## 文件

| 文件 | 用途 |
| --- | --- |
| [00-health.http](00-health.http) | 配置服务器 / 查询容器是否活着、部署了哪一代、节点状态、指标 |
| [01-documents.http](01-documents.http) | `/document/v1`：visit 列文档、按 id 取、手工喂一条、局部更新、删除 |
| [02-search.http](02-search.http) | `/search/` YQL：按 package / dmc / strategy / 告警 / 适用性过滤，grouping 统计，trace |
| [03-dense-search.http](03-dense-search.http) | `nearestNeighbor` 向量检索（需要先生成 payload） |

## 前置

**"connection was rejected" 基本都是容器没起**（它会被 docker OOM 杀掉，
`docker ps -a` 里显示 `Exited (137)`）：

```bash
docker ps -a --filter name=learnarken-vespa    # 先看死没死
docker start learnarken-vespa                  # 起容器
curl -s http://localhost:19071/state/v1/health   # 配置服务器，约 10s 后 up
curl -s http://localhost:8080/state/v1/health    # 查询容器，约 30s 后 up
```

19071 先活、8080 后活，中间那段时间 8080 也会 connection refused —— 等满 30 秒再发。

`8080` 在应用包部署前不应答。`uv run learnarken index samples/package-a` 在检测到
8080 未应答时会自己调 `vespa.deploy()`（[retrieval/\_\_init\_\_.py:248](../../src/learnarken/retrieval/__init__.py#L248)）；
只想部署不喂数据就 `uv run python -c "from learnarken import vespa; vespa.deploy()"`。

## 向量检索为什么要先跑脚本

rank-profile `dense` 的输入是 `tensor<float>(x[4096])` —— 4096 个浮点数没法手写。
先生成请求体：

```bash
uv run python tools/gen_vespa_query.py "engine oil servicing" --package package-a --top-k 10
# -> var/http/dense-search.json（git-ignored）
```

[03-dense-search.http](03-dense-search.http) 里用 `< ../../var/http/dense-search.json`
把它当请求体发出去。换查询词就重跑脚本再 Send。
首次会加载本地 Qwen3-Embedding-8B，比较慢；之后有缓存。

## 这个 schema 上容易踩的坑

- **`text` 不能用来过滤**。`text` / `dm_title` / `issue_info` / `applic_display` /
  `security_classification` / 日期字段都只有 `summary`，没有 index/attribute，
  写 `where text contains "..."` 会直接报错。BM25 在 Python 侧
  （[src/learnarken/retrieval/](../../src/learnarken/retrieval/)），Vespa 这里只当稠密向量库用。
- **能过滤的字段**：`chunk_id`、`dmc`、`package`、`chunk_type`、`source_path`、
  `strategy`、`has_warning`、`has_caution`、`outbound_dm_refs`、`icn_refs`、
  `applic_properties`、`applic_values`。
- **DMC 不会被拆**：`dmc` 是 `match: word`，
  `dmc contains "DMC-LA100-A-29-10-00-00A-520A-A"` 要写全，不能按 `-` 分片匹配。
- **YQL 用 POST 发**。GET 的 `?yql=` 要手工百分号编码空格，可读性差；只有
  `count()` 那种固定查询值得用 GET（见 `vespa/store.py` 的 `count()`）。
- **过滤类查询加 `"ranking": "unranked"`**，否则会白算一遍打分。
- **`embedding` 查不出来**：schema 里它没有 `summary`，`/search/` 永远不返回；
  要确认向量在不在，走 `/document/v1/.../docid/<id>`。
- **删除是真删**：`01-documents.http` 底部两条 DELETE 会清空索引，删完要重新
  `uv run learnarken index samples/package-a`。

## 可选：把主机名抽成环境变量

REST Client 支持环境切换。`.vscode/` 在本仓库是 git-ignored，所以这段自己贴到
`.vscode/settings.json` 即可（Day 10 云上部署那套地址填进 `deployed`）：

```json
{
  "rest-client.environmentVariables": {
    "local":    { "query": "http://localhost:8080", "config": "http://localhost:19071" },
    "deployed": { "query": "https://<your-host>:8080", "config": "https://<your-host>:19071" }
  }
}
```

之后把 .http 文件里的 `@query = ...` 那行删掉，用 `Ctrl/Cmd+Alt+E` 切环境。

## 验证状态

2026-07-23 对着本地 45 chunk 的 package-a 索引实跑过一遍：00/01/02 每一条请求
（含 feed→update→delete 往返）和 03 的向量检索链路都返回 200 且结果符合预期。
唯一不可达的是集群控制器 `/cluster/v2/`（在 19050，容器没映射到宿主机），
已在 00-health.http 里改成 `docker exec` 的写法。

## 参考

- schema：[chunk.sd](../../src/learnarken/vespa/app/schemas/chunk.sd)
- 服务配置：[services.xml](../../src/learnarken/vespa/app/services.xml)
- Python 侧唯一知道 Vespa 存在的模块：[store.py](../../src/learnarken/vespa/store.py)
- 端口 / 容器：[local-services.md](../local-services.md)
