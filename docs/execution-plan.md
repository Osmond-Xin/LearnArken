# LearnArken 执行计划(AI-first 日节点版)

> 本文档是项目的**执行主计划**:目标是约 10 个工作日内交付一个可演示、有实测基准的最小闭环,
> 而不是一次性实现 [project-design.md](project-design.md) 的全部 M0–M8。
> **一天一个节点**:每个节点 = 学(教程)→ 规(自己写 SPEC)→ 做(AI 实现)→
> 审(红队)→ 裁(本人裁决)→ 证(验收)→ 交(tag + release notes)。
> 本文档可随仓库公开。

## 为什么是 AI-first(先读这个,防止用错力气)

旧版计划的隐含前提是"代码全部自己手写",按周推进。这个前提已经过时:
2026 年的真实工程节奏是 **人写规格与判断,AI 写实现,人负责验证与裁决**。
继续按"全手写"规划有两个害处:交付慢到失去展示价值;且向雇主传递了一个
错误信号——不会用 AI 的工程师。

因此本计划把"证明我会写代码"改为证明三件更值钱的事:

1. **我能把模糊目标拆成 AI 可执行的规格**(每日 SPEC,人写);
2. **我能组织多智能体互相对抗来保证质量**(红队评审 + 本人裁决,留痕);
3. **我理解产出的每一行核心逻辑**(裁决记录 + 手写学习日志 + 口述关,不可伪造)。

这三件事同时服务两个目标:**自我学习掌握**(不理解就无法裁决红队 findings),
**向雇主证明能力**(审批人和招聘方的 AI agent 都能沿证据链核查)。

## 范围(与旧版一致,交付节奏压缩)

**切片内**(Day 1–10):合成样本包 → 规范模型与校验器 → BM25 基线与评估 →
混合检索(dense + RRF + rerank)与消融表 → 带引用的 RAG 问答 →
校验修复 agent → 评估红队 → API + 在线 demo。

**切片外**(README Roadmap 标 Planned):RDF/SPARQL 全量知识图谱(**最小依赖
图查询已于 Day 4 复评拉回切片,挂 Day 9——ADR-0002**)、世界模型、vLLM 本地
serving、TensorRT-LLM、Rust 扩展、GNN、形式化验证。SPLADE 与 ColBERT 曾列
此处,后改为 Day 4b 证据开门项,**门未开、已按证据关闭**(ADR-0001)。

> 注:旧版把"多智能体"整体划到切片外。AI-first 之后实现成本大幅下降,
> 因此把两个最有面试价值的 agent 场景收回切片内(Day 7–8),其余仍推迟。

## 每日循环(全程纪律,替代旧版周节奏)

每个节点固定七步,当天走完:

| 步 | 动作 | 产出 | 谁做 |
| --- | --- | --- | --- |
| 1a 研 | 深度调研当日领域:背景、发展源流、主流特色、未来方向、最佳实践、必会技巧与坑(中文) | `docs/research/dayN-report.md` | AI(Gemini Deep Research) |
| 1b 读 | 读调研报告 + 当日教程,列出 3 个"实现时要验证的概念" | 教程笔记(可简) | 人 |
| 1c 扫 | 未知点扫描(blind spot pass)+ 必会知识点深讲,对照报告与教程 | `docs/research/dayN-unknowns.md` | AI(Claude) |
| 2 规 | 写当日 SPEC:目标、接口、验收标准、明确不做什么 | `docs/specs/dayN.md` | **人写,AI 只许提问** |
| 3 做 | AI 按 SPEC 实现,小步 commit | feature branch | AI(Claude Code) |
| 4 审 | 第二个独立 agent **只读**红队:P0/P1/P2 findings + 终判 SHIP / REVIEW_NEEDED / DO_NOT_MERGE | `docs/reviews/dayN.md` 前半 | AI(Codex / Gemini / MiniMax) |
| 5 裁 | 逐条裁决 findings:accept / reject + 一句话理由;红队报的数字必须自验 | `docs/reviews/dayN.md` 后半 | **人,不可外包** |
| 6 证 | `make test` 全绿 + 当日验收标准逐条打勾 | CI 绿 | 人跑,AI 修 |
| 7 交 | squash merge → tag → release notes(含当日基准数字)→ 手写学习日志 | `docs/journal/dayN.md` | 人写日志 |

> **学习流程 v2**(2026-07-15 起、Day 4 生效,Yi Xin 指示):步骤 1 由"读教程"
> 升级为"研→读→扫"三段。方法论来自 Anthropic《A Field Guide to Claude Fable:
> Finding Your Unknowns》的未知象限框架——把 unknown unknowns 显式化是 agentic
> 工作方式的核心技能;对应到学习:先用深度调研建立领域全景(压缩 unknown
> unknowns),再由实现方 AI 做盲区扫描 + 必会点深讲(把 known unknowns 讲透),
> 然后按原教程实践。调研通道:首选 Gemini 官方 Deep Research
> (Interactions API,agent `deep-research-preview-04-2026`,
> `tools/deep_research.py`,需付费级 `GEMINI_API_KEY`;或在 Gemini App 手动跑
> 后存档);兜底为 `agy`(Antigravity CLI)+ Gemini 3.1 Pro 单次联网调研,
> 产物必须标注"模拟"。`gemini` CLI 个人免费层已被 Google 停用,不是可用通道。

**理解三道闸**(招聘方核查的就是这三样,也是自学的强制机制):
- **SPEC 是人写的**——拆解能力装不出来;
- **裁决记录是人写的**——不理解实现就无法判断红队 finding 真假;
- **学习日志是人写的**——固定三问:今天学到什么?AI 错在哪、我怎么发现的?
  我拒绝了 AI 的什么方案、为什么?

**红队怎么跑**(已在另一个个人项目中验证的工作流,直接复用):
- 轻量:`adversarial-review` 类交叉评审——让非实现方的模型(Codex/Gemini)只读审查
  diff 与设计,输出分级 findings;
- 重型(用于 Day 4/5/8 这类有数字结论的节点):Producer → Challenger → Reviser
  多轮收敛循环,直到 Challenger 无新 P0/P1;
- 铁律:红队只读不写;红队报的任何数字,合并前本人重跑一遍。

**工程纪律**(不变项):
- conventional commits;AI 生成的 commit 带 `Co-Authored-By`,诚实留痕;
- 每天一个 feature branch → 一个 PR → squash merge;PR 描述 = SPEC 链接 + 验证方式;
- 每天一个 GitHub issue(当日节点),`closes #N` 关联;
- 安全红线:第一个 commit 配好 `.gitignore`(`.env`、密钥、缓存);
  样本只用自造合成 XML,不放任何真实 S1000D 内容;
- **滑点规则**:一个节点最多占用 2 个日历日,到点必须裁剪范围收口打 tag,
  砍掉的写进 Roadmap,不许让计划整体漂移。

---

## 阶段一:核心闭环(Day 1–6)

### Day 1 — 骨架与样本包(`v0.1.0`)

**学**:[tutorials/01 标准与 XML](tutorials/01-standards-and-xml.md)、
[tutorials/10 Python 工程](tutorials/10-python-engineering.md)

**做**:
- [ ] 仓库初始化:`pyproject.toml`、ruff、pytest、pre-commit、GitHub Actions CI
- [ ] CLI 骨架:`learnarken inspect <package>`
- [ ] 合成 S1000D-like 样本包 ×2:`samples/package-a`(合法)、
      `samples/package-b`(含 5 类已知违规),附 README 说明相对真实 S1000D 简化了什么
- [ ] `docs/adr/001-scope.md`:范围与 AI-first 工作流决策记录

**证**:CI 绿;`inspect` 输出包结构摘要;两个样本包各有冒烟测试。

### Day 2 — 规范模型与校验器(`v0.2.0`)

**学**:复习 [tutorials/01](tutorials/01-standards-and-xml.md) 的 BREX/SNS 节

**做**:
- [ ] Pydantic 规范模型:DMC、数据模块、publication module、引用、warning/caution、
      applicability(结构化断言 + displayText——为 Day 3 chunk 元数据奠基)
- [ ] 四层校验器:L0 XML 语法合法 → L1 结构 schema 校验(简化 XSD)→
      L2 单文件 BREX,3–5 条 Schematron 式断言(rule id、severity、path、
      message、fix hint)→ L3 跨文件完整性(dmRef 悬空、ICN 缺失、
      DM/DML 版本错位、循环引用)——L3 的引用图为将来知识图谱打基础
- [ ] `learnarken validate <package>` 输出结构化 findings(JSON + 人读两种格式,
      按层分组);低层失败则该文件 fail-closed,不进高层
- [ ] `learnarken dm <package> <DMC>`:单 DM 详情——元数据模型、内容统计
      (步骤/警告/引用数)、评估过的 BREX 规则数、issueDate 与生效/失效时间
- [ ] golden 测试:每条规则至少一个通过用例 + 一个违规用例

**证**:package-a 全过;package-b 产出精确到行/路径、与违规清单一一对应的
findings;`learnarken dm` 对任意 package-a DMC 可查;`pytest` 覆盖每条规则。

### Day 3 — BM25 基线与检索评估(`v0.3.0`)

**学**:[tutorials/02 检索基础](tutorials/02-information-retrieval.md)

**做**:
- [ ] 结构感知分块器:按步骤/warning 边界切,chunk 携带 DMC/任务/
      applicability 元数据(适用性来自 Day 2 模型)
- [ ] BM25 索引与查询(Tantivy 或 rank-bm25)
- [ ] golden set:30–50 个「问题 → 相关 chunk」标注对——**标注必须人做**
      (这是检索评估的判断力所在,也是面试金料),AI 只许起草候选问题
- [ ] `learnarken eval retrieval`:Recall@k、MRR、nDCG
- [ ] README 加入第一张基准表(哪怕只有 BM25 一行)

**证**:评估脚本可复现(固定随机种子、版本化 golden set);基准表进 README。

### Day 4 — 混合检索与消融表(`v0.4.0`)⚑ 重型红队节点

**学**:[tutorials/03 向量与 ANN](tutorials/03-embeddings-and-vector-search.md)、
[tutorials/04 高级检索](tutorials/04-advanced-retrieval.md)

**做**:
- [ ] 稠密检索:BGE 或 E5 embedding + Vespa(docker;2026-07-14 Day 3
      会议裁决由 Qdrant 改选 Vespa,理由与取舍见 docs/discussions/day3.md D2)
- [ ] RRF 融合(BM25 + dense)+ 交叉编码器重排(bge-reranker 类)
- [ ] **消融表**:BM25 / dense / hybrid / hybrid+rerank 四行 ×
      Recall@10 / nDCG@10 / p50 延迟
- [ ] 失败案例分析:至少一个 dense 输给 BM25 的零件号/标识符查询实例,
      写进 `docs/notes/`
- [ ] 消融数字过重型红队(Challenger 攻击评估方法本身:泄漏?种子?样本量?)

**证**:消融表进 README;红队裁决记录落盘;数字本人复跑一致。

> **4a/4b 拆分(spec day4 Q7 + D5 裁决,记录于 2026-07-16 收口)**:
> Day 4a = LangChain 默认栈 + Qwen3-8B 稠密 + Vespa + 四行消融,`v0.4.0`;
> Day 4b = SPLADE/ColBERT,**证据开门**——仅当 4a 的 per-category 表暴露
> 具体缺口才立项,无独立 tag。**结果:门未开,已关闭**(paraphrase 缺口被
> dense 关死至 1.00,identifier 未输;ADR-0001,内含未来若开门 MaxSim 走
> Python 侧的预裁)。
>
> 🔓 本日完成 = Projects 简历行与 AI 赛道解锁(见私档,此处不展开)。
>
> 🔁 **复评点(Day 4 收口时执行)**:重新评估是否把一个**最小 RDF/SPARQL
> 依赖图查询**从 Planned 拉回切片(挂 Day 9 前后)。理由:Knowledge-Graph RAG
> 出现在目标岗位的职位标题里(详见私档),是当前切片唯一的标题级关键词缺口;
> 教程 [06 知识图谱](tutorials/06-knowledge-graph.md) §9 已备好"图谱 × RAG"
> 的三个组合接口。决策(拉回/维持 Planned)与理由记入 ADR。
> **→ 已执行(2026-07-16):拉回,挂 Day 9(ADR-0002)。**

### Day 5 — 带引用的 RAG 问答(`v0.5.0`)⚑ 重型红队节点

**学**:[tutorials/05 RAG](tutorials/05-rag.md)、
[tutorials/07 LLM 原理](tutorials/07-llm-fundamentals.md)

**做**:
- [ ] ~~Claude API~~ **MiniMax-M3** 回答生成(2026-07-16 Day 5 开题裁决,
      见 specs/day5.md 决策 2):结构化 prompt、引用标注(chunk id → 原文出处)
- [ ] 图谱同步 + 接口③上下文注入(ADR-0002 修订:图切片前半提前到本日)
- [ ] 拒答逻辑:证据不足时 fail-closed,不编造
- [ ] answer trace JSON:query → 检索结果 → prompt → 回答 → 引用,全链路落盘
- [ ] 回答质量小评估:citation coverage + groundedness,**人工抽查 20 例**
- [ ] `learnarken query "<question>"` 端到端可用

**证**:10 个演示问题全部带引用回答或明确拒答;trace 文件可回放。

### Day 6 — API 与本地 demo(`v0.6.0`)

**学**:[tutorials/11 合规与可观测](tutorials/11-compliance-observability.md)(选读审计节)

**做**:
- [ ] FastAPI 端点:`POST /validate`、`POST /query`(含 OpenAPI 文档)
- [ ] Streamlit demo 界面:上传/选样本包 → 校验报告 → 问答带引用
- [ ] `make demo` 一条命令本地起全套

**证**:本地 demo 全流程可走通;`make test` / `make demo` 各一条命令。

## 阶段二:差异化(Day 7–10)

> 这四天是与"又一个 RAG demo"拉开距离的部分:两个 agent 场景 + 把
> "AI-first 工作流本身"变成可核查的作品。

### Day 7 — 校验修复 agent(`v0.7.0`)

**学**:[tutorials/09 智能体](tutorials/09-agents.md)

**做**:
- [ ] `learnarken fix <package>`:agent 读取 Day 2 校验器的 findings,
      结合检索到的规范上下文,生成修复 patch(dry-run 默认,`--apply` 显式)
- [ ] 每个 patch 附带理由与引用;修复后自动重跑校验器闭环验证
- [ ] 评估:package-b 的 5 类违规,修复成功率表(成功/失败各分析一例)

**证**:校验 → 修复 → 复验闭环演示可录 GIF;失败案例分析进 `docs/notes/`。

### Day 8 — 评估红队:攻击自己的 RAG(`v0.8.0`)⚑ 重型红队节点

**学**:复习 [tutorials/05](tutorials/05-rag.md) 评估节

**做**:
- [ ] 对抗评估集:同义改写、跨模块陷阱问题、无答案问题、零件号扰动,≥30 例
- [ ] LLM-as-judge 自动 groundedness 评分 + 与 Day 5 人工抽查对齐校准
      (报告 judge 与人工的一致率,不许只报 judge 数字)
- [ ] 修复至少 2 个红队暴露的真实缺陷,前后指标对比进 README

**证**:对抗评估可一条命令复跑;"发现缺陷 → 修复 → 指标变化"完整证据链。

### Day 9 — 证据链与机器可读性(`v0.9.0`)

**学**:[tutorials/12 面试准备](tutorials/12-interview-prep.md)

**做**:
- [ ] `docs/EVIDENCE.md`:每一条对外声明(简历行、README 数字)→
      指向仓库内证据(评估脚本、golden set、消融表、trace)的映射表,
      **专为审批人和招聘方 AI agent 的核查路径设计**
- [ ] `docs/AI-COLLABORATION.md`:本仓库的 AI-first 工作流说明——SPEC 样例、
      红队记录样例、裁决样例、三道理解闸,以及"哪些必须人做"清单;
      **显式使用行业术语 adversarial validation** 描述红队工作流
      (governed-AI 行业即用此语;求职材料同步用词,见私档),并注明与
      ML 传统含义(分布偏移检测)的区别
- [ ] 根目录 `llms.txt`:给 AI agent 的仓库导览(是什么、证据在哪、怎么复跑)
- [ ] **依赖图查询**(ADR-0002,已修订):图同步与接口③注入已提前到
      Day 5;本日补齐**依赖查询类**(如"DM X 被废弃影响哪些程序",
      接口①方向);当日超时则按 INV-8 滑点规则优先裁剪为设计稿
- [ ] 复盘 specs/reviews/journal 全目录,补齐缺漏

**证**:一个陌生 AI agent 只读 `llms.txt` + `EVIDENCE.md` 能在 5 分钟内
定位任意一个基准数字的复跑方式。

### Day 10 — 上线与收尾(`v1.0.0`)

**做**:
- [ ] 在线部署:Streamlit Community Cloud 或 HuggingFace Spaces
- [ ] README 定稿:demo GIF、完整基准表、架构图(复用 `docs/diagrams/rendered/`)、
      Quickstart(3 条命令内跑通)、Roadmap 诚实分层(Implemented / Toy-scale / Planned)、
      AI-first 工作流一节(链接 AI-COLLABORATION.md)
- [ ] 口述关:把 [tutorials/12](tutorials/12-interview-prep.md) 的 60 秒陈述
      改写为"已实现"版,脱稿讲一遍并录音自查

**证**:陌生人按 README 10 分钟内跑通;在线 demo 链接可访问。

---

## 阶段三:JD 对位扩展(Day 11–13,v1.0.0 后追加)

> **AI-drafted**(Claude,2026-07-19,待人审):Day 1–10 收口后对照目标岗位 JD
> 复盘(岗位分析见私档,不入仓库),标题级关键词仍有两个缺口:
> **Knowledge-Graph RAG**——图谱已做到影响查询(接口①,Day 9)与上下文注入
> (接口③,Day 5),但**没有进入检索路径**;**Multi-Modal**——全切片纯文本,
> ICN 插图从未入库。各补一个 1–2 日切片。另有一条技能行要求
> **Python mastery(asyncio / multiprocessing / Cython/numba;Rust/C++ 为 plus)**,
> 补 Day 13 性能工程切片,把并发与性能优化变成项目内的基准数字。
> JD 另有一行 **multi-agent(ReAct/ToT/GoT/MCTS)+ world-model +
> counterfactual + adversarial self-critique**:盘点结论是 ReAct(Day 7)、
> 对抗质检(Day 8 + 红队流程)、反事实归因(Day 8 前后对比)、world-model
> 雏形(dry-run 沙箱)已有实现证据,搜索类(ToT/GoT/MCTS)不专开一天——
> 仅并入一个半日**玩具 ToT 实验**挂 Day 13,其余保持"概念掌握 + 适用边界
> 判断"的第二档口径。
> 七步循环、滑点规则(每节点最多 2 个日历日)照旧;**SPEC 决策层仍由人写**,
> 本节只是计划占位,不替代 specs/day11–13.md。

### Day 11 — 图谱增强检索 KG-RAG(`v1.1.0`)

**学**:[tutorials/14 KG-RAG](tutorials/14-kg-rag.md)、
复习 [tutorials/06](tutorials/06-knowledge-graph.md) §9 三接口

**做**:
- [ ] 查询侧实体链接:从 query 识别 DMC/零件号/任务实体——确定性规则
      (正则/词表)优先,不上来就用 LLM
- [ ] 图谱候选扩展(接口②升级为检索路径):命中实体沿引用/依赖边取 1–2 跳
      邻域,作为第三路信号进 RRF 融合(复用 Day 9 引用图,不引入 RDF/SPARQL
      ——全量图谱仍在 Planned,诚实分层)
- [ ] golden set 补跨模块多跳问题(答案分散在引用链多个 DM 上的组合问题),
      标注人做
- [ ] 消融表加一行:hybrid vs **hybrid+graph**(Recall@k / nDCG / zero-hit / p50)
- [ ] 引用增强:回答引用附"图谱路径"(该 chunk 为何相关:X 引用 Y)
- [ ] 失败案例分析:图扩展引入邻居噪声的实例,写进 `docs/notes/`

**证**:消融行进 README;多跳类查询指标提升或**诚实报告不提升**(假设待验证,
不许只报有利数字);数字本人复跑一致。

### Day 12 — 多模态入库与问答(`v1.2.0`)

**学**:[tutorials/15 多模态 RAG](tutorials/15-multimodal-rag.md)、
复习 [tutorials/01](tutorials/01-standards-and-xml.md) ICN 节

**做**:
- [ ] 合成样本包补 ICN 插图 2–3 张(自绘 SVG→PNG 示意图,含 hotspot 编号;
      仍是合成红线 INV-1,不放任何真实图纸)
- [ ] 入库管线 describe-then-index:VLM 对 ICN 生成**受控结构化描述**
      (部件清单、hotspot 编号、警告;schema 约束),进现有索引,chunk 关联
      ICN id;描述与图文件 checksum 绑定
- [ ] 问答:图相关问题的答案可引用 ICN(引用 = 图 id + 描述出处);
      描述覆盖不了的问题 fail-closed 拒答,不看图硬编
- [ ] 小评估:8–10 个看图问题 golden set(答案在图 / 答案在文 / 图文冲突陷阱),
      报告引用正确率,标注人做
- [ ] 失败案例:VLM 幻觉图内细节(编号/箭头)的实例与防线,写进 `docs/notes/`

**证**:demo 里"这个部件在图中哪个位置"类问题带图引用回答;评估一条命令可复现。

### Day 13 — 性能工程与玩具 ToT 实验(`v1.3.0`)

**学**:[tutorials/16 性能工程](tutorials/16-performance-engineering.md)、
复习 [tutorials/10](tutorials/10-python-engineering.md) 并发模型版图、
复习 [tutorials/09](tutorials/09-agents.md) ToT/critic 节

**做**:
- [ ] **asyncio**(I/O 密集):把一条批量外部调用管线(评估批量问答或 Day 12
      的逐图描述)改为 `asyncio.gather` + `Semaphore(k)` 限并发 + 超时/重试,
      报告串行 vs 并发的 wall-clock 对比与所选并发度的理由
- [ ] **multiprocessing**(CPU 密集):多包校验/分块入库按分片并行
      (`ProcessPoolExecutor`,分片藏在抽象后、写入幂等——INV-2 本来的要求),
      测 1/2/4/8 worker 扩展曲线,**分析拐点成因**(pickle 序列化、进程启动
      开销),不许只报最好的一列
- [ ] **profile → numba**:`py-spy`/`cProfile` 定位一个真实热点(候选:BM25
      打分、RRF 融合、精确 cosine),产出三列对比:纯 Python / numpy 向量化 /
      numba `@njit`——收益小就如实报小("知道何时不值得"是本日核心结论之一)
- [ ] **Rust/PyO3 证据开门项**(仿 Day 4b):默认不做,仅当 profile 显示
      Python 侧成为瓶颈才立项;不开门则在 `docs/notes/` 写"知情消费者"
      说明(Tantivy/Qdrant 即 Rust 实现,触发条件与预选路线 PyO3/maturin)
- [ ] 失败案例/边界分析写进 `docs/notes/`:小任务负加速、asyncio await 点
      交错的一个实例
- [ ] **玩具 ToT 实验**(半日,全部复用现有设施):修复 agent 对同一违规
      生成 3 个候选 patch → 各自沙箱复验(Day 7 执行器)+ 打分 → 取最优;
      对 package-b 全部违规跑单候选 vs 3 候选对比:修复成功率 × token 成本
      两列都报——**成本诚实入表**,成功率没涨或涨不抵成本就如实写
      (这正是"ToT 何时不值得"的实测答案);候选生成可用本日 asyncio
      并发,两个主题自然衔接

**证**:并发扩展曲线 + 热点三列对比表进 README;每个数字带复跑命令;
Rust 开门与否有留痕结论;ToT 对比表(成功率 × token 成本)进
`docs/notes/`,结论一句话进 README Roadmap(ToT 从 Planned 改为
Toy-scale measured)。

---

## 完成定义(整个切片的 DoD)

- [ ] 10 个 tag、10 份 release notes、10 份人写的 SPEC / 裁决记录 / 学习日志
- [ ] README:demo GIF + 消融表 + 对抗评估前后对比 + Quickstart + 诚实分层 Roadmap
- [ ] `make test` / `make demo` 一条命令可用;在线 demo 可访问
- [ ] 每个基准数字 30 秒内能从 `EVIDENCE.md` 指到评估脚本和 golden set
- [ ] 每个红队 P0/P1 finding 都有本人裁决记录;红队数字全部有本人复跑记录
- [ ] 60 秒陈述能脱稿;任选一天的 journal,能就"AI 错在哪"展开讲 3 分钟
