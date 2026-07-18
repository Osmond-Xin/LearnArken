# Day 9 未知点扫描 — 证据链与机器可读性（`v0.9.0`）

> **AI-generated**（Claude 实现方，2026-07-18，研→读→扫 第三步）。交叉引用：
> `docs/gemini-deepresearch/day9-AI Verifiable Repo Research.md`（官方 DR 报告）、
> `docs/tutorials/12-interview-prep.md`（面试准备，武器③=证据链）、
> execution-plan.md §Day 9、`docs/adr/0002-minimal-graph-query-slice.md`、
> `docs/handoff/day8.md` §6。按 Anthropic "Finding Your Unknowns" 四象限做盲区扫描。
>
> **边界声明**：本文只做扫描与深讲，**不代写 SPEC 决策层**（INV-6 / CLAUDE.md
> 角色边界）。文末「待决策层拍板的张力」列的都是判断题，等 Yi Xin 手写
> `docs/specs/day9.md`——有歧义先问，不猜。

## 本项目的落地锚点（Day 9 不是造新能力，是把已有证据串成可核查的链）

Day 9 与前八天不同:**基本不写业务代码**(唯一的代码交付是依赖图查询),主体是
把 repo 里**已经存在**的证据、流程、数字整理成「陌生 AI agent 5 分钟可核查」的形态。
所以第一步是认清「素材已在仓库里,别重造」:

- **README 已有一批带复跑路径的数字**(EVIDENCE.md 的直接原料):
  - 分块消融表 `README.md:99`(structure-aware Recall@10 0.93 / nDCG 0.83,zero-hit 0.40);
  - Embedding provider 对比 `README.md:130`(Qwen3-8B **0.99/1.00/0.87/0.90** 击败
    MiniMax remote 0.50/0.68);
  - 端到端 RAG 模式表 `README.md:161`(含 p50 延迟);
  - Day 8 κ 校准(Codex **0.737** / agy **0.667**,`eval/results/day8-kappa.json`)、
    X-01 聚合缺陷确定性消除 3/3→0/3、裁判有据性 0.53→0.63。
  - 每个数字**都有**冻结 artifact + 固定 seed + 复跑命令(INV-5),散落在
    `eval/golden/`、`eval/results/`、`tools/*.py`、各 handoff——**EVIDENCE.md 的工作
    是汇总成一张映射表,不是重新测**。
- **不可伪造的人类产出已成体系**(AI-COLLABORATION.md 的直接原料):
  `docs/specs/`(人写决策层)、`docs/reviews/`(AI 红队 Part1 + 人裁决 Part2)、
  `docs/journal/`(人写)、`docs/discussions/`(AI 蒸馏人审)。DR §「不可伪造的人类
  产出」要的「决策记录 + 纠偏日志」我们全有——**AI-COLLABORATION.md 是给已存在的
  流程贴一张导览图 + 显式术语,不是发明工作流**。
- **供应链透明已实践**:`git log --grep='Co-Authored-By'` 命中——DR §「激进透明度」
  的 Co-Authored-By 诚实标注**已是既成事实**,AI-COLLABORATION.md 只需指出来。
- **agents.md 的角色已被 CLAUDE.md 占位**:DR §「agents.md 崛起」讲的「面向代理的
  行为宪法」= 本仓库的 `CLAUDE.md` + `docs/constitution.md`。我们有其实,缺其名。
- **依赖图查询的地基已铺好**:`src/learnarken/graph/store.py` 已有
  `(:DM)-[:REFS]->(:DM)` 边(Day 5 index-time sync,`store.py:138`)与
  interface ③ 的 `facts()`。Day 9 的接口① = 在**已存在的 REFS 边**上加一个
  **反向传递闭包**查询(「谁依赖 X」= `MATCH (a)-[:REFS*]->(x)`)——不是新建图。

## 象限扫描

### 已知的已知(今天/实现期要动手的)

- **`docs/EVIDENCE.md`**:claim → 证据映射表。DR §「Evidence Mapping」给了分级模板
  (公开事实 / 审计披露 / 合理推演 / 待核验假设)。落到本项目 = 每行对外声明配
  ①声明文本 ②证据容器(golden/artifact/trace 路径)③复跑命令 ④诚实分层标签
  (Implemented / Toy-scale / Planned,INV-7)。**指令级精确**(DR §「容器谬误」):
  给命令不给截图。
- **`docs/AI-COLLABORATION.md`**:AI-first 工作流说明。execution-plan 硬性要求:
  ①SPEC/红队/裁决样例 + 三道理解闸 + 「哪些必须人做」清单;②**显式用
  adversarial validation 术语**,并注明与 ML 传统义(分布偏移)的区别。DR §
  「Adversarial Validation 语境演变」+ tutorial 12 §问题3/§09 术语卡是弹药。
  项目三层实践现成:critic 攻答案 / Day 8 攻评估 / 红队攻代码。
- **根目录 `llms.txt`**:AnswerDotAI 标准(DR §「llms.txt 规范」)。强制结构:H1
  项目名 → blockquote 一句话摘要 → 可选正文 → H2 分节的 `[文件](路径): 说明`
  链接映射 → `## Optional` 可丢弃节。**干瘪陈述句**,禁营销词(DR 坑#1)。
- **依赖图查询(接口①,ADR-0002)**:在 `graph/store.py` 加「DM X 被废弃影响哪些
  程序」= 反向 REFS 传递闭包。CLI 暴露一条查询命令。**超时按 INV-8 裁为设计稿**
  (ADR-0002 Consequences 明写:图切片是第一个被砍回设计草稿的)。
- **复盘 specs/reviews/journal 全目录补漏**:handoff §5 已点名两处——`docs/journal/day8.md`
  表头占位 `Day N — <date>` 待改(**AI 不碰 journal**,只能提示 Yi Xin 改);Day 8
  backlog(#8 index epoch / #9 trace 明文 payload)是否入 Roadmap 章节。
- **INV-4 fail-closed 落到图查询**:Neo4j 不可达时 `GraphError` 已 fail-closed
  (`store.py:52`),查询命令必须显式拒答/报错,不静默返回空集。

### 已知的未知(动手前须由决策层定 —— 见文末张力清单)

1. **EVIDENCE.md 要不要覆盖「简历行」,怎么覆盖而不违 INV-1**。execution-plan
   §Day 9 原话是「每条对外声明(**简历行**、README 数字)」。但 INV-1 红线:
   **个人求职文档永不进 repo**(简历唯一事实源在非提交的 `resume-master/`)。
   张力:映射「简历声明→repo 证据」需要引用简历内容,而简历内容不能进公开仓库。
   是只映射 README/repo 内的对外声明、简历侧单独在私档做?还是在 EVIDENCE.md 里
   用「能力声明」的抽象措辞(不含简历原文数字)反向指向证据?**决策题,不猜**。
2. **数字进 EVIDENCE.md/llms.txt 是手写还是从 artifact 生成**。DR 坑#3 是本日最
   致命陷阱:「宏观声明与底层证据数据不一致」在机器核验下直接判「诚实度缺失」。
   README 数字目前是手写的(如 `README.md:132` 的 provider 表)。选项:(a)手写 +
   加一个「数字一致性/死链」测试(CI 校验 EVIDENCE.md 引用的路径存在、引用的
   数字与源 JSON 一致);(b)纯手写 + 人工核对(toy-scale 可接受);(c)模板注入
   (DR 推荐但工程量大)。**要不要写这个校验测试是范围决策**(INV-5 精神倾向 a,
   但工作量归 INV-8 管)。
3. **依赖图查询的接口形态与深度语义**。tutorial 06 §9 说接口①「agent 调 SPARQL」——
   但本项目图在 Neo4j/Cypher 不在 SPARQL,且 Day 9 未必接 agent。选项:(a)独立
   CLI 查询命令(`learnarken graph deps DMC`)输出受影响 DM 列表;(b)进 answer
   pipeline 当工具。**传递深度**:无界 `REFS*` 还是限深 `REFS*1..N`?
   **VIO-7 循环引用是 package-b 故意注入的**(constitution §4),反向传递闭包遇环
   必须有 guard(Cypher `*` 对已访问节点去重,但要测)。**这些是决策层的切片刀**。
4. **「废弃/superseded」是结构语义还是版本语义**。图当前只有 REFS 结构边,**没有
   issue/version 节点**。「DM X 被废弃」若指 issueInfo 版本淘汰,需要版本建模——
   那是新地基,远超 ADR-0002 的「minimal」。若只做「谁引用 X」的结构影响分析(不
   涉版本),则在现有图上一条查询即可。**ADR-0002 界定为 minimal 结构切片,但决策
   层要明确「废弃」的口径**,否则易滑向全量版本图(INV-8 风险)。
5. **agents.md 要不要真的落一个文件**。DR §「agents.md 崛起」+ tutorial 12 §问题2
   把 README/llms.txt/agents.md 三分。我们有 CLAUDE.md 行其实。选项:(a)只在
   AI-COLLABORATION.md/llms.txt 里说明 CLAUDE.md 扮演 agents.md 角色;(b)真加一个
   根目录 `AGENTS.md`(可 include/指向 CLAUDE.md)迎合标准。execution-plan §Day 9
   **没列 agents.md 为交付物**——加它属超范围,须决策层显式点头。
6. **验收测试「陌生 agent 5 分钟定位复跑方式」怎么验**。这是 execution-plan §Day 9
   的「证」。选项:(a)人工走查(Yi Xin 或另一 session 盲读 llms.txt+EVIDENCE.md
   实测);(b)自动化 harness(脚本核验每条 claim 的复跑命令可执行);(c)红队闸
   里让跨宿主模型盲读做核查。**验收方式是决策层的验收标准**。

### 未知的已知(仓库里已成立、但尚未被显式写下/命名的事实)

- **本仓库其实已是 DR 描述的「高可核查仓库」范本**——只是证据散落、没有单一
  入口。Day 9 的本质不是「获得可核查性」,是「把已有的可核查性索引化」。这个认知
  改变工作量估计:偏文档整理,非能力建设(利好 INV-8 不滑点)。
- **「adversarial validation」的项目三层实践早已跑通**,只是没用这个词标注:
  Day 5 critic 攻答案、Day 8 双异构裁判 + 红队攻评估、每日跨宿主 `coding-adversarial-review`
  攻代码。DR/tutorial 要的「术语精确 + 双义区分」是给已有实践**贴标签**。
- **DR 的「不可伪造人类产出」在本仓库有强于 DR 样例的形态**:不只 ADR + 纠偏日志,
  还有**每日红队 Part2 逐条裁决 + 数字人复跑**(INV-6)。这是比 DR 模板更硬的证据,
  AI-COLLABORATION.md 应主打这一点,而非照抄 DR 的通用模板。
- **Co-Authored-By 已是每个 AI commit 的既成实践**(git 历史可查),DR §「供应链
  信任」的建议对本仓库是「已完成」而非「待办」。

### 未知的未知(盲区盘问 —— 最容易在机器核验下翻车的点)

- **死链是本日的头号技术债**(DR 坑#2)。EVIDENCE.md/llms.txt 会引用几十条路径;
  Day 10 收尾、目录调整会移动文件,链接一断,核查 agent 立即判「不可信」。**没有
  死链检查 = 埋雷**。是否在 CI/pytest 加一个「EVIDENCE.md/llms.txt 引用路径存在性」
  测试?(与已知的未知#2 相关,但这里强调的是「路径存在」而非「数字一致」。)
- **数字漂移的自指风险**:Day 8 我们**主动推翻过自己的 README 数字**(0.917→0.979
  被撤,handoff §3)。若 EVIDENCE.md 把一个「后来被推翻的数字」固化成 claim,就制造
  了新的不一致源。EVIDENCE.md 必须以**当前 main 上的冻结 artifact**为唯一源,不引
  历史 handoff 里的过时数字。
- **llms.txt 用于 repo 而非 website 是轻微 off-label**。DR/标准的 llms.txt 面向
  网站(URL 映射)。本项目是 GitHub repo(相对路径映射)。链接该用相对路径还是
  GitHub raw URL?给「只读文件系统的 agent」用相对路径,给「只能 HTTP 抓取的 agent」
  用 URL——**受众假设影响格式**,且要诚实标注这是 repo 适配版(INV-7)。
- **双语仓库的上下文膨胀**(DR 坑#4):repo 有 `README.md` + `README.zh-CN.md`。
  llms.txt 若两版都链,给核查 agent 造 ~重复语义。标准做法:只链规范英文版。但本
  项目定位含中文学习受众——**取舍要显式**。
- **反向传递闭包的性能与环**:package-b 的 VIO-7 环 + 无界 `REFS*` 在真图上是
  组合爆炸风险。toy 语料 43 chunks 无所谓,但**接口设计要「as if distributed」**
  (INV-2):限深、去重、可回滚的语义要在设计稿里写清,即使实现是玩具规模。
- **EVIDENCE.md 自身是不是也要被红队/核查**:如果 EVIDENCE.md 声称「X 数字可由命令
  Y 复现」而命令 Y 实际跑不出 X,这是最尴尬的翻车。**至少要人工复跑抽查几条**
  (INV-6 数字人复跑精神),或让红队闸盲测。

## 必须掌握的深讲(面试级,DR + tutorial 12 交叉)

### 1. 三份文件的受众分工(tutorial 12 §问题2 必考)

- **README.md** → 人类贡献者/recruiter 快扫:视觉、徽章、装配向导、宏观概览。
- **llms.txt** → **外部检索型** LLM/搜索 agent 的**静态快照**:极简结构、Token 高效、
  被动抓取时的知识索引与导览。**它不指导 agent 行为,只帮它理解 repo 是什么、
  证据在哪、怎么复跑**。
- **agents.md(本仓库=CLAUDE.md)** → **仓库内部**协作 agent 的**行为宪法**:代码
  规范、测试命令、依赖约束——主动约束 agent 写码行为。
- 一句话记忆:**llms.txt 是「给外部 agent 的地图」,CLAUDE.md 是「给内部 agent 的
  法律」,README 是「给人的门面」**。三者受众 × 交互时机全不同。

### 2. 容器谬误与指令级证据(DR §「可复现性声明」,本日灵魂)

DEMM 的「容器谬误」:系统产了海量日志(证据的容器),但审计 agent 问某个具体决策时,
杂乱日志无法**属性级重构**该结论 → 证据无效。**破法**:声明↔证据映射要**指令级
精确**——不贴图表,给「标准环境下无副作用可执行的验证指令」+ **SHA 绑定的冻结
数据快照**。这正是 INV-5(固定 seed + 版本化 golden + 可复跑命令)的外部表达。
本项目已合规(每个 README 数字都有 seed + golden + 命令),EVIDENCE.md 是把这份合规
**显式索引化**给机器看。

### 3. Adversarial Validation 双义(tutorial 12 §问题3 / §09 术语卡)

- **传统 ML 义**:检测训练集/测试集**分布偏移**的诊断技术——混两集打二元标签、训
  判别器,若能轻易区分则分布差异大、泛化有风险。**离线数据科学手段**。
- **governed-AI 义(2025–2026)**:「**认知与执行分离**」的纵深防御架构(Parallax
  范式)。假设推理 agent 随时可能被提示注入攻破,在「思考系」与「执行引擎」间强插
  一个**无状态、不共享信任**的验证屏障,以**渐进确定性**(静态规则 → 无 LLM 分类器
  → human-in-the-loop)审查每次 API/DB 写入。**运行时架构手段**。
- **本项目对应**:Day 6 SSE + fail-closed、Day 7 修复 agent 的「批准后才写入 + 沙箱
  执行」、Day 8 双异构裁判 + 交集判定——都是「模型提建议、运行时握绝对授权边界」
  (DR §Agent Trust Boundary)的兑现。AI-COLLABORATION.md **必须写明这个双义区分**
  (execution-plan 硬性要求),否则面试被追问「和分布偏移啥关系」会翻车。

### 4. 依赖图接口①的面试话术(tutorial 06 §9 / 12 §知识图谱)

「关系问题查图,内容问题查文本」——「DM X 废弃影响哪些程序」是**关系问题**,答案
在**边**里不在文档里,一条属性路径查询(反向 `REFS*`)顶传统递归 CTE。选 Neo4j/
Cypher 还是 RDF/SPARQL 是选型题(tutorial 06:RDF 赢在 IRI 整合/命名图版本化,
Neo4j 赢在 Cypher 易用/图算法生态——**要会夸对手**)。本项目 Day 5 已落 Neo4j,
Day 9 接口①是在其上加影响分析查询,**规模玩具、接口按分布式设计**(INV-2)。

## 待决策层拍板的张力(等 Yi Xin 手写 `docs/specs/day9.md`,不猜)

| # | 张力 | 选项概览 | 关联约束 |
| --- | --- | --- | --- |
| T1 | EVIDENCE.md 是否覆盖「简历行」及如何不违 INV-1 | 只映射 repo 内对外声明 / 抽象能力声明反指证据 / 简历侧留私档 | INV-1、execution-plan §Day 9 |
| T2 | EVIDENCE.md/llms.txt 数字:手写+一致性&死链测试 / 纯手写人工核 / 模板注入 | 影响 INV-5 兑现强度与工作量 | INV-5、INV-8、DR 坑#2#3 |
| T3 | 依赖图查询接口形态与深度:独立 CLI / 进 pipeline;无界 vs 限深 `REFS*`;环 guard | 决定实现量与是否触 INV-8 裁为设计稿 | ADR-0002、INV-2、INV-4、VIO-7 |
| T4 | 「废弃/superseded」口径:结构影响分析(现图可做) vs 版本语义(需新建模) | minimal 切片 vs 滑向全量版本图 | ADR-0002 minimal、INV-8 |
| T5 | 是否真落一个根目录 `AGENTS.md`(超 execution-plan 列表) | 只文档说明 CLAUDE.md 行其实 / 真加文件 | execution-plan §Day 9 范围、INV-6 |
| T6 | 验收「陌生 agent 5 分钟核查」怎么验 | 人工盲走查 / 自动 harness / 红队闸盲测 | execution-plan §Day 9「证」 |

**环境自检附注(给 Yi Xin,与本扫描并列)**:
- 分支纪律已就位:`feat/day9` 从 `main` HEAD 新开,`git log main..HEAD` 空。
- `make test` 268 passed + 9 skipped;`make lint` All checks passed。
- Vespa/Neo4j 均在 `127.0.0.1`(容器 up)。codex/agy CLI 在;`gemini` CLI 二进制虽在
  但按 handoff 已死(IneligibleTierError),agy 是 Gemini 唯一通道。
- **⚠️ 与 handoff §7 的出入**:handoff 称「`.env` 只有 `MINIMAX_*`,无 `NEO4J_*`」,
  实测 `.env` **含 `NEO4J_USER` + `NEO4J_PASSWORD`**(`graph/store.py:44` 也读它们)。
  handoff §7 该条不准,以实测为准。不影响运行(store 有 fallback),但记录纠偏。
