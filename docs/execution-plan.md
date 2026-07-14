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

**切片外**(README Roadmap 标 Planned):SPLADE、ColBERT、RDF/SPARQL 全量知识图谱、
世界模型、vLLM 本地 serving、TensorRT-LLM、Rust 扩展、GNN、形式化验证。

> 注:旧版把"多智能体"整体划到切片外。AI-first 之后实现成本大幅下降,
> 因此把两个最有面试价值的 agent 场景收回切片内(Day 7–8),其余仍推迟。

## 每日循环(全程纪律,替代旧版周节奏)

每个节点固定七步,当天走完:

| 步 | 动作 | 产出 | 谁做 |
| --- | --- | --- | --- |
| 1 学 | 读当日教程,列出 3 个"实现时要验证的概念" | 教程笔记(可简) | 人 |
| 2 规 | 写当日 SPEC:目标、接口、验收标准、明确不做什么 | `docs/specs/dayN.md` | **人写,AI 只许提问** |
| 3 做 | AI 按 SPEC 实现,小步 commit | feature branch | AI(Claude Code) |
| 4 审 | 第二个独立 agent **只读**红队:P0/P1/P2 findings + 终判 SHIP / REVIEW_NEEDED / DO_NOT_MERGE | `docs/reviews/dayN.md` 前半 | AI(Codex / Gemini / MiniMax) |
| 5 裁 | 逐条裁决 findings:accept / reject + 一句话理由;红队报的数字必须自验 | `docs/reviews/dayN.md` 后半 | **人,不可外包** |
| 6 证 | `make test` 全绿 + 当日验收标准逐条打勾 | CI 绿 | 人跑,AI 修 |
| 7 交 | squash merge → tag → release notes(含当日基准数字)→ 手写学习日志 | `docs/journal/dayN.md` | 人写日志 |

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
- [ ] 稠密检索:BGE 或 E5 embedding + Qdrant(docker compose)
- [ ] RRF 融合(BM25 + dense)+ 交叉编码器重排(bge-reranker 类)
- [ ] **消融表**:BM25 / dense / hybrid / hybrid+rerank 四行 ×
      Recall@10 / nDCG@10 / p50 延迟
- [ ] 失败案例分析:至少一个 dense 输给 BM25 的零件号/标识符查询实例,
      写进 `docs/notes/`
- [ ] 消融数字过重型红队(Challenger 攻击评估方法本身:泄漏?种子?样本量?)

**证**:消融表进 README;红队裁决记录落盘;数字本人复跑一致。

> 🔓 本日完成 = Projects 简历行与 AI 赛道解锁(见私档,此处不展开)。
>
> 🔁 **复评点(Day 4 收口时执行)**:重新评估是否把一个**最小 RDF/SPARQL
> 依赖图查询**从 Planned 拉回切片(挂 Day 9 前后)。理由:Knowledge-Graph RAG
> 出现在目标岗位的职位标题里(详见私档),是当前切片唯一的标题级关键词缺口;
> 教程 [06 知识图谱](tutorials/06-knowledge-graph.md) §9 已备好"图谱 × RAG"
> 的三个组合接口。决策(拉回/维持 Planned)与理由记入 ADR。

### Day 5 — 带引用的 RAG 问答(`v0.5.0`)⚑ 重型红队节点

**学**:[tutorials/05 RAG](tutorials/05-rag.md)、
[tutorials/07 LLM 原理](tutorials/07-llm-fundamentals.md)

**做**:
- [ ] Claude API 回答生成:结构化 prompt、引用标注(chunk id → 原文出处)
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

## 完成定义(整个切片的 DoD)

- [ ] 10 个 tag、10 份 release notes、10 份人写的 SPEC / 裁决记录 / 学习日志
- [ ] README:demo GIF + 消融表 + 对抗评估前后对比 + Quickstart + 诚实分层 Roadmap
- [ ] `make test` / `make demo` 一条命令可用;在线 demo 可访问
- [ ] 每个基准数字 30 秒内能从 `EVIDENCE.md` 指到评估脚本和 golden set
- [ ] 每个红队 P0/P1 finding 都有本人裁决记录;红队数字全部有本人复跑记录
- [ ] 60 秒陈述能脱稿;任选一天的 journal,能就"AI 错在哪"展开讲 3 分钟
