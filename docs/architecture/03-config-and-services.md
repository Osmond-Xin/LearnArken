# 03 · 配置全景：工具链、本地服务与外部 API

> **AI-drafted，待人审**。快照：2026-07-21（`v1.3.0`；沿用 2026-07-18 / `v1.0.0`
> 撰写）。**Day 11–13 的配置增量很小**：(a) Day 12 多模态 VLM **复用同一 MiniMax
> 代理**（`MINIMAX_*` 四键，仅换成多模态 `content` 数组打 `/chat/completions`，
> **无新增环境变量/服务**，见 §4）；(b) 运行时依赖 Day 8 加 `scikit-learn`、Day 12
> 加 `pillow`（现 16 个，§5 的"仅 4 个依赖"是 Day 1 起步值的历史陈述）；Day 11
> 图谱第三路复用既有 Neo4j、Day 13 零新增依赖/服务（numba/Rust 证据门未开，
> [ADR-0003](../adr/0003-day13-rust-gate.md)）。密钥值一律不出现在仓库（只在本地
> `.env`，git-ignored）；本文只记录变量名、端口与拓扑。本地服务操作细节的权威文档是
> [docs/local-services.md](../local-services.md)，部署操作的权威文档是
> [deploy/DEPLOY-GUIDE.zh.md](../../deploy/DEPLOY-GUIDE.zh.md) 与
> [deploy/runbook.md](../../deploy/runbook.md)。

## 1. 配置拓扑图

```mermaid
flowchart LR
    subgraph DEV["开发机（本地）"]
        subgraph TOOL["工程工具链"]
            UV["uv + uv.lock<br/>依赖锁定"]
            RUFF["ruff<br/>lint + format"]
            PYTEST["pytest"]
            PC["pre-commit<br/>含 detect-private-key"]
        end
        CODE["learnarken 包<br/>Python 3.12"]
        ENV[".env（git-ignored）<br/>MINIMAX_* 四变量 + NEO4J_*"]
        subgraph DOCKER["docker（已接线）"]
            VESPA["learnarken-vespa<br/>:8080 查询/喂数据<br/>:19071 config server"]
            NEO["learnarken-neo4j<br/>:7474 HTTP/浏览器<br/>:7687 Bolt"]
        end
        subgraph DEMO["make demo（Day 6，loopback）"]
            API["FastAPI / uvicorn<br/>:8100 单 worker"]
            FE["Streamlit<br/>:8501 哑客户端"]
        end
    end

    subgraph CLOUD["外部"]
        GH["GitHub Actions CI<br/>uv sync --locked → lint → test"]
        MM["MiniMax-M3 chat API<br/>Bearer key + X-Proxy-Token"]
    end

    subgraph GCP["GCP（Day 10，按需）"]
        CF["Cloud Function gen2<br/>token 状态页 + instances.start"]
        VM["停机 VM（同 make demo 拓扑）<br/>:8501 Streamlit · :8110 状态 shim<br/>API 保持 loopback<br/>watchdog 30min 自关"]
    end

    CODE --- UV & RUFF & PYTEST
    PC -->|"提交前"| CODE
    CODE -->|push/PR| GH
    CODE -->|Day 4 稠密/混合| VESPA
    CODE -->|Day 5 图同步/注入| NEO
    ENV -->|Day 5 chat 生成| MM
    FE -->|"HTTP（哑客户端）"| API
    API --> CODE
    CF -->|"POST /api/start<br/>(token 门控)"| VM
```

## 2. 工程工具链配置

| 配置项 | 所在文件 | 要点 |
| --- | --- | --- |
| Python 版本 | pyproject.toml | `>=3.12`（StrEnum、新语法） |
| 依赖策略 | pyproject.toml + uv.lock | 运行时依赖 Day 1 起步 4 个 → 现 **16 个**（Day 4–6 langchain 全家 + ST + fastapi 栈、Day 8 scikit-learn、Day 12 pillow），全部带上界；CI `--locked` 安装。**理由**：解析器行为不许在未锁定安装下漂移（Day 2 红队裁决 #13） |
| ruff | pyproject.toml `[tool.ruff]` | py312 目标、100 列、规则集 E/F/I/UP/B/SIM |
| pytest | pyproject.toml `[tool.pytest.ini_options]` | testpaths=tests，`-q` |
| pre-commit | .pre-commit-config.yaml | ruff（--fix）+ ruff-format + 大文件/冲突/**私钥检测**/空白 |
| CI | .github/workflows/ci.yml | push(main) + PR 触发；action 按 commit SHA 固定 |
| 入口命令 | pyproject.toml `[project.scripts]` | `learnarken` → `cli:main`；子命令收口到 Day 10：`inspect`/`validate`/`dm`/`chunk`/`search`/`index`/`query`/`repair`/`eval retrieval`/`eval ablation`/`eval adversarial`/`graph impact` |
| Day 7 修复预算 | pyproject.toml `[tool.learnarken.repair]` | 迭代/token/no-progress 熔断、沙箱超时/内存、import 与 shell 白名单——版本化保证复现（INV-5），CLI flags 可覆盖 |
| 运行时依赖 | pyproject.toml | Day 4/5/6 增至含 langchain 全家 + sentence-transformers + fastapi/uvicorn/python-multipart，**全部带上界**；`streamlit` 在独立 `demo` 组、`httpx` 在 `dev` 组。CI 三处均 `--locked`（红队 day6 #10:锁文件是唯一事实源）|
| Day 6 一键 demo | Makefile `demo` → tools/run_demo.sh | fail-closed 预检 → uvicorn 单 worker → 轮询就绪(超时非零退出) → Streamlit |

## 3. 本地 docker 服务（Day 3 部署，Day 4–5 接线完成）

### Vespa — 向量数据库（稠密/混合检索）

| 项 | 值 |
| --- | --- |
| 容器名 | `learnarken-vespa`（镜像 `vespaengine/vespa:latest`） |
| 端口 | `8080` 查询/喂数据；`19071` config server |
| 鉴权 | 无（仅本地开发） |
| 就绪信号 | `curl -s localhost:19071/state/v1/health` → `up` |
| **当前状态** | ✅ **已接线**（Day 4）:应用包 `chunk.sd` schema 已部署,`index`/`search`/`query` 走稠密/混合检索;`verify_corpus` 用 `list_doc_ids` 校验 engine 与本地语料一致 |

### Neo4j — 图存储（三元组导出 / graph-RAG 备选）

| 项 | 值 |
| --- | --- |
| 容器名 | `learnarken-neo4j`（镜像 `neo4j:latest`，community 2026.06.0） |
| 端口 | `7474` HTTP/浏览器 UI；`7687` Bolt 驱动 |
| 凭证 | `neo4j` / `learnarken`（一次性本地开发口令，可留在文档；一旦暴露到 localhost 之外必须挪进 `.env`） |
| 验证 | `docker exec learnarken-neo4j cypher-shell -u neo4j -p learnarken 'RETURN 1;'` |
| 凭证来源 | `NEO4J_USER`/`NEO4J_PASSWORD` 走 `.env`（`.env.example` 已列） |
| **当前状态** | ✅ **已接线**（Day 5，ADR-0002）:`index` 时 `graph.sync` 幂等 upsert DM 节点 + dmRef/ICN 边;`query` 经 `graph.facts` 做接口③ 上下文注入。**Day 9 加多跳**:`graph impact` 反向依赖 BFS（限深+环去重+fail-closed）。 |

## 4. MiniMax-M3 chat API（Day 5 生成供应商）

环境变量（值只在本地 `.env`；`config.load_minimax_config` 只读 repo-root `.env`、
仅接受 `MINIMAX_*` 白名单、强制 https——红队 day4 #7 加固）：

| 变量 | 用途 |
| --- | --- |
| `MINIMAX_API_URL` | base url |
| `MINIMAX_MODEL_NAME` | 模型名（`MiniMax-M3`）|
| `MINIMAX_API_KEY` | `Authorization: Bearer` |
| `MINIMAX_API_PROXY_TOKEN` | **非标准 `X-Proxy-Token` 请求头**——库存 OpenAI SDK 不会带，必须手工加 |

**已探测形状**（specs/day5 Probe，2026-07-16）:OpenAI 兼容 `/chat/completions`,
成功 = HTTP 200 **且** `base_resp.status_code==0`;**M3 恒发 `<think>…</think>`
前缀**(即便 temp 0 + `response_format:json_object`),解析前剥除。**Day 6 补测流式**
(2026-07-17):`stream:true` 走 `text/event-stream`,delta 里含 think,无 `[DONE]`
哨兵,stream 模式 `usage` 为 null——`chat_json_stream` 据此实现。

**历史**:MiniMax 曾是 *embedding* 供应商候选,因实测长度偏置于 Day 4 裁决移除
(现默认 Qwen3-8B 本地);该裁决不覆盖 chat/生成——即本节 M3 所做。

## 5. Demo 服务（Day 6，`make demo`，均 loopback）

| 服务 | 端口 | 要点 |
| --- | --- | --- |
| FastAPI / uvicorn | `127.0.0.1:8100` | **单 worker**（本地嵌入/重排模型进程内常驻,多 worker 各加载一份炸内存）；路由 `def` 进线程池；`/health` `/upload` `/query`(SSE) |
| Streamlit | `127.0.0.1:8501` | 哑客户端,只 HTTP 打后端 |

安全边界（详见 [05-api-and-demo §5](05-api-and-demo.md)）:仅 loopback 绑定;
**CSRF Origin 门**守 `/upload` `/query`（server 端客户端无 Origin 头放行,浏览器
跨源 403）;上传 Content-Length 预检 + 2 MiB 上限 + `DMC-*.xml` 文件名服务端重铸;
`var/uploads/`（git-ignored）是上传落盘区,事务化 staging 在 `.staging/` 子目录。
loopback 前提下不做鉴权/限流/JWT;**公网模式（Day 10）** 另有两枚环境变量:
`DEMO_PUBLIC=1` 启用 demo_guard 围栏（LLM 配额/并发/上传闸）,`DEMO_GATE_KEY`
是 token 状态页发放给访客的共享门钥（后端校验 `X-Demo-Key` 头）。二者不设时
本地 demo 与测试行为零改变。

## 6. 配置层级与密钥红线

```text
仓库内（公开）          仓库内（文档）           本地（绝不入库）
├─ pyproject.toml      ├─ local-services.md    ├─ .env（MINIMAX_*/NEO4J_* 值）
├─ uv.lock             │   变量名/端口/命令      ├─ var/uploads/（demo 上传落盘）
├─ ci.yml              │   （无任何密钥值）       └─ 真实 S1000D 参考文件
├─ .env.example（形状） └─ 本目录（快照）              （samples/s1000d 非提交部分）
└─ .pre-commit（防线）
```

红线执行有三道机器防护：`.gitignore`（第一 commit 即配,含 `.env`/`var/`）、
pre-commit `detect-private-key`、以及"文档只记形状不记值"的写作纪律。
Day 10 部署侧同一纪律：`deploy/trigger/tokens.example.json` 只提交形状,真实
token 表与 SMTP 凭证只进 Cloud Function 环境变量。

## 7. Day 10 按需部署拓扑（GCP，选型 D）

选型与决策出处见 [04 §4.11](04-tech-selection.md) 与
[specs/day10](../specs/day10.md)。要点（操作权威在 deploy/ 两份文档）:

| 组件 | 形态 | 要点 |
| --- | --- | --- |
| 触发闸 | Cloud Function gen2（`deploy/trigger/`） | 邮件里的 token URL → 静态状态/导览页;`/api/start` 限流拉起停机 VM;点击与首次就绪各通知 Yi Xin 一封（邮件失败不破页面）|
| 演示 VM | 停机 GCP VM（`deploy/vm/`） | 开机即拉起**与 `make demo` 同一拓扑**的完整真栈（Vespa+Neo4j+本地嵌入/重排+MiniMax）——部署物=基准物,零 INV-5 口径漂移 |
| 公网暴露面 | 仅 `:8501`（Streamlit）与 `:8110`（状态 shim） | FastAPI 后端保持 loopback,Day 6 安全信封原样;shim 只 GET 代理 `/demo/status` 粗粒度布尔 |
| 费用围栏 | VM 内看门狗 + demo_guard + 预算警报 | 闲置 ≥30 min / 开机 ≥3 h / 自检失联 ⇒ 关机（歧义朝关机解）;demo_guard 拦 MiniMax 花费（GCP 账单看不见它）;$20 GCP 预算警报兜底 |
| 状态机 | closed / starting(带自检深度) / running(闲置倒计时) | 页面任何状态都有下一步动作;closed 态提供重启并诚实说明费用动机 |
