# Day 9 设计讨论蒸馏 — 证据链与机器可读性

> **AI-distilled**（Claude 实现方，2026-07-18，同 session 蒸馏；INV-6：AI 蒸馏、
> 标注、待 Yi Xin 复核）。来源：day9-unknowns.md 的 T1–T6 张力 + Yi Xin 2026-07-18
> 的口述目标 + 当日三条裁定（clarifying questions）。格式：问题 → 选项 → 决定 →
> 理由。决策层权威见 [docs/specs/day9.md](../specs/day9.md)。

## D1（T1）EVIDENCE.md 映射「简历行」与 INV-1 红线

- **问题**：execution-plan §Day 9 要 EVIDENCE.md 映射「简历行→证据」，但 INV-1
  红线禁止**个人求职文档/简历原文进公开仓库**（唯一事实源在非提交的
  `resume-master/`）。映射需引用简历内容，而简历内容不能公开——直接冲突。
- **选项**：(a) 公开档只放**抽象能力声明→证据**，简历原文数字留私档、反向指回
  公开锚点；(b) 简历行**逐字**进公开 EVIDENCE.md（违 INV-1）；(c) 公开档只映射
  README/repo 声明，简历侧整份留私档单独做（不碰「简历行」要求）。
- **决定（Yi Xin）**：走 **(a)**——公开 `docs/EVIDENCE.md` 只列抽象能力声明→
  repo 证据，**不含简历逐字数字/措辞**；简历行在 `resume-master/` 私档里映射到
  这些公开锚点。招聘方 agent 核查公开矩阵，简历侧向内指、绝不向外泄。
- **理由**：同时兑现「招聘方 AI agent 可核查」与 INV-1，不破红线。这与 DR
  §「供应链信任」的诚实标注同向——公开的是可核查的能力，私有的是个人材料。

## D2（T3/T4）依赖图影响查询的接口形态与遍历语义

- **问题**：最小 Neo4j 图查询（dmRef 反向传递「废弃 X 波及谁」）——独立 CLI 还是
  进 pipeline？无界还是限深？package-b 的 **VIO-7 循环引用是故意注入的**，遍历
  必须防环。且「废弃」是结构语义还是版本语义？
- **选项**：(a) 独立 CLI + 限深（`REFS*1..N`）+ 环去重 + 并联选型接口；
  (b) 独立 CLI + 无界传递闭包；(c) 进 answer/agent pipeline 当接口①工具。
- **决定（Yi Xin）**：走 **(a)**——`learnarken graph impact <DMC>` 独立命令，反向
  dmRef **限深**遍历、**已访问节点去重**（VIO-7 环不再死循环）、Neo4j 不可达
  **fail-closed**（INV-4）；作为 **Graph-RAG 并联选型接口**，**不进主 answer
  pipeline**。「废弃」取**结构影响分析**语义（现有 REFS 边即可），**不建版本/issue
  节点**（那超 ADR-0002 minimal）。
- **理由**：限深+去重是 as-if-distributed 的接口纪律（INV-2），即使实现是玩具
  规模；并联而非入主链，符合 tutorial 06 §9「关系问题查图、内容问题查文本」的
  分工。结构语义守住 ADR-0002 的 minimal 边界，避免滑向全量版本图（INV-8）。若
  当日超时，此切片是第一个被裁回设计稿的（ADR-0002 Consequences）。

## D3（T2）证据防漂移：死链与数字不一致

- **问题**：EVIDENCE.md/llms.txt 会引用几十条路径+数字。DR 两大坑：证据**死链**
  （#2，Day10 目录调整断链→核查 agent 判不可信）、声明与源数据**不一致**（#3，
  机器核验下判「诚实度缺失」）。要不要加自动防护？
- **选项**：(a) 加 pytest：死链（路径存在）+ 数字一致性（与源 artifact 比对）；
  (b) 只加死链检查，数字人工核；(c) 纯手写人工核，不加测试。
- **决定（Yi Xin）**：走 **(a)**——`tests/test_day9_evidence.py` 校验①引用路径
  全存在②关键数字与源 artifact（如 κ vs `eval/results/day8-kappa.json`）一致。
- **理由**：把 INV-5「可复跑」从一次性人工核对升级为**持续可执行**，Day10 重排
  目录不埋雷。Day 8 主动推翻过自己的 README 数字（0.917→0.979），证明数字漂移
  是真实风险——机器闸兜底比人记性可靠。**EVIDENCE.md 数字唯一源 = 当前 main 上的
  冻结 artifact**，不引历史 handoff 的过时值。

## D4（T5）要不要落一个根目录 AGENTS.md

- **问题**：DR §「agents.md 崛起」+ tutorial 12 §问题2 把 README/llms.txt/agents.md
  三分。本仓库 `CLAUDE.md` + `constitution.md` 已行 agents.md 之实。要真加文件吗？
- **决定（AI 起草、Yi Xin 未加=保守裁为 out-of-scope）**：**不加 AGENTS.md**。
  execution-plan §Day 9 未列它，加属超范围。改为在 `AI-COLLABORATION.md`/`llms.txt`
  里**说明 CLAUDE.md 扮演 agents.md 角色**——有其实，命其名，不重复造。
- **理由**：surgical / 不超 SPEC 范围（coding-guidelines §3、CLAUDE.md 实现纪律）。
  若 Yi Xin 要真落 AGENTS.md，属决策层显式追加。

## D5（T6）「陌生 agent 5 分钟核查」怎么验

- **问题**：execution-plan §Day 9 的「证」是陌生 agent 只读 llms.txt+EVIDENCE.md
  5 分钟定位任意数字复跑方式。用什么当「陌生 agent」、怎么测？
- **决定（Yi Xin 口述）**：用 **MiniMax**（`minimax` CLI 的 `minimax code`，或项目
  现有 MiniMax 配置）当陌生 agent，只喂 llms.txt+EVIDENCE.md，验它能否说出抽样数字
  的复跑命令，录为证据。
- **理由**：MiniMax 在 Day 8 是被评的生成器，但这里**只读文档、不自评**，无
  生成器-验证器共谋张力。用项目已有通道，零新依赖。
