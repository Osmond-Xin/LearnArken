# 01 · 文件清单：每个文件在做什么

> **AI-drafted，待人审**。快照：2026-07-17，分支 `feat/day6`（Day 5 已合并打标
> `v0.5.0`；Day 6 实现完成、两轮红队已裁、待提交）。行数为快照当日近似值，仅示意规模。

## 一、根目录：工程骨架（Day 1）

| 文件 | 职责 |
| --- | --- |
| [pyproject.toml](../../pyproject.toml) | 项目元数据与依赖单一事实源。运行时依赖现 14 个（Day 1 起步仅 4：defusedxml / lxml / pydantic / rank-bm25；Day 4–6 增至含 langchain 五件套、sentence-transformers、fastapi/uvicorn/python-multipart/requests），全部带上界 + `uv.lock` 锁定（Day 2 红队裁决 #13：解析器行为不许在未锁定安装下漂移）。注册 CLI 入口 `learnarken = learnarken.cli:main`。 |
| [.env.example](../../.env.example) | 本地 `.env` 的形状模板：`MINIMAX_*` 四变量 + `NEO4J_*`，只记形状不记值（安全红线）。 |
| [uv.lock](../../uv.lock) | 依赖锁文件，CI 用 `uv sync --locked` 安装，保证可复现（INV-5）。 |
| [Makefile](../../Makefile) | 三个入口：`make test`（pytest）、`make lint`（ruff check + format --check）、`make fmt`（自动修复）。 |
| [.pre-commit-config.yaml](../../.pre-commit-config.yaml) | 提交前钩子：ruff 检查/格式化 + 大文件/合并冲突/私钥泄漏/行尾空白检查。**detect-private-key 是安全红线的机器执行层**。 |
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | CI：锁定安装 → lint → test。action 全部按 commit SHA 固定（防供应链漂移）。 |
| [.gitignore](../../.gitignore) | 首个 commit 即配好：`.env`、密钥、缓存不入库（安全红线）。 |
| [README.md](../../README.md) / [README.zh-CN.md](../../README.zh-CN.md) | 对外门面：业务场景、AI-first 工作流说明、进度表、**Day 3 检索基准表**（含复跑命令）、诚实分层 Roadmap、仓库导览。对外一律英文（中文版为镜像）。 |
| [CLAUDE.md](../../CLAUDE.md) | AI 实现方的操作规则：角色边界（SPEC 决策层人写、journal/裁决 AI 不碰）、自动红队闸、当日讨论纪要强制规则。 |

## 二、src/learnarken/ — 产品代码

### 2.1 核心解析与模型（Day 1–2）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [package.py](../../src/learnarken/package.py) | 166 | **Day 1 的轻量扫描器**：只解析 inspect 摘要表需要的字段（dmCode、标题、issueInfo、语言），直接读 XML 属性。含控制字符清洗（红队 #9：防标题里的 ANSI 序列污染终端）。是 `inspect` 命令的后端。 |
| [models.py](../../src/learnarken/models.py) | 175 | **Day 2 规范模型（Pydantic）**：DmCode、DataModule、PublicationModule、DML、DmRef/IcnRef、warning/caution、Applicability（displayText + 结构化断言双轨——断言给 Day 3 chunk 做机器过滤，displayText 给人读）。全仓库的"规范数据字典"。 |
| [loader.py](../../src/learnarken/loader.py) | 300 | **XML → 规范模型的装载器**：每个文件先过 defusedxml（L0 良构性 + 防实体炸弹），再由加固的 lxml（禁实体/DTD/网络）重解析拿行号、XPath、XSD 校验。含 fail-closed 文件大小上限（红队 #4：超限拒收而非耗尽内存）。 |
| [cli.py](../../src/learnarken/cli.py) | 670 | 命令行入口，现 9 个子命令：Day 1–3 的 `inspect`/`validate`/`dm`/`chunk`/`search`/`eval retrieval`，加 Day 4 的 `index`（喂 Vespa）、`eval ablation`（四模式消融），加 Day 5 的 `query`（带引用问答:退出码 0 答/3 拒答/1 fail-closed/2 非包）。 |
| [config.py](../../src/learnarken/config.py) | — | `REPO_ROOT` 解析 + `load_minimax_config`：只读 repo-root `.env`、仅接受 `MINIMAX_*` 白名单、强制 https（红队 day4 #7 加固，Day 5 起用于 chat）。 |
| [schemas/learnarken.xsd](../../src/learnarken/schemas/learnarken.xsd) | — | 项目自造的**简化 XSD**（L1 结构校验层），对真实 S1000D schema 的玩具级替身（INV-7 诚实分层）。 |

### 2.2 validation/ — 四层校验器（Day 2）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [engine.py](../../src/learnarken/validation/engine.py) | 433 | 四层编排：L0 良构 → L1 mini-XSD → L2 单文件 BREX → L3 跨文件完整性（dmRef 悬空、ICN 缺失、版本错位、循环引用）。**Fail-closed 分层（INV-4）**：L0 挂的文件不进上层；L1 挂的跳过自身 L2 但仍作为 L3 图节点存在。**L3 的引用图是未来知识图谱（Neo4j）的地基**。 |
| [rules.py](../../src/learnarken/validation/rules.py) | 169 | L2 BREX 规则表：Schematron 风格的声明式断言（rule id、severity、描述、fix hint、检查函数），不引入 isoschematron 工具链。BREX-001 是诚实标注的玩具启发式（危险词词表代替真实业务规则，INV-7）。 |
| [report.py](../../src/learnarken/validation/report.py) | 58 | 四层共用的 Finding / ValidationReport Pydantic 模型（rule_id、layer、severity、file、line、path、message、fix_hint）。 |

### 2.3 chunking/ — 结构感知分块（Day 3–4）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [base.py](../../src/learnarken/chunking/base.py) | 104 | Chunk 模型 + 元数据继承：chunk 从 Day 2 DataModule 继承 DMC、applicability（排除场合）、hazard 标志（紧急场合，见 discussions/day3 D4）、`outbound_dm_refs`/`icn_refs`（**图谱钩子**，D3 的"不许饿死未来图谱"义务）。chunk_id 确定性生成（内容哈希），复跑不变。 |
| [structure.py](../../src/learnarken/chunking/structure.py) | 113 | **结构感知策略（主力）**：沿文档自带的切线切——每个 procedural step 一块（行内 warning 折入并置 hazard 标志）、reqSafety 前置警告独立成块、前置条件/收尾各成块、描述节按 levelledPara 切。每块保留 XPath 锚点（golden set 按锚点标注）。 |
| [recursive.py](../../src/learnarken/chunking/recursive.py) | 74 | **递归字符窗口策略（对照组）**：故意结构盲，800 字符窗口 / 100 重叠，在词边界断开。存在的意义是让评估表**量化**结构感知值多少分。 |
| [semantic.py](../../src/learnarken/chunking/semantic.py) | 128 | **语义分块策略（Day 4a，spec Q5）**：Day 3 D1 承诺的第三策略，embedding 就位后交付。结构盲但按内容切——逐句嵌入、量邻句距离、在距离尖峰处断；断点取 DM 自身距离的 95 分位（自适应，不用固定余弦阈值）。唯一发网络调用的分块器，活体测试打 `integration` 标。 |
| [documents.py](../../src/learnarken/chunking/documents.py) | 30 | Chunk ⇄ LangChain `Document` 的**唯一转换点**（Day 4a，D13）：metadata 无损往返完整 Chunk（适用性/hazard/图谱钩子）。 |
| [\_\_init\_\_.py](../../src/learnarken/chunking/__init__.py) | 81 | `chunk_package` 入口：遍历包内 DM，按策略产出 chunk；复用 Day 2 loader，不重复解析。 |

### 2.4 retrieval/ — BM25 基线、稠密/混合检索与评估（Day 3–4）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [bm25.py](../../src/learnarken/retrieval/bm25.py) | 80 | **保标识符的分词器** + rank-bm25 薄封装（Day 4 起为 LC `BM25Retriever`）。核心洞察（教程 02 §1）：标准分析器会把 `DMC-LA100-…`、`P/N 1234-567` 在标点处打碎，标识符查询就被数字碎片淹没；把标识符保成整 token 是技术语料里单点杠杆最高的修复。 |
| [dense.py](../../src/learnarken/retrieval/dense.py) | — | **Day 4 稠密检索**：`VespaDenseRetriever`——查询向量走缓存 embedder，engine 侧按 package scope 过滤并 fail-closed 校验返回文档确在 scope 内（红队 day4 #5）。 |
| [hybrid.py](../../src/learnarken/retrieval/hybrid.py) | — | **Day 4 混合检索**：BM25 + 稠密的 RRF 融合（LC `EnsembleRetriever`）+ 交叉编码器重排（`bge-reranker-v2-m3`，本地，`_RERANKER_CACHE` 进程缓存）。`rerank_scored` 额外吐 top-1 分数——Day 5 拒答阈值门的信号源。 |
| [evaluate.py](../../src/learnarken/retrieval/evaluate.py) | 238 | golden set 评估：Recall@k / MRR / nDCG，固定种子。Day 4 加 `run_ablation`（bm25/dense/hybrid/hybrid-rerank 四行 + p50 延迟 + 分类召回）。 |
| [\_\_init\_\_.py](../../src/learnarken/retrieval/__init__.py) | — | `search_package` / `run_eval` / `run_ablation` / `index_package` / `verify_corpus` 入口。`index_package`:分块→嵌入→喂 Vespa→图同步→写 manifest（幂等，红队 day4 #4）。`verify_corpus`:三查 fail-closed（manifest 存在且匹配 provider/strategy/chunk_id + engine 实际 doc-id 集 == 本地集），防陈旧/混合索引。 |

### 2.5 embedding/ · vespa/ · graph/ · llm/ — 服务适配层（Day 4–5）

| 文件 | 职责 |
| --- | --- |
| [embedding/providers.py](../../src/learnarken/embedding/providers.py) | LangChain `Embeddings` 接口后的 provider 注册表。**默认 Qwen3-Embedding-8B 本地**——MiniMax 因实测长度偏置于 Day 4 裁决移除（历史客户端在 `b414fa4`）。`get_embeddings` 每 provider 单例缓存，`embed_query_cached` LRU。 |
| [vespa/store.py](../../src/learnarken/vespa/store.py) | 唯一知道 Vespa 存在的模块:`deploy`/`feed`/`search`/`list_doc_ids`/`is_up`。`search(package=…)` engine 侧 scope 过滤 + 越界 fail-closed。app/ 下是 Vespa 应用包(schema `chunk.sd`、services.xml)。 |
| [graph/store.py](../../src/learnarken/graph/store.py) | 唯一知道 Neo4j 存在的模块（Day 5）:`sync`（从 chunk 幂等 upsert DM 节点 + DM→DM dmRef 边 + DM→ICN 边）、`facts`（取回检索 DM 的出/入引用与 ICN，接口③上下文注入）、`is_up`。loopback 绑定。 |
| [llm/minimax.py](../../src/learnarken/llm/minimax.py) | 唯一跟 LLM 说话的模块（Day 5）:MiniMax-M3 chat。`chat_json` 一次性 JSON;**`chat_json_stream`（Day 6）OpenAI 式 `stream:true`,`on_delta` 回调**。M3 恒发 `<think>…</think>` 前缀,解析前剥除;契约违规 → `LLMContractError`(拒答,非传输错)。 |

### 2.6 answer/ — 带引用问答引擎（Day 5–6）

| 文件 | 职责 |
| --- | --- |
| [engine.py](../../src/learnarken/answer/engine.py) | `answer_question`:**三门 fail-closed，严格二分**（INV-4:带引用回答 xor 拒答占位符）。门1 重排 top-1 < 实测阈值 → 短路,不调 LLM;门2 LLM `is_answerable:false` 或契约违规;门3 **引用确证**——每条 citation 的 chunk_id 须 ⊆ 检索集,且 `supporting_quote` 是该 chunk 的逐字子串(容空白/大小写),空/过短/样板句拒。DMC/XPath 由本模块从 chunk 元数据回填,LLM 只吐 chunk_id + quote(防引用漂移)。**Day 6 加 `on_event` 回调**:status/token/retract。 |
| [stream.py](../../src/learnarken/answer/stream.py) | **Day 6 `AnswerFieldExtractor`**:从 M3 流里增量剥出 `answer` 字段文本——跳 `<think>`、定位 `"answer":"`、跨 delta 边界解转义(含代理对;孤 surrogate 换 U+FFFD 保 UTF-8)。只吐答案文本,绝不吐 think/JSON 脚手架。 |
| [prompt.py](../../src/learnarken/answer/prompt.py) | 三区 prompt 契约:系统指令(证据唯一来源、拒答码、JSON 输出契约)/证据区(全部不可信素材序列化为**转义 JSON + 随机分隔符** spotlighting,图谱事实在栅栏内)/引用格式契约(只吐 chunk_id)。 |
| [models.py](../../src/learnarken/answer/models.py) / [trace.py](../../src/learnarken/answer/trace.py) | `AnswerResult`/`Citation` Pydantic 模型;每次查询落一份五跨度 trace(检索/重排/LLM/生成/图)到 `eval/traces/`(git-ignored)。 |

### 2.7 api/ — HTTP 服务层（Day 6，见 [05-api-and-demo](05-api-and-demo.md)）

| 文件 | 职责 |
| --- | --- |
| [api/app.py](../../src/learnarken/api/app.py) | FastAPI 后端:`/health`(四服务 fail-closed 探测)、`/upload`(信封检查→四层校验→索引,**staging 事务化 + 原子换入**)、`/query`(SSE:status/token/retract/result/error/done,**召回覆盖门拒答与传输中断**)。路由 `def`(同步栈进线程池);CSRF Origin 门守状态变更路由;fail-closed 分类镜像 CLI 的 INV-4 映射。 |

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

### 2.9 adversarial/ — 评估红队：对抗集 + LLM-as-judge（Day 8）

攻击自家 RAG:≥30 例对抗集跑 Day 5 引擎,**行为**确定性判分(应答/拒/澄清),**有据性**
由**两个异构裁判(Codex + agy/Gemini,绝不用生成器 MiniMax)**打分。裁判不是信任来源,是
"异构 + 人工锚定(Cohen's κ)的人工抽查放大器"(呼应"别用 LLM 验 LLM")。

| 文件 | 职责 |
| --- | --- |
| [judge.py](../../src/learnarken/adversarial/judge.py) | 有据性裁判:extraction+verification 双步 prompt(单点打分,反位置/冗长偏差)、`CLIJudge`(受约束单发,非自主 agent)、`ScriptedJudge`(测试)、`parse_judge_output`(从噪声 stdout 抽 JSON)。**`FORBIDDEN_JUDGES={minimax}`**——同族裁判会 self-preference 共谋。 |
| [score.py](../../src/learnarken/adversarial/score.py) | `behavior_pass`(无需 LLM);`grounded_intersection`(**交集**:两裁判皆过才算有据,无人工兜底);`cohen_kappa`(sklearn;单类退化 → κ=None + 显式标注 DR §4 偏斜陷阱)。 |
| [run.py](../../src/learnarken/adversarial/run.py) / [models.py](../../src/learnarken/adversarial/models.py) | 编排:逐例跑引擎→判行为→答对行送裁判→冻结 per-judge artifact(记 model+version+date,INV-5 复现口径);`AdversarialCase`/`JudgeVerdict`/`RowResult`/`AdversarialReport` 模型。 |

## 三、demo/ · tools/ — 演示与脚本（Day 4–8）

| 文件 | 职责 |
| --- | --- |
| [demo/streamlit_app.py](../../demo/streamlit_app.py) | **哑客户端**:绝不 import `learnarken`(测试强制),只 HTTP 打后端。上传面板渲染四种结果,问答面板 SSE 流式 + 召回回撤 UI,历史进 `st.session_state`。渲染一律转义(无 `unsafe_allow_html`)。 |
| [tools/run_demo.sh](../../tools/run_demo.sh) | `make demo`:fail-closed 预检 → uvicorn 单 worker → 轮询 `/health`(60s 不健康非零退出)→ Streamlit,均 loopback。 |
| [tools/demo_preflight.py](../../tools/demo_preflight.py) | 预检:repo-root cwd、`.env`、阈值 artifact、Vespa、Neo4j——缺则给修复命令并中止。 |
| [tools/measure_refusal_threshold.py](../../tools/measure_refusal_threshold.py) / [answer_sample_eval.py](../../tools/answer_sample_eval.py) | Day 5:从 golden 分数分布测拒答阈值(INV-5 artifact);带引用问答样本评估。 |
| [tools/adversarial_eval.py](../../tools/adversarial_eval.py) | **Day 8**:对抗评估活体 runner(≡ `learnarken eval adversarial`)+ **确定性 κ 校准模式** `--kappa-only`(读冻结 judge artifact × 人工标签算 Cohen's κ,无活体调用——INV-5 复现命令)。 |
| [tools/dense_bakeoff.py](../../tools/dense_bakeoff.py) / [probe_length_bias.py](../../tools/probe_length_bias.py) | Day 4a:dense 模型 bake-off(BGE-M3 vs Qwen3-8B;历史 MiniMax 行在 `b414fa4` 复现)；长度偏置证据脚本(自带 MiniMax 客户端,保证裁决证据可复跑 INV-5)。 |
| [tools/gen_benchmark_tables.py](../../tools/gen_benchmark_tables.py) | 从 eval artifacts **生成** README 基准表(红队 day4 #1:手编表出过 R@5 > R@10 的算术不可能;标记区间内原地重写,禁止手改)。 |
| [tools/deep_research.py](../../tools/deep_research.py) | 每日循环步骤 1a(研)的自动化通道:Gemini Interactions API 跑官方 Deep Research(需付费 key;截至 2026-07-15 未实跑验证)。 |

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

## 五、eval/ — 版本化评估资产（Day 3–8）

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
| results/day8-adversarial-report.json / day8-judge-{codex,agy}.json | **Day 8** 冻结报告 + per-judge 裁决 artifact(记 model+version+date,INV-5 复现口径);κ 由 `adversarial_eval.py --kappa-only` 对人工标签算,人工标签 `golden/day8-human-labels.json`(人工所有,INV-6,待 Yi Xin 标)。 |

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
| [specs/day1–6.md](../specs/) | 每日 SPEC：决策层人写，阐述层可 AI 起草（带标签） | 人主导 |
| [discussions/day1–6.md](../discussions/) | 蒸馏的设计讨论：问题→选项→决定→理由 | AI 蒸馏、人审 |
| [reviews/day1–6.md](../reviews/) | 红队 findings（非实现方模型出）+ 人工逐条裁决（Day 6 为两轮:跨宿主对抗 + 安全评审） | AI + 人 |
| [journal/day1–6.md](../journal/) | 学习日志（固定三问），**AI 永不触碰** | 人 |
| [research/dayN-*.md](../research/) | 每日「研→读→扫」的未知点扫描（AI 生成、标注），交叉引用深调研报告 + 教程 | AI 起草 |
| [gemini-deepresearch/](../gemini-deepresearch/) | 每日「研」的深调研报告存档（day1–10，2026-07-15 一次生成；REVIEW.md 为人工审读记录） | 外部生成、人审 |
| [notes/](../notes/) | 测量笔记：Day 4 dense bake-off、嵌入长度偏置、失败案例分析——选型裁决的证据文件 | AI 起草 |
| [handoff/](../handoff/) | 跨会话交接文档（day4–6）：当日状态、待办、坑位 | AI 起草 |
| [redteam.md](../redteam.md) | 红队配方：轻量交叉评审 + 重型 Producer→Challenger→Reviser 循环 | 人 |
| [local-services.md](../local-services.md) | **本地服务手册**：Vespa/Neo4j docker 连接信息、MiniMax API 环境变量形状（无密钥值） | 人+AI |
| [adr/](../adr/) | 架构决策记录:0001 Day4b 关门、0002 最小图查询切片 | 人主导 |
| [tutorials/00–12](../tutorials/) | 中文零基础教程系列（Day 5 对应 05 RAG、Day 6 对应 10/11 可观测/合规） | AI 起草 |
| [diagrams/](../diagrams/) | mermaid 源 + 渲染 SVG：学习路线图、领域地图、架构流 | AI 起草 |
| [learning-guide.md](../learning-guide.md) / [visual-map.md](../visual-map.md) | 学习导引与视觉地图 | AI 起草 |
| [github-plan.md](../github-plan.md) / [job-search-review-2026-07.md](../job-search-review-2026-07.md) / [resume-fixes-2026-07.md](../resume-fixes-2026-07.md) | 求职侧文档（GitHub 呈现计划、求职评审、简历修订） | 人主导 |
| architecture/（本目录） | 架构快照与变更基准 | AI 起草、人审 |
