# LearnArken

**A standards-aware technical-publication intelligence platform for aviation
(S1000D), built AI-first: human-written specs, AI implementation, adversarial
red-team review, human adjudication.**

*[English version (default)](README.md)*

面向航空领域 S1000D 技术出版物的校验 + 检索问答 + 辅助修复系统。
这是一个**学习作品集项目**,同时刻意演示一件事:2026 年的工程师如何
**用规格与判断力驾驭 AI 完成交付**,并让整个过程可被第三方(包括招聘方的
AI agent)沿证据链核查。

## 项目模拟的业务场景

一家航空维修公司为一线工程师提供支持:工程师站在飞机旁,打开电脑,
**现在就要**找到正确的维修方案。因此**延迟与召回率高于一切**——本项目
所有基准都同时报告这两项。输入材料是该公司的培训手册(S1000D 风格数据包),
其中会累积过期旧版本,必须建模区分并过滤。

规划中的系统(按下方 13 日进度表逐日构建,当前已有内容见进度表)将提供:

1. **Fail-closed 入库闸门** — 每份文档入库前经 S1000D 结构与基础 BREX
   (Schematron)规则校验。过期、不合规、错领域文档(如混入的舰船维修模块)
   一律报错拒收、说明与标准的差异,绝不自动修正——由人裁决;只有合规文档进入知识库;
2. **带引用的问答** — "更换这个零件要先做什么准备?" 答案必须带出处,
   证据不足时明确拒答(维修领域不容编造);
3. **辅助修复** — 对已知违规生成修复建议,人审批后应用,修复后自动复验。

**诚实声明**:样本数据是自造合成的 S1000D-like XML(含人为注入的已知违规),
规模是教学级;分布式行为用单机多线程模拟,但接口按真分布式设计。
全部模拟设定与不变式见 [docs/constitution.md](docs/constitution.md)。

## AI-first 工作流(本项目的第二个作品)

每天一个节点,固定七步:**学 → 规(人写 SPEC)→ 做(AI 实现)→
审(独立模型只读红队)→ 裁(本人逐条裁决)→ 证(验收)→ 交(tag)**。

三道不可伪造的理解闸,全部留痕在仓库里:

| 闸 | 证据位置 | 为什么装不出来 |
| --- | --- | --- |
| SPEC **决策层**人写(目标/验收标准/砍掉什么/关键取舍) | [docs/specs/](docs/specs/) | 拆解与判断力直接暴露在文字里;AI 起草的展开层明确标注 |
| 裁决人写 | [docs/reviews/](docs/reviews/) | 不理解实现就无法判断红队 finding 真假 |
| 日志人写 | [docs/journal/](docs/journal/) | 固定三问:学到什么 / AI 错在哪 / 我拒绝了 AI 什么 |

此外,每天决策背后的设计讨论蒸馏进 [docs/discussions/](docs/discussions/)
(问题 → 选项 → 决策 → 理由),展示 AI 方案在真实工作会话中如何被引导、采纳或拒绝。

红队纪律:评审模型与实现模型必须不同、只读不写、报出的数字本人复跑。
详见 [docs/redteam.md](docs/redteam.md) 与 [docs/execution-plan.md](docs/execution-plan.md)。

## 进度(Day 1–13)

| Day | 节点 | Tag | 状态 |
| --- | --- | --- | --- |
| 1 | 骨架、样本包、项目宪法 | `v0.1.0` | ✅ 2026-07-13 |
| 2 | 规范模型与校验器 | `v0.2.0` | ✅ 2026-07-14 |
| 3 | BM25 基线与检索评估 | `v0.3.0` | ✅ 2026-07-16 |
| 4 | 混合检索与消融表 ⚑重型红队 | `v0.4.0` | ✅ 2026-07-16 |
| 5 | 带引用的 RAG 问答 ⚑重型红队 | `v0.5.0` | ✅ 2026-07-17 |
| 6 | API 与本地 demo | `v0.6.0` | ✅ 2026-07-17 |
| 7 | 校验修复 agent | `v0.7.0` | ✅ 2026-07-17 |
| 8 | 评估红队:攻击自己的 RAG ⚑重型红队 | `v0.8.0` | ✅ 2026-07-18 |
| 9 | 证据链与机器可读性 | `v0.9.0` | ✅ 2026-07-18 |
| 10 | 按需真栈部署与收尾 | `v1.0.0` | ✅ 2026-07-18 |
| 11 | 图谱增强检索(KG-RAG 切片) | `v1.1.0` | ✅ 2026-07-19 |
| 12 | 多模态入库与问答(describe-then-index + G15 二次看图)⚑重型红队 | `v1.2.0` | ✅ 2026-07-20 |
| 13 | 性能与推理策略实验(mp / profile→numba / ToT / asyncio)⚑重型红队 | `v1.3.0` | ✅ 2026-07-21 |

基准表、消融表、对抗评估结果附在英文 README 对应节点下方(中文版为压缩镜像,
不重复搬运基准表);每个数字附复跑命令(不可复现的数字不进 README — INV-5)。

## Roadmap(诚实分层)

- **Implemented**:`inspect` CLI(包摘要、JSON 输出、加固的 XML 解析);
  合成样本包 a/b/c 及可枚举违规清单(VIO-1..8);规范 Pydantic 模型
  (含结构化 applicability);四层校验器(语法 → 项目 mini-XSD → BREX →
  跨文件引用图),`validate` 与单模块查询 `dm`;保标识符 BM25 基线 + 人工标注
  golden set 评估(`search`、`eval retrieval`);Vespa 稠密检索(Qwen3-8B、
  revision 锁定)、混合 RRF + 交叉编码器重排、包级作用域检索、四模式消融与生成的
  基准表(`index`、`eval ablation`);带强制引用或显式拒答的问答——三道 fail-closed
  门(重排阈值、LLM 可答性、逐字引用确证)——`query`(Day 5);本地 demo
  (FastAPI 后端 + Streamlit 哑客户端、SSE 流式带召回回撤、上传事务化)
  `make demo`(Day 6);LLM 主导的 ReAct **修复 agent**,诊断 L0–L3 校验 finding
  并提议最小结构化 patch,仅当确定性校验器复跑通过才采信,默认 dry-run、
  批准后写入 `--apply`(逐 patch 人工闸、绝不静默——宪法 §1.3)`repair`(Day 7);
  **对抗评估** harness——32 例 golden 集、异构双裁判(Codex + agy)+ Cohen's κ
  人工锚定 + 行为确定性判分——`eval adversarial`(Day 8);Neo4j 依赖图**影响查询**
  (反向 `dmRef` 遍历、环安全、限深)`graph impact` + 机器可读证据链(`llms.txt`、
  [docs/EVIDENCE.md](docs/EVIDENCE.md)、[docs/AI-COLLABORATION.md](docs/AI-COLLABORATION.md))
  (Day 9);**按需真栈部署**——token 门控 Cloud Function 拉起停机 GCP VM 跑完整
  `make demo` 拓扑,多层 fail-closed 费用围栏(VM 内闲置 + 硬顶关机、进程内 LLM 花费
  配额、共享门钥、公网模式上传/trace 熔断)见 [deploy/](deploy/runbook.md)(Day 10);
  **图谱增强检索**——确定性实体链接(regex + 语料词典、无 LLM)+ 1-2 跳 `REFS` 扩展
  作第三路 RRF(`hybrid-graph` 模式),人工标注多跳 golden 集,消融诚实结论:rerank
  后逐位不变(Day 11);**多模态入库/问答**——describe-then-index(VLM 描述离线相
  SHA-256 绑定、索引相无 VLM 只 ground 声明集)+ G15 二次看图多采样共识 fail-closed
  拒答(Day 12);**性能与推理策略实验**——多进程分片(INV-2 逐字节等价)、asyncio
  I/O 编排、ToT best-of-N 确定性验证器选优(Day 13)
- **Toy-scale**:合成样本包规模、单机模拟分布式;修复 agent 的沙箱是应用层围栏
  (import/argv 白名单 + 临时目录 jail + 资源上限),非 OS 级隔离;demo 单用户、
  仅 loopback、无鉴权;**按需公网部署单访客 + 共享门钥 + 明文 HTTP**(TLS/逐收件方
  会话鉴权切片外,见 [docs/reviews/day10.md](docs/reviews/day10.md));VLM 通道
  (MiniMax 代理)不稳定,靠重试 + 多采样共识兜底(Day 12);Day 13 是实验日——玩具
  语料 CPU 不够重,mp 无加速、ToT repeat=3 无提升但 2.76× 成本(诚实登记)
- **基于证据否决**:SPLADE 与 ColBERT——Day 4b 闸在复核的消融上保持关闭
  (决策 + 复评触发见 [docs/adr/0001-day4b-gate-stays-shut.md](docs/adr/0001-day4b-gate-stays-shut.md));
  **numba / 自写 Rust·PyO3 / Python free-threading**(Day 13)——profiler 显示本语料
  无纯数值/Python 侧 CPU 瓶颈,numba"无靶"、Rust·free-threading 保持证据门/叙事
  (见 [docs/adr/0003-day13-rust-gate.md](docs/adr/0003-day13-rust-gate.md));latency
  关键路径**已消费** Rust(Tantivy BM25、向量库)——以 informed-consumer 方式取得
  Rust 性能而非自写扩展
- **Planned**:完整 RDF/SPARQL 知识图谱(最小依赖图查询切片已 Day 9 落地、图谱检索
  第三路已 Day 11 落地,见 [docs/adr/0002-minimal-graph-query-slice.md](docs/adr/0002-minimal-graph-query-slice.md);
  完整图谱 / 版本语义建模 / 多跳 SPARQL 仍规划中)、vLLM 本地 serving、GNN、形式化验证
  (见 [docs/project-design.md](docs/project-design.md));**Day 8 红队遗留**:数字/单位
  感知匹配(`125 Nm` 不应满足 `25 Nm`)、裁判熔断、index content-hash/epoch
  (见 [docs/reviews/day8.md](docs/reviews/day8.md))

## 仓库导览

| 入口 | 内容 |
| --- | --- |
| [docs/constitution.md](docs/constitution.md) | 业务场景设定 + 8 条项目不变式(最高约束) |
| [docs/execution-plan.md](docs/execution-plan.md) | 执行主计划与每日验收标准 |
| [docs/project-design.md](docs/project-design.md) | 完整设计、JD 覆盖矩阵、里程碑 |
| [docs/specs/](docs/specs/) · [docs/reviews/](docs/reviews/) · [docs/journal/](docs/journal/) | 每日证据链:SPEC / 红队+裁决 / 学习日志 |
| [docs/discussions/](docs/discussions/) | 蒸馏的设计讨论:问题 → 选项 → 决定 → 理由 |
| [docs/architecture/](docs/architecture/README.md) | 架构快照与变更基准(文件清单、数据流、配置、选型、API/demo) |
| [docs/research/](docs/research/README.md) · [docs/gemini-deepresearch/](docs/gemini-deepresearch/) | 每日深度调研报告 + 未知点扫描(研→读→扫 学习循环) |
| [docs/adr/](docs/adr/) | 架构决策记录(Day 4b 关门、最小图查询切片、Day 13 Rust/free-threading 证据门) |
| [docs/redteam.md](docs/redteam.md) · [docs/local-services.md](docs/local-services.md) | 红队 recipe;本地 Vespa/Neo4j/MiniMax 服务手册 |
| [docs/tutorials/00-overview.md](docs/tutorials/00-overview.md) | 零基础教程系列(中文) |
| [samples/](samples/README.md) | S1000D 样本说明与许可证核查记录 |
| [CLAUDE.md](CLAUDE.md) | AI 实现方的操作规则与角色边界 |

## Quickstart

```bash
uv sync --locked                               # Python 3.12 + 依赖(需要 uv)
make test                                      # ruff + pytest
uv run learnarken inspect samples/package-a    # 查看样本包摘要
uv run learnarken validate samples/package-b   # 四层校验 findings
```

`inspect`/`validate` 离线可跑。检索、问答与修复路径(`index`、`query`、
`repair`、`make demo`)需要本地服务(Vespa + Neo4j)在跑,以及 repo 根目录的
`.env`(`MINIMAX_*`、`NEO4J_*`),详见
[docs/local-services.md](docs/local-services.md)。其中 `repair` 每条 finding 会驱动
一次 LLM ReAct 循环;`repair --apply` 仅在逐 patch 人工批准后才写盘(宪法 §1.3)。
