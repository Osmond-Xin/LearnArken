# 01 · 文件清单：每个文件在做什么

> **AI-drafted，待人审**。快照：2026-07-21，`main`（Day 1–13 全部合并，
> 打标至 `v1.3.0`）。行数为快照当日近似值，仅示意规模。**v1.3.0 补章**在 Day 11
> 图谱检索（§2.4）、Day 12 多模态（§2.10）、Day 13 性能与推理策略（§2.11）三处，
> 并回填 cli/tests/eval/docs 各表。

## 一、根目录：工程骨架（Day 1）

| 文件 | 职责 |
| --- | --- |
| [pyproject.toml](../../pyproject.toml) | 项目元数据与依赖单一事实源。运行时依赖现 16 个（Day 1 起步仅 4：defusedxml / lxml / pydantic / rank-bm25；Day 4–6 增至含 langchain 五件套、sentence-transformers、fastapi/uvicorn/python-multipart/requests；**Day 8 加 scikit-learn（Cohen's κ）、Day 12 加 pillow（合成 ICN 栅格）**；Day 13 零新增——numba/Rust 证据门未开），全部带上界 + `uv.lock` 锁定（Day 2 红队裁决 #13：解析器行为不许在未锁定安装下漂移）。注册 CLI 入口 `learnarken = learnarken.cli:main`。 |
| [.env.example](../../.env.example) | 本地 `.env` 的形状模板：`MINIMAX_*` 四变量 + `NEO4J_*`，只记形状不记值（安全红线）。 |
| [uv.lock](../../uv.lock) | 依赖锁文件，CI 用 `uv sync --locked` 安装，保证可复现（INV-5）。 |
| [Makefile](../../Makefile) | 四个入口：`make test`（pytest）、`make lint`（ruff check + format --check）、`make fmt`（自动修复）、`make demo`（Day 6 一键起后端+前端）。 |
| [llms.txt](../../llms.txt) | **Day 9 机器可读仓库地图**：给招聘方 AI agent 的入口——从这里 + EVIDENCE.md 出发，5 分钟内定位任一基准数字的复跑命令（specs/day9 验收口径）。 |
| [.pre-commit-config.yaml](../../.pre-commit-config.yaml) | 提交前钩子：ruff 检查/格式化 + 大文件/合并冲突/私钥泄漏/行尾空白检查。**detect-private-key 是安全红线的机器执行层**。 |
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | CI：锁定安装 → lint → test。action 全部按 commit SHA 固定（防供应链漂移）。 |
| [.gitignore](../../.gitignore) | 首个 commit 即配好：`.env`、密钥、缓存不入库（安全红线）。 |
| [README.md](../../README.md) / [README.zh-CN.md](../../README.zh-CN.md) | 对外门面：业务场景、AI-first 工作流说明、进度表、**基准表**（检索消融/bake-off 由 `gen_benchmark_tables.py` 从 artifact 生成;对抗评估/κ 数字同样指向冻结 artifact,均含复跑命令）、诚实分层 Roadmap、仓库导览。对外一律英文（中文版为镜像）。 |
| [CLAUDE.md](../../CLAUDE.md) | AI 实现方的操作规则：角色边界（SPEC 决策层人写、journal/裁决 AI 不碰）、自动红队闸、当日讨论纪要强制规则。 |

## 二、src/learnarken/ — 产品代码

### 2.1 核心解析与模型（Day 1–2）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [package.py](../../src/learnarken/package.py) | 166 | **Day 1 的轻量扫描器**：只解析 inspect 摘要表需要的字段（dmCode、标题、issueInfo、语言），直接读 XML 属性。含控制字符清洗（红队 #9：防标题里的 ANSI 序列污染终端）。是 `inspect` 命令的后端。 |
| [models.py](../../src/learnarken/models.py) | 175 | **Day 2 规范模型（Pydantic）**：DmCode、DataModule、PublicationModule、DML、DmRef/IcnRef、warning/caution、Applicability（displayText + 结构化断言双轨——断言给 Day 3 chunk 做机器过滤，displayText 给人读）。全仓库的"规范数据字典"。 |
| [loader.py](../../src/learnarken/loader.py) | 300 | **XML → 规范模型的装载器**：每个文件先过 defusedxml（L0 良构性 + 防实体炸弹），再由加固的 lxml（禁实体/DTD/网络）重解析拿行号、XPath、XSD 校验。含 fail-closed 文件大小上限（红队 #4：超限拒收而非耗尽内存）。 |
| [cli.py](../../src/learnarken/cli.py) | 915 | 命令行入口：Day 1–3 的 `inspect`/`validate`/`dm`/`chunk`/`search`/`eval retrieval`，Day 4 的 `index`（喂 Vespa）、`eval ablation`（四模式消融），Day 5 的 `query`（带引用问答:退出码 0 答/3 拒答/1 fail-closed/2 非包），Day 7 的 `repair`（默认 dry-run，`--apply` 人工闸），Day 8 的 `eval adversarial`，Day 9 的 `graph impact <DMC>`（反向依赖影响查询，`--depth` 1..N 默认 3）。**Day 11**：`eval ablation` 增 `--modes hybrid-graph / hybrid-graph-rerank`（图谱第三路，需 Neo4j；默认仍 Day 4 集不含图路，`run_ablation` 前置 `graph.is_up()` fail-closed）。Day 12/13 的多模态描述、性能/ToT 基准以脚本形式落在 `tools/`（见 §三），不新增 CLI 面。 |
| [config.py](../../src/learnarken/config.py) | — | `REPO_ROOT` 解析 + `load_minimax_config`：只读 repo-root `.env`、仅接受 `MINIMAX_*` 白名单、强制 https（红队 day4 #7 加固，Day 5 起用于 chat）。 |
| [schemas/learnarken.xsd](../../src/learnarken/schemas/learnarken.xsd) | — | 项目自造的**简化 XSD**（L1 结构校验层），对真实 S1000D schema 的玩具级替身（INV-7 诚实分层）。 |

### 2.2 validation/ — 四层校验器（Day 2）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [engine.py](../../src/learnarken/validation/engine.py) | 433 | 四层编排：L0 良构 → L1 mini-XSD → L2 单文件 BREX → L3 跨文件完整性（dmRef 悬空、ICN 缺失、版本错位、循环引用）。**Fail-closed 分层（INV-4）**：L0 挂的文件不进上层；L1 挂的跳过自身 L2 但仍作为 L3 图节点存在。**L3 的引用图是未来知识图谱（Neo4j）的地基**。 |
| [rules.py](../../src/learnarken/validation/rules.py) | 169 | L2 BREX 规则表：Schematron 风格的声明式断言（rule id、severity、描述、fix hint、检查函数），不引入 isoschematron 工具链。BREX-001 是诚实标注的玩具启发式（危险词词表代替真实业务规则，INV-7）。 |
| [report.py](../../src/learnarken/validation/report.py) | 58 | 四层共用的 Finding / ValidationReport Pydantic 模型（rule_id、layer、severity、file、line、path、message、fix_hint）。 |
| [parallel.py](../../src/learnarken/validation/parallel.py) | 61 | **Day 13 多进程分片适配器**（Decision 1，INV-2）：分片粒度 = 每 DM 文件（不是"复制 N 个包"制造假负载）。`analyze_package_sharded` 把文件列表切片→`perf.shard.run_sharded` 分发→worker 各自 `build_schema()` + `_process_file`（L0/L1/L2，`build_schema` 每进程建，lxml XMLSchema 不能跨进程共享）→主进程 `_merge_file_results` 跑 L3（需整包状态，是 Amdahl 串行分数）。结果**与单进程 `analyze_package` 逐字节等价**（Decision 1b，测试断言相等）；engine 为此拆出 `_process_file`/`_merge_file_results`/`FileResult` 供两条路径共用。诚实结论：玩具语料 CPU 不够重，mp 无加速（04 §4.14、ADR-0003）。 |

### 2.3 chunking/ — 结构感知分块（Day 3–4）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [base.py](../../src/learnarken/chunking/base.py) | 104 | Chunk 模型 + 元数据继承：chunk 从 Day 2 DataModule 继承 DMC、applicability（排除场合）、hazard 标志（紧急场合，见 discussions/day3 D4）、`outbound_dm_refs`/`icn_refs`（**图谱钩子**，D3 的"不许饿死未来图谱"义务）。chunk_id 确定性生成（内容哈希），复跑不变。 |
| [structure.py](../../src/learnarken/chunking/structure.py) | 113 | **结构感知策略（主力）**：沿文档自带的切线切——每个 procedural step 一块（行内 warning 折入并置 hazard 标志）、reqSafety 前置警告独立成块、前置条件/收尾各成块、描述节按 levelledPara 切。每块保留 XPath 锚点（golden set 按锚点标注）。 |
| [recursive.py](../../src/learnarken/chunking/recursive.py) | 74 | **递归字符窗口策略（对照组）**：故意结构盲，800 字符窗口 / 100 重叠，在词边界断开。存在的意义是让评估表**量化**结构感知值多少分。 |
| [semantic.py](../../src/learnarken/chunking/semantic.py) | 128 | **语义分块策略（Day 4a，spec Q5）**：Day 3 D1 承诺的第三策略，embedding 就位后交付。结构盲但按内容切——逐句嵌入、量邻句距离、在距离尖峰处断；断点取 DM 自身距离的 95 分位（自适应，不用固定余弦阈值）。唯一发网络调用的分块器，活体测试打 `integration` 标。 |
| [documents.py](../../src/learnarken/chunking/documents.py) | 30 | Chunk ⇄ LangChain `Document` 的**唯一转换点**（Day 4a，D13）：metadata 无损往返完整 Chunk（适用性/hazard/图谱钩子）。 |
| [\_\_init\_\_.py](../../src/learnarken/chunking/__init__.py) | 81 | `chunk_package` 入口：遍历包内 DM，按策略产出 chunk；复用 Day 2 loader，不重复解析。 |

### 2.4 retrieval/ — BM25 基线、稠密/混合检索、图谱第三路与评估（Day 3–4，Day 11 图谱增量）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [bm25.py](../../src/learnarken/retrieval/bm25.py) | 80 | **保标识符的分词器** + rank-bm25 薄封装（Day 4 起为 LC `BM25Retriever`）。核心洞察（教程 02 §1）：标准分析器会把 `DMC-LA100-…`、`P/N 1234-567` 在标点处打碎，标识符查询就被数字碎片淹没；把标识符保成整 token 是技术语料里单点杠杆最高的修复。 |
| [dense.py](../../src/learnarken/retrieval/dense.py) | — | **Day 4 稠密检索**：`VespaDenseRetriever`——查询向量走缓存 embedder，engine 侧按 package scope 过滤并 fail-closed 校验返回文档确在 scope 内（红队 day4 #5）。 |
| [hybrid.py](../../src/learnarken/retrieval/hybrid.py) | — | **Day 4 混合检索**：BM25 + 稠密的 RRF 融合（LC `EnsembleRetriever`）+ 交叉编码器重排（`bge-reranker-v2-m3`，本地，`_RERANKER_CACHE` 进程缓存）。`rerank_scored` 额外吐 top-1 分数——Day 5 拒答阈值门的信号源。**Day 11 加三路融合** `graph_hybrid_retriever`：BM25 + dense + **图谱扩展**三路等权 RRF（`weights=[1/3,1/3,1/3]`，`c=RRF_K=60`）——加第三路是唯一变量，重复到达的 chunk 由 RRF 按名次自然合并、无需专门 dedup。 |
| [entity_link.py](../../src/learnarken/retrieval/entity_link.py) | 144 | **Day 11 确定性查询侧实体链接**（spec §1）：纯 regex + 语料派生词典，**全路径无 LLM**（Key Decision 1）。三类实体——`dmc`（全码/裸码，裸码链到所有以它为后缀的 DMC）、`part`（**按词典成员判定**，词典从 IPD chunk 文本建，自由文本不会误链）、`task`（DM 标题 `techName — infoName` 片段，≥2 token，最长匹配优先）。链接 fail-closed（INV-4：未知码链空）、纯函数（INV-5）。`EntityLexicon` 按 chunk_id 集缓存（红队 day11 #10：内容哈希，陈旧不复用）。 |
| [graph_expand.py](../../src/learnarken/retrieval/graph_expand.py) | 80 | **Day 11 图谱扩展检索器**（RRF 第三路，spec §2）：候选**扩展**而非重排——存在的意义是捞回语义/词法候选池里**根本没有**的 chunk（教程 14 §2）。流程：实体链接 → `graph.neighborhood(seeds, depth=2)` 双向 `:REFS` 邻域 → 种子与邻居 DM 的 chunk 作"虚拟排名"（hop 0→1→2，store 确定性序，INV-5）。退化：无实体 ⇒ 空（fail-closed）；Neo4j 不可达 ⇒ 空 + 告警，`run_ablation` 前置 `is_up()` 拒跑，评估行不静默降级成普通 hybrid。 |
| [evaluate.py](../../src/learnarken/retrieval/evaluate.py) | 238 | golden set 评估：Recall@k / MRR / nDCG，固定种子。Day 4 加 `run_ablation`（bm25/dense/hybrid/hybrid-rerank 四行 + p50 延迟 + 分类召回）；**Day 11 加 `hybrid-graph`/`hybrid-graph-rerank` 两行**（需 Neo4j；诚实结论见 04 §4.12：小语料上 rerank 后逐位不变）。 |
| [\_\_init\_\_.py](../../src/learnarken/retrieval/__init__.py) | — | `search_package` / `run_eval` / `run_ablation` / `index_package` / `verify_corpus` 入口。`index_package`:分块→嵌入→喂 Vespa→图同步→写 manifest（幂等，红队 day4 #4）。`verify_corpus`:三查 fail-closed（manifest 存在且匹配 provider/strategy/chunk_id + engine 实际 doc-id 集 == 本地集），防陈旧/混合索引。**Day 12 加 `figure_chunks_for_package`**：读已提交的 `.describe.json` 记录、在 DM XML 内重验（红队 P1），把已核验图形并进语料一起索引。 |

### 2.5 embedding/ · vespa/ · graph/ · llm/ — 服务适配层（Day 4–5，Day 9/11 图查询增量）

| 文件 | 职责 |
| --- | --- |
| [embedding/providers.py](../../src/learnarken/embedding/providers.py) | LangChain `Embeddings` 接口后的 provider 注册表。**默认 Qwen3-Embedding-8B 本地**——MiniMax 因实测长度偏置于 Day 4 裁决移除（历史客户端在 `b414fa4`）。`get_embeddings` 每 provider 单例缓存，`embed_query_cached` LRU。 |
| [vespa/store.py](../../src/learnarken/vespa/store.py) | 唯一知道 Vespa 存在的模块:`deploy`/`feed`/`search`/`list_doc_ids`/`is_up`。`search(package=…)` engine 侧 scope 过滤 + 越界 fail-closed。app/ 下是 Vespa 应用包(schema `chunk.sd`、services.xml)。 |
| [graph/store.py](../../src/learnarken/graph/store.py) | 唯一知道 Neo4j 存在的模块（Day 5）:`sync`（从 chunk 幂等 upsert DM 节点 + DM→DM dmRef 边 + DM→ICN 边）、`facts`（取回检索 DM 的出/入引用与 ICN，接口③上下文注入）、`is_up`。**Day 9 加 `impact(dmc, depth)`**:反向 `dmRef` 逐跳 BFS（"DM X 被替换,谁受影响"），限深 + 已访问去重（package-b 的 VIO-7 环不死循环），Neo4j 不可达 fail-closed（INV-4）;并联 Graph-RAG 接口选项,**不并入**主答案管线（specs/day9 决策 2）。**Day 11 加 `neighborhood(seeds, depth)`**:与 `impact` 同形的逐跳 BFS,但**双向** `:REFS`（出边先于入边,再按 dmc,INV-5 确定性）,带 per-node 扇出上限 `GRAPH_FANOUT_CAP`（hub 守卫）——这是图谱检索第三路（`graph_expand.py`）的图侧引擎。loopback 绑定。 |
| [llm/minimax.py](../../src/learnarken/llm/minimax.py) | 唯一跟 LLM 说话的模块（Day 5）:MiniMax-M3 chat。`chat_json` 一次性 JSON;**`chat_json_stream`（Day 6）OpenAI 式 `stream:true`,`on_delta` 回调**。M3 恒发 `<think>…</think>` 前缀,解析前剥除;契约违规 → `LLMContractError`(拒答,非传输错)。 |

### 2.6 answer/ — 带引用问答引擎（Day 5–6）

| 文件 | 职责 |
| --- | --- |
| [engine.py](../../src/learnarken/answer/engine.py) | `answer_question`:**三门 fail-closed，严格二分**（INV-4:带引用回答 xor 拒答占位符）。门1 重排 top-1 < 实测阈值 → 短路,不调 LLM;门2 LLM `is_answerable:false` 或契约违规;门3 **引用确证**——每条 citation 的 chunk_id 须 ⊆ 检索集,且 `supporting_quote` 是该 chunk 的逐字子串(容空白/大小写),空/过短/样板句拒。DMC/XPath 由本模块从 chunk 元数据回填,LLM 只吐 chunk_id + quote(防引用漂移)。**Day 6 加 `on_event` 回调**:status/token/retract。 |
| [stream.py](../../src/learnarken/answer/stream.py) | **Day 6 `AnswerFieldExtractor`**:从 M3 流里增量剥出 `answer` 字段文本——跳 `<think>`、定位 `"answer":"`、跨 delta 边界解转义(含代理对;孤 surrogate 换 U+FFFD 保 UTF-8)。只吐答案文本,绝不吐 think/JSON 脚手架。 |
| [prompt.py](../../src/learnarken/answer/prompt.py) | 三区 prompt 契约:系统指令(证据唯一来源、拒答码、JSON 输出契约)/证据区(全部不可信素材序列化为**转义 JSON + 随机分隔符** spotlighting,图谱事实在栅栏内)/引用格式契约(只吐 chunk_id)。 |
| [models.py](../../src/learnarken/answer/models.py) / [trace.py](../../src/learnarken/answer/trace.py) | `AnswerResult`/`Citation` Pydantic 模型;每次查询落一份五跨度 trace(检索/重排/LLM/生成/图)到 `eval/traces/`(git-ignored)。 |
| [figure_relook.py](../../src/learnarken/answer/figure_relook.py) | **Day 12 问答侧二次看图接线（G15）**：当证据是图形 chunk 但（声明式）描述没答上问题时，先对**真实图像**做多采样共识再读（`second_look.consensus_read`）再拒答。诚实边界：索引图文本已是「完整已核验声明集」，二次读不会带出新的**已核验**内容——所以它在此的角色是**共识门控确认，喂给 G15 fail-closed 拒答**（防单次 flaky 读、记进 trace），而非从再读构造答案（后者对真实有损图形是 Roadmap）。永不抛异常：`FigureRefusal` 捕为 `consensus=False`。 |

### 2.7 api/ — HTTP 服务层（Day 6，见 [05-api-and-demo](05-api-and-demo.md)）

| 文件 | 职责 |
| --- | --- |
| [api/app.py](../../src/learnarken/api/app.py) | FastAPI 后端:`/health`(四服务 fail-closed 探测)、`/upload`(信封检查→四层校验→索引,**staging 事务化 + 原子换入**)、`/query`(SSE:status/token/retract/result/error/done,**召回覆盖门拒答与传输中断**)。路由 `def`(同步栈进线程池);CSRF Origin 门守状态变更路由;fail-closed 分类镜像 CLI 的 INV-4 映射。**Day 10 加 `/demo/status`**(粗粒度 stage 布尔自检,绝不出探测详情——要经 shim 出公网)与**业务活动时钟**(只有 `/query`/`/upload` 触碰,状态轮询不重置——否则 30 分钟闲置关机永不触发)。 |
| [api/demo_guard.py](../../src/learnarken/api/demo_guard.py) | **Day 10 公网 demo 安全信封**（红队 day10 #1/#2/#4/#5），仅 `DEMO_PUBLIC=1` 生效、本地 `make demo` 与测试零改变:**LLM 花费闸**(每日调用配额 + 并发信号量——MiniMax 花费不走 GCP 账单,$20 预算警报看不见它,这是问答路径唯一真实费用围栏;超限拒答不排队)、**共享门钥**(变更/花费路由须带 `X-Demo-Key`,钥匙只从 token 状态页发放)、**上传总闸**(公网模式直接拒——上传变异共享活语料)。全部 fail-closed（INV-4）。 |

### 2.8 repair/ — 自愈校验修复 Agent（Day 7）

LLM 主导的 ReAct 循环 + 受约束工具 + 沙箱执行器,读 Day 2 校验器 findings、出结构化
补丁,**默认 dry-run,`--apply` 逐补丁人工闸**(宪法 §1.3:绝不静默改数据)。信任来源
是**确定性校验器复跑通过**,不是 LLM 自称修好(生成器-验证器不共谋)。

| 文件 | 职责 |
| --- | --- |
| [agent.py](../../src/learnarken/repair/agent.py) / [core.py](../../src/learnarken/repair/core.py) | ReAct 循环(thought/tool/args 结构化 JSON,非原生 function-calling)+ 三维熔断(迭代/token/no-progress),编排单 finding 的诊断→补丁→复验。 |
| [tools.py](../../src/learnarken/repair/tools.py) | 6 个受约束工具:`search_corpus`/`read_module`/`query_xml`(只读)/`run_validator`(确定性验证器,反共谋)/`propose_patch`(唯一写路径,绑定到锚定节点)/`exec_sandbox`。**绝不给自由字符串/正则替换**(ACI 防呆)。 |
| [sandbox.py](../../src/learnarken/repair/sandbox.py) | 沙箱执行器:temp-dir jail(仅目标 XML/ICN 副本)、import/命令白名单、禁网络/禁越 jail 写、`setrlimit` + 超时。**玩具层(INV-7):应用层围栏,非 OS 级隔离**。 |
| [patch.py](../../src/learnarken/repair/patch.py) | 4 个扁平 `EditOp`(set_attr/set_text/remove/insert + 单节点 xpath),lxml 拼 DOM——消灭"忘闭合标签"类崩溃(神经符号分工)。 |
| [apply.py](../../src/learnarken/repair/apply.py) | 批准后写入:原子 `os.replace` + trash/启动恢复(INV-2 幂等+回滚)、apply 边界按 rule_id **重算风险 tier**、文件名 jail、TOCTOU 复检。 |
| [config.py](../../src/learnarken/repair/config.py) / [models.py](../../src/learnarken/repair/models.py) / [prompt.py](../../src/learnarken/repair/prompt.py) | 预算/沙箱配置(`pyproject [tool.learnarken.repair]`,加载钳位);`RepairReport`/`EditOp` 模型;ReAct 系统 prompt + 工具契约。 |
| [tot.py](../../src/learnarken/repair/tot.py) | **Day 13 Tree-of-Thoughts 修复**（Decision 3）：Best-of-N = 深度 1 宽度 N 的 ToT。对单个 finding 生成 **N 个异构角色候选**（conservative / schema-focused / reference-focused，低/中低温），每个是**各自独立沙箱**里的一次 Day 7 `repair_finding`，**由确定性沙箱验证器选优、绝不由 LLM 自评**（Decision 3b，INV-4）。选择顺序：验证通过且未被否决的候选里，删动最少 → 角色序 → diff 文本（全序，无 LLM 裁判）。**reward-hack 否决**：单补丁删源文件行占比 > `REWARD_HACK_DELETE_FRACTION=0.5`（诚实标注 toy 常量，粗信号，按后果分级是 Roadmap）→ 否决"删节点消 finding"；源不可读也否决（fail-closed）。候选自包含 → 可被 asyncio 编排器并发跑（`concurrent_runner`，Track-A/B 接缝）。复用而非重造：生成器 = Day 7 `repair_finding`，验证器 = Day 7 `propose_patch`。 |

### 2.9 adversarial/ — 评估红队：对抗集 + LLM-as-judge（Day 8）

攻击自家 RAG:≥30 例对抗集跑 Day 5 引擎,**行为**确定性判分(应答/拒/澄清),**有据性**
由**两个异构裁判(Codex + agy/Gemini,绝不用生成器 MiniMax)**打分。裁判不是信任来源,是
"异构 + 人工锚定(Cohen's κ)的人工抽查放大器"(呼应"别用 LLM 验 LLM")。

| 文件 | 职责 |
| --- | --- |
| [judge.py](../../src/learnarken/adversarial/judge.py) | 有据性裁判:extraction+verification 双步 prompt(单点打分,反位置/冗长偏差)、`CLIJudge`(受约束单发,非自主 agent)、`ScriptedJudge`(测试)、`parse_judge_output`(从噪声 stdout 抽 JSON)。**`FORBIDDEN_JUDGES={minimax}`**——同族裁判会 self-preference 共谋。 |
| [score.py](../../src/learnarken/adversarial/score.py) | `behavior_pass`(无需 LLM);`grounded_intersection`(**交集**:两裁判皆过才算有据,无人工兜底);`cohen_kappa`(sklearn;单类退化 → κ=None + 显式标注 DR §4 偏斜陷阱)。 |
| [run.py](../../src/learnarken/adversarial/run.py) / [models.py](../../src/learnarken/adversarial/models.py) | 编排:逐例跑引擎→判行为→答对行送裁判→冻结 per-judge artifact(记 model+version+date,INV-5 复现口径);`AdversarialCase`/`JudgeVerdict`/`RowResult`/`AdversarialReport` 模型。 |

### 2.10 multimodal/ — 图形多模态入库与二次看图（Day 12）

**describe-then-index** 离线管线 + 问答侧 G15 二次看图。核心纪律：**VLM 自由文本
（summary/warnings）绝不作为权威进语料**（红队 P1），索引文本只 ground 在 DM XML
声明集；VLM 描述被 SHA-256 绑到确切图像字节、成为可复审 artifact；单次 VLM 读不
可信，问答侧用**多采样共识**（Day 8"重复测不确定生成器"纪律应用到读图）。

| 文件 | 职责 |
| --- | --- |
| [vlm.py](../../src/learnarken/multimodal/vlm.py) | **VLM 图形描述客户端**：复用 MiniMax 代理传输（Bearer + X-Proxy-Token、剥 `<think>`、`base_resp.status_code==0`），发 OpenAI **多模态** content 数组（`image_url` data-URI）。探测发现：代理有 vision 但温度 0 下不稳定（空/散文频发），故每次调用 fail-closed，**两种截止条件**：(i) 空/"no image"/不可解析/schema 违规 = flaky miss，重试至 `VLM_MAX_RETRIES=3` → `VLMUnavailable`；(ii) HTTP **429** = 订阅上限，**终止不重试** → `VLMRateLimited`。温度 0、结构化输出、单图单调用；hotspot id 以**声明集为闭包 enum**（首个幻觉杠杆）。 |
| [figures.py](../../src/learnarken/multimodal/figures.py) | **声明式合成 ICN 图形**（INV-1）：单个 `FigureSpec` 是每张 ICN 的**唯一事实源**，同时产 **SVG**（DM 引用的 S1000D 图形 artifact + `<text>` 白名单锚点）与 **PNG**（VLM 读的栅格，via Pillow，提交并 SHA-256 绑定）。一源 ⇒ 无 SVG↔PNG 分歧；Pillow 环境内确定、跨环境字节一致不承诺（诚实位置，扫 T3）。图录仅 2 张 ICN（≤3 以护 43-chunk 池）。 |
| [ingest.py](../../src/learnarken/multimodal/ingest.py) | **describe-then-index 两相管线**（§3）。相 1 **describe（离线，用 VLM）**：渲 PNG → 算 SHA-256 → 调 VLM → **机械 hotspot diff**（读到的 id vs DM 声明的规范集，Decision 3a）+ **锚点印证**（声明件号须在读到的文本里复现，扫 T2）→ 出 `FigureRecord`；不匹配 ⇒ 图形**降级**（`verified=False`：记录但不索引），记录写在 asset 旁 `<icn>.describe.json` 并提交。相 2 **index（无 VLM）**：`figure_chunks` 对**当前** PNG 字节与**当前** DM 声明集**重验** SHA-256（换图/手改记录即跳过，fail-closed），把已核验图形转成可检索 `Chunk`（chunk_type="figure"），文本**只 ground 在声明集**。chunk_id 绑图像 SHA + 声明映射摘要——标签/件号一改即换 id，陈旧 Vespa doc 过不了语料校验（红队 R2 P1）。ICN id 正则限死在 `icn/` 目录内（红队 P2 防路径穿越）、PNG ≤4 MB 上限。 |
| [second_look.py](../../src/learnarken/multimodal/second_look.py) | **问答时二次看图 = 多采样共识读**（§4，Decision 2）。Yi Xin 裁决（2026-07-20）：单次 VLM 读不可信，故对真实图像做**多次独立 VLM 调用**，仅当样本**达成共识** AND 与确定性锚点（声明件号）一致才接受——推理时 self-consistency。`consensus_read` 采样至 `k=2` 个读一致（早停）且锚点印证；投票签名 = hotspot-id 集 + 件号集（顺序无关）。fail-closed（G15）：分歧/无共识/429 皆 `FigureRefusal` → 答案层 `refuse("figure-out-of-description")`，绝不返回任意单次读。件号印证只用**读到的 OCR 文本**、不用模型自报 `parts`（红队 P1 反自证），且 token 边界非子串。 |

### 2.11 perf/ — 性能与推理策略实验（Day 13）

Day 13 是**性能与推理策略实验日**，交付物是"**可验证的工程判断，不是花哨优化**"。
CPU/IO 分工严格二分（Decision 7a）：多进程管 CPU-bound、asyncio 管 I/O-bound，两者
不混。诚实结论全在 04 §4.14 与 [ADR-0003](../adr/0003-day13-rust-gate.md)：mp 玩具规模
无加速、numba 无靶、ToT repeat=3 无提升但 2.76× 成本、Rust/free-threading 证据门未开。

| 文件 | 职责 |
| --- | --- |
| [shard.py](../../src/learnarken/perf/shard.py) | **通用 CPU-bound 分片 runner**（Decision 1，INV-2）：分片藏在此抽象后——worker 收**分片描述**（如文件路径列表）、读自己那片、返回**可 pickle** 结果，无共享可变态、无活对象跨进程（INV-2 形态："分片藏抽象后、无共享内存捷径"）。`make_shards` 切近等分保序（item 少于 worker 时返回更少分片——有效并行被 item 数封顶）；`run_sharded` 按分片序 flatten 保**确定性**，`workers<=1` 进程内跑、`>1` 用 `ProcessPoolExecutor`，进程数 `min(workers, len(shards), cpu)`（红队 P2：`workers=10000` 不得成本地 DoS）。单机今天，同接口留给分布式队列（INV-2 全部意义）。 |
| [orchestrate.py](../../src/learnarken/perf/orchestrate.py) | **asyncio I/O-bound 编排**（Decision 7）：**项目唯一的 asyncio**，严格只做*编排*——调度等待型工作（LLM 候选调用 + 沙箱子进程 exec），`Semaphore(limit)` 限并发、每 task 有超时、单 task 失败**不**取消兄弟（非 fail-fast，各捕为 `TaskOutcome{success/timeout/error}`）。阻塞 job 经 `asyncio.to_thread` 进工作线程（`run_in_executor` 模式，Decision 7e），asyncio 只重叠其等待。**超时语义**（红队 P1 诚实标注）：`asyncio.timeout` 只界*编排器的等待*、不界工作线程（线程不可取消）——所以每个真 job 自带硬超时（LLM 请求超时 / 沙箱 `SandboxPolicy.timeout_s` 的 SIGKILL），本编排器超时是*外层*等待界。`run_bounded_sync` 拒在已有事件循环内跑（红队 P2）。 |

## 三、demo/ · tools/ · deploy/ — 演示、脚本与部署（Day 4–13）

| 文件 | 职责 |
| --- | --- |
| [demo/streamlit_app.py](../../demo/streamlit_app.py) | **哑客户端**:绝不 import `learnarken`(测试强制),只 HTTP 打后端。上传面板渲染四种结果,问答面板 SSE 流式 + 召回回撤 UI,历史进 `st.session_state`。渲染一律转义(无 `unsafe_allow_html`)。**Day 10 公网模式**(`DEMO_PUBLIC=1`):把访客 `?k=` 门钥经 `X-Demo-Key` 转发、隐藏上传页签、不渲染健康探测详情;本地无此变量零改变。 |
| [tools/run_demo.sh](../../tools/run_demo.sh) | `make demo`:fail-closed 预检 → uvicorn 单 worker → 轮询 `/health`(60s 不健康非零退出)→ Streamlit,均 loopback。 |
| [tools/demo_preflight.py](../../tools/demo_preflight.py) | 预检:repo-root cwd、`.env`、阈值 artifact、Vespa、Neo4j——缺则给修复命令并中止。 |
| [tools/measure_refusal_threshold.py](../../tools/measure_refusal_threshold.py) / [answer_sample_eval.py](../../tools/answer_sample_eval.py) | Day 5:从 golden 分数分布测拒答阈值(INV-5 artifact);带引用问答样本评估。 |
| [tools/adversarial_eval.py](../../tools/adversarial_eval.py) | **Day 8**:对抗评估活体 runner(≡ `learnarken eval adversarial`)+ **确定性 κ 校准模式** `--kappa-only`(读冻结 judge artifact × 人工标签算 Cohen's κ,无活体调用——INV-5 复现命令)。 |
| [tools/dense_bakeoff.py](../../tools/dense_bakeoff.py) / [probe_length_bias.py](../../tools/probe_length_bias.py) | Day 4a:dense 模型 bake-off(BGE-M3 vs Qwen3-8B;历史 MiniMax 行在 `b414fa4` 复现)；长度偏置证据脚本(自带 MiniMax 客户端,保证裁决证据可复跑 INV-5)。 |
| [tools/gen_benchmark_tables.py](../../tools/gen_benchmark_tables.py) | 从 eval artifacts **生成** README 基准表(红队 day4 #1:手编表出过 R@5 > R@10 的算术不可能;标记区间内原地重写,禁止手改)。 |
| [tools/deep_research.py](../../tools/deep_research.py) | 每日循环步骤 1a(研)的自动化通道:Gemini Interactions API 跑官方 Deep Research(需付费 key;截至 2026-07-15 未实跑验证)。 |
| tools/day11_ablation.py / day11_refusal_gate.py | **Day 11**:图谱检索六行消融 runner + G-RAG 拒答门评估(产 `eval/results/day11-*.json`)。 |
| tools/day12_eval.py / day12_resolution.py | **Day 12**:多模态 describe/index 评估 + VLM 通道稳定性/分辨率探测(产 `day12-*.json`)。 |
| tools/day13_profile.py / day13_mp_bench.py / day13_async_bench.py / day13_tot_eval.py | **Day 13**:profiler(热点定位,Rust/numba 证据门的依据)、mp 分片伸缩基准、asyncio 编排基准、ToT best-of-N 评估(产 `day13-*.json`,全固定 seed INV-5)。 |

**deploy/ — Day 10 按需真栈部署**（选型 D:停机 GCP VM + token 状态页,详见
[03 §7](03-config-and-services.md) 与 [05 §9](05-api-and-demo.md)）:

| 文件 | 职责 |
| --- | --- |
| [deploy/trigger/main.py](../../deploy/trigger/main.py) | **Cloud Function（gen2）触发闸**:三条路由全 token 门控——`GET /?t=` 状态/导览页、`GET /api/state` 停机态轮询源(compute API)、`POST /api/start` 限流的 `instances.start` + 邮件通知(点击/首次就绪只发 Yi Xin,邮件失败不破页面)。 |
| [deploy/trigger/index.html](../../deploy/trigger/index.html) / [logic.py](../../deploy/trigger/logic.py) / [tokens.example.json](../../deploy/trigger/tokens.example.json) | 静态状态/导览页(架构图+要点+后端三态:closed/starting/running 倒计时,closed 态给重启入口并诚实说明"闲置 30 分钟自动关闭");纯逻辑抽出可测;token 表只提交形状(真值不入库)。 |
| [deploy/vm/provision.sh](../../deploy/vm/provision.sh) / [run_demo_vm.sh](../../deploy/vm/run_demo_vm.sh) | VM 置备(容器+模型+systemd 单元)与开机拉起完整真栈(与 `make demo` 同拓扑——零基准口径漂移)。 |
| [deploy/vm/idle_watchdog.py](../../deploy/vm/idle_watchdog.py) | **VM 内闲置看门狗**(systemd oneshot,1 分钟 timer):业务闲置 ≥30 min、开机 ≥3 h 硬顶、自检连续不可达——**任何歧义都朝关机解**(机器在花钱)。闲置时钟来自 `/demo/status`,状态轮询不重置。 |
| [deploy/vm/status_shim.py](../../deploy/vm/status_shim.py) | 公网只读状态 shim(:8110):唯一职责是 GET 代理 loopback `/demo/status`;后端 FastAPI 保持 loopback-only(Day 6 安全信封不变),VM 上暴露公网的只有 Streamlit(:8501) 与本 shim。 |
| [deploy/vm/systemd/](../../deploy/vm/systemd/) | 五个 systemd 单元:containers/demo/shim/watchdog(+timer)。 |
| [deploy/DEPLOY-GUIDE.zh.md](../../deploy/DEPLOY-GUIDE.zh.md) / [runbook.md](../../deploy/runbook.md) | 中文部署指南（人操作步骤）与运维 runbook（状态机、费用围栏、故障排查）。 |

## 四、tests/ — 测试（与实现同 PR 交付）

| 文件 | 覆盖 |
| --- | --- |
| [test_inspect.py](../../tests/test_inspect.py) | Day 1 冒烟：包扫描 + inspect CLI。 |
| [test_validation.py](../../tests/test_validation.py) | Day 2 golden 测试：每条 BREX 规则 ≥1 通过 + ≥1 违规用例（INV-3）。 |
| [test_cli_day2.py](../../tests/test_cli_day2.py) | Day 2 CLI：validate / dm 子命令。 |
| [test_adjudication_fixes.py](../../tests/test_adjudication_fixes.py) | Day 2 红队裁决修复的回归测试。 |
| [test_chunking.py](../../tests/test_chunking.py) | Day 3 分块：两策略、元数据继承、存储健全性。 |
| [test_retrieval.py](../../tests/test_retrieval.py) | Day 3 检索：分词器、BM25 搜索、指标、CLI。 |
| [test_day4_retrieval.py](../../tests/test_day4_retrieval.py) / [test_day4_integration.py](../../tests/test_day4_integration.py) / [test_day4_closeout.py](../../tests/test_day4_closeout.py) | Day 4:稠密/混合/重排、Vespa 集成、收口回归。 |
| [test_day5_answer.py](../../tests/test_day5_answer.py) / [test_day5_integration.py](../../tests/test_day5_integration.py) | Day 5:配置加固、M3 解析、三门拒答、CLI 退出码;golden 问答活体套件(skip 标记)。 |
| [test_day6_stream.py](../../tests/test_day6_stream.py) | Day 6:`AnswerFieldExtractor` 边界(think 跳过、跨 delta 解转义)、SSE chunk 解析、流式客户端。 |
| [test_day6_api.py](../../tests/test_day6_api.py) | Day 6:上传信封/事务化/拒答路径、SSE 事件序(答/召回/阈值拒答/传输中断)、CSRF、哑客户端纯度(不 import learnarken)。引擎/服务全 mock,无活体依赖。 |
| [test_day7_repair.py](../../tests/test_day7_repair.py) / [test_day7_sandbox.py](../../tests/test_day7_sandbox.py) | Day 7:VIO 金对、沙箱逃逸(路径穿越/网络/白名单外)、预算熔断、apply 批准/拒绝/恢复、over-repair 门。 |
| [test_day8_adversarial.py](../../tests/test_day8_adversarial.py) | Day 8:对抗集完整性、行为判分(答/拒/澄清)、裁判交集/分歧、Cohen's κ(含偏斜陷阱)、**MiniMax 永不当裁判**、**对抗集不泄进生成 prompt**、编排端到端(stub 引擎 + ScriptedJudge);活体裁判套件 skip 标记。 |
| [test_day9_evidence.py](../../tests/test_day9_evidence.py) | Day 9:**EVIDENCE.md 防漂移守卫**——所有链接路径必须存在(无死链)、所有标记数字必须与源 artifact 一致;llms.txt 链接有效性;graph impact(限深钳位、环去重、fail-closed、CLI 退出码)。 |
| [test_day10_deploy.py](../../tests/test_day10_deploy.py) | Day 10:demo_guard(配额/并发/门钥/上传闸,含公网模式反向失效回归)、`/demo/status` 粗粒度、活动时钟只被业务路由触碰、watchdog 判定逻辑、trigger token 门控(`logic.py`)。 |
| [test_day11_entity_link.py](../../tests/test_day11_entity_link.py) / [test_day11_graph_expand.py](../../tests/test_day11_graph_expand.py) / [test_day11_golden.py](../../tests/test_day11_golden.py) | Day 11:实体链接(全码/裸码/件号词典成员/task 最长匹配、未知码 fail-closed、词典缓存内容哈希)；图谱扩展检索器(虚拟排名确定性、无实体空、Neo4j 不可达退化)；三路 RRF golden。 |
| [test_day12_multimodal.py](../../tests/test_day12_multimodal.py) | Day 12:VLM 客户端两种截止(flaky 重试→`VLMUnavailable` / 429→`VLMRateLimited`,含畸形 200 body、base_resp 限流)、SVG/PNG 一源、describe/index 两相、SHA-256 与声明映射重验(换图/手改跳过)、路径穿越拒绝、多采样共识(k 一致早停/分歧拒/锚点印证/反自证)、G15 拒答接线。VLM/服务全 stub,hermetic。 |
| [test_day13_perf.py](../../tests/test_day13_perf.py) / [test_day13_tot.py](../../tests/test_day13_tot.py) | Day 13:分片保序/进程数上限/空输入、mp 校验与单进程逐字节等价、asyncio 编排(信号量限并发/非 fail-fast/超时/拒事件循环内跑/NaN 超时)；ToT 角色候选、确定性选优(无 LLM 裁判)、reward-hack 否决(删占比/源不可读 fail-closed)、DRY_RUN_ONLY 降级不被选、并发/顺序 runner 一候选异常不拖垮全 finding。 |

## 五、eval/ — 版本化评估资产（Day 3–13）

| 文件 | 职责 |
| --- | --- |
| [golden/README.md](../../eval/golden/README.md) | 双文件双作者制的说明（检索评估的红线：**相关性判断必须人做**）。 |
| [golden/day3.jsonl](../../eval/golden/day3.jsonl) | **人工标注的权威 golden set**：32 题（27 可答 + 5 无答案陷阱），Yi Xin 判定相关性。 |
| golden/day4.jsonl | Day 4 消融用 golden（带分类标签）。 |
| golden/day3.candidates.jsonl / day4.candidates.jsonl | AI 起草的候选题（红线：AI 只许起草，相关性判定人做；裁定后进权威 golden）。 |
| results/day4-ablation.json / day4-bakeoff.json / day4-bakeoff-historical.json | Day 4 消融与 dense bake-off 数字 artifact——README 表由 `gen_benchmark_tables.py` 从这里生成；historical 保留 MiniMax 长度偏置的证据行。 |
| results/day5-answer-sample.json | Day 5 带引用问答样本评估结果（`answer_sample_eval.py` 产出）。 |
| results/day5-refusal-threshold.json | **Day 5 实测拒答阈值 artifact（INV-5）**：从 golden 分数分布测出、非手挑，`load_threshold` 加载时校验有限且 ∈[0,1]（红队 day5 #6）。 |
| traces/（git-ignored） | 每次 `query` 落一份五跨度 answer trace，可从语料复现。 |
| [golden/day8-adversarial.jsonl](../../eval/golden/day8-adversarial.jsonl) | **Day 8 对抗集**:32 例四类(改写/扰动/无答案/跨文档),LA100 真锚。**AI 设计、Yi Xin review**(SPEC day8 决策 1,每行 `ai_drafted:true`);**绝不进生成 prompt**(防泄漏)。 |
| results/day8-adversarial-report.json / day8-judge-{codex,agy}.json | **Day 8** 冻结报告 + per-judge 裁决 artifact(记 model+version+date,INV-5 复现口径);`day8-adversarial-before.json` / `day8-behavior-{before,after}.json` 保留 X-01 聚合缺陷修复前后的对照证据。 |
| [golden/day8-human-labels.json](../../eval/golden/day8-human-labels.json) / results/day8-kappa.json | **人工锚定校准（已完成）**:Yi Xin 标注 n=30;κ 由 `adversarial_eval.py --kappa-only` 确定性重算——codex κ=0.737、agy κ=0.667,双双过 0.60 软门。 |
| results/day9-acceptance.json | **Day 9 验收 artifact**:陌生 AI agent（MiniMax-M3）只读 llms.txt+EVIDENCE.md 定位抽样数字复跑命令的实测记录（自标注:演示性质,非基准——生成器非确定）。 |
| results/day11-ablation.json / day11-refusal-gate.json | **Day 11 图谱检索消融**（bm25/dense/hybrid/hybrid-rerank/**hybrid-graph/hybrid-graph-rerank** 六行 + p50 延迟）；G-RAG 拒答门 artifact。诚实结论：小语料 rerank 后逐位不变（图路加值在召回阶段被 rerank 吸收，04 §4.12）。 |
| results/day12-multimodal.json / day12-resolution.json | **Day 12 多模态** describe/index 评估；`day12-resolution.json` 记 T5 小测试集的 VLM 通道不稳定率（`VLM_CONSENSUS_K` 的 INV-5 出处）。 |
| results/day13-hotspots.json / day13-mp-scaling.json / day13-async.json / day13-tot.json | **Day 13 性能与推理策略**：profiler 热点（CPU 花在 lxml/schema/Pydantic 已编译层——Rust/numba 无靶的证据，ADR-0003）；mp 分片伸缩（玩具规模无加速）；asyncio 编排 overlap；ToT repeat=3 无提升但 2.76× 成本。全固定 seed（INV-5）。 |

## 六、samples/ — 合成样本包（INV-1：绝不含真实 S1000D 内容）

| 目录 | 职责 |
| --- | --- |
| [package-a/](../../samples/package-a/) | **合法包**：10 个 S1000D-like XML（描述、程序、fault、IPD、DML、PMC）+ ICN 图形。校验应全绿。 |
| [package-b/](../../samples/package-b/) | **已知违规包**：植入枚举过的违规类（VIO-1..8，清单在宪法 §4），是校验器的靶场——findings 必须与违规清单一一对应到行/路径。 |
| [package-c/](../../samples/package-c/) | **适用性排除测试包**（Day 3 新增）：验证"排除 variant X 真的排除"的指定输入，也进检索评估语料。 |
| [samples/s1000d/](../../samples/s1000d/) | 真实 S1000D 结构的**只读参考**（非提交文件仅参考、绝不复制内容）。 |

## 七、docs/ — 证据链与知识资产

| 目录/文件 | 职责 | 作者 |
| --- | --- | --- |
| [constitution.md](../constitution.md) | 最高权威：业务场景 + 8 条不变项（INV-1 数据红线 … INV-8 滑点规则）+ package-b 违规清单 | 人 |
| [execution-plan.md](../execution-plan.md) | 10 日执行主计划：每日七步循环、各日验收标准 | 人 |
| [project-design.md](../project-design.md) | 完整愿景设计（M0–M8、JD 覆盖矩阵）——执行计划只切其中最小闭环 | 人 |
| [EVIDENCE.md](../EVIDENCE.md) | **Day 9 主张→证据矩阵**：每个对外能力主张 → 仓库内证据文件 → 可复制复跑命令 → 诚实分层标签;守卫测试 `test_day9_evidence.py` 保证无死链、数字与源 artifact 零漂移;INV-1 边界——只放抽象能力声明,简历留私档指回 | AI 起草、人审 |
| [AI-COLLABORATION.md](../AI-COLLABORATION.md) | **Day 9 AI-first 工作流白皮书**：七步每日循环、adversarial validation 术语卡（并与传统 ML 语义区分）、哪些必须人工所有 | AI 起草、人审 |
| [specs/day1–13.md](../specs/) | 每日 SPEC：决策层人写，阐述层可 AI 起草（带标签） | 人主导 |
| [discussions/day1–13.md](../discussions/) | 蒸馏的设计讨论：问题→选项→决定→理由（含 `day11-13-planning.md` 三日联合规划） | AI 蒸馏、人审 |
| [reviews/day1–13.md](../reviews/) | 红队 findings（非实现方模型出）+ 人工逐条裁决（Day 6 起多为两轮:跨宿主对抗 + 安全评审） | AI + 人 |
| [journal/day1–13.md](../journal/) | 学习日志（固定三问），**AI 永不触碰** | 人 |
| [research/dayN-*.md](../research/) | 每日「研→读→扫」的未知点扫描（day1–13，AI 生成、标注），交叉引用深调研报告 + 教程 | AI 起草 |
| [gemini-deepresearch/](../gemini-deepresearch/) | 每日「研」的深调研报告存档（day1–10，2026-07-15 一次生成；REVIEW.md 为人工审读记录） | 外部生成、人审 |
| [notes/](../notes/) | 测量笔记：Day 4 dense bake-off、嵌入长度偏置、失败案例分析、**Day 13 numba 决策、Day 12 幻觉边界**——选型裁决的证据文件 | AI 起草 |
| [handoff/](../handoff/) | 跨会话交接文档（day4–13）：当日状态、待办、坑位 | AI 起草 |
| [redteam.md](../redteam.md) | 红队配方：轻量交叉评审 + 重型 Producer→Challenger→Reviser 循环 | 人 |
| [local-services.md](../local-services.md) | **本地服务手册**：Vespa/Neo4j docker 连接信息、MiniMax API 环境变量形状（无密钥值） | 人+AI |
| [adr/](../adr/) | 架构决策记录:0001 Day4b 关门、0002 最小图查询切片、**0003 Day13 Rust/free-threading 证据门未开** | 人主导 |
| [tutorials/00–16](../tutorials/) | 中文零基础教程系列（Day 5 对应 05 RAG、**Day 11 对应 14 KG-RAG、Day 12 对应 15 多模态、Day 13 对应 16 性能工程**） | AI 起草 |
| [diagrams/](../diagrams/) | mermaid 源 + 渲染 SVG：学习路线图、领域地图、架构流 | AI 起草 |
| [learning-guide.md](../learning-guide.md) / [visual-map.md](../visual-map.md) | 学习导引与视觉地图 | AI 起草 |
| [resume-fixes-2026-07.md](../resume-fixes-2026-07.md) | 求职侧文档（简历修订）。**注**：同批的 `github-plan.md` / `job-search-review-2026-07.md` 已于 2026-07-21 作废删除（未入库的本地个人规划稿） | 人主导 |
| architecture/（本目录） | 架构快照与变更基准 | AI 起草、人审 |
