# 04 · 选型说明：候选、决定、理由、出处

> **AI-drafted，待人审**。快照：2026-07-18（Day 1–10 全部合并，`v1.0.0`）。本文只汇总
> **已经做出**的选型决策；每条给出决策出处（spec / discussion / review 裁决）。
> 新决策不在这里做——在讨论里做、在这里登记。

## 1. 语言与工程基座（Day 1）

| 选型 | 候选 | 决定与理由 | 出处 |
| --- | --- | --- | --- |
| Python 3.12 | — | 目标岗位技术栈；StrEnum 等新特性直接可用 | [specs/day1](../specs/day1.md) |
| uv + hatchling | pip/poetry | 锁定安装最快路径；CI `--locked` 保证可复现（INV-5） | specs/day1 |
| ruff（lint+format 一体） | flake8+black | 单工具、快、pre-commit/CI 三处同一套规则 | specs/day1 |
| 依赖上界 + uv.lock | 仅下界 | **解析器行为不许在未锁定安装下漂移**——校验器的裁决结果依赖 lxml 行为稳定 | [reviews/day2 裁决 #13](../reviews/day2.md) |

## 2. XML 解析（Day 1–2）

| 选型 | 候选 | 决定与理由 | 出处 |
| --- | --- | --- | --- |
| defusedxml 前置安检 + 加固 lxml 双通道 | 只用 lxml / 只用 stdlib | defusedxml 挡实体炸弹（L0 门卫）；lxml 提供行号、XPath、XSD——findings 要精确到行/路径就离不开它；lxml 侧再关实体/DTD/网络 | [reviews/day1](../reviews/day1.md) 裁决、loader.py 模块注释 |
| Pydantic 规范模型 | dataclass / attrs | 项目基线要求（CLAUDE.md）；序列化/校验自带；Day 5 API 层直接复用 | [specs/day2](../specs/day2.md) |
| 声明式 BREX 规则表 | isoschematron 工具链 | 3–5 条规则不值得引入整个 Schematron 栈；规则=数据（id/severity/hint/检查函数），新增规则零框架成本 | specs/day2 Q5 |

## 3. 分块与检索（Day 3）

| 选型 | 候选 | 决定与理由 | 出处 |
| --- | --- | --- | --- |
| 结构感知分块（主力）+ 递归窗口（对照） | 一次做齐三种（含语义分块） | S1000D-like 文档自带切线（步骤/警告/引用）；语义分块需要 embedding，挪到 Day 4 消融，避免踩两日滑点规则（INV-8）。**语义分块已如期于 Day 4a 落地**（`semantic.py`，百分位断点），作第三对照策略 | [discussions/day3 D1](../discussions/day3.md) |
| rank-bm25（进程内） | Tantivy | 语料极小，服务化索引是过度工程；瓶颈在分词不在引擎 | specs/day3 Q1 |
| 自写保标识符分词器 | 库默认分析器 | 技术语料单点杠杆最高的修复：`DMC-…`/件号保持整 token，否则标识符查询被数字碎片淹没 | [教程 02 §1](../tutorials/02-information-retrieval.md)、bm25.py |
| 人工标注 golden set | LLM 标注 | 检索评估的判断力红线：相关性判断必须人做，AI 只许起草候选 | execution-plan Day 3、eval/golden/README |

## 4. 存储与外部服务（2026-07-14 Day 3 会议定，Day 4 落地）

| 选型 | 候选 | 决定与理由 | 出处 |
| --- | --- | --- | --- |
| **Vespa**（向量库） | Qdrant（AI 推荐、执行计划原默认）、pgvector/Chroma/FAISS（无 ColBERT 路径，出局） | **Yi Xin 否决 AI 的 Qdrant 推荐**：late-interaction（ColBERT 类 MaxSim）在 Vespa 是原生一等公民而非附加功能；运维重量已接受（docker 现成）。ColBERT 本身仍在切片外——选型只是不封死这条路 | [discussions/day3 D2](../discussions/day3.md) |
| **Neo4j**（图存储） | RDFLib（最小方案）、Kùzu（嵌入式） | 行业标准；docker 已在跑，"服务化太重"的反对不成立。注意：**存储已定，是否把最小图查询拉入切片仍待 Day 4 收口复评点** | discussions/day3 D3 |
| **MiniMax**（embedding） | BGE / E5 本地模型（执行计划原方案） | Yi Xin 指定；复用 FollowTheBig 的配置模式（含非标准 X-Proxy-Token 头）。**开口项**：参考实现无 embedding 端点，端点形状待验证 | discussions/day3 D8、[local-services.md](../local-services.md) |
| 图数据来源 = 确定性序列化 | NLP 实体/关系抽取 | L3 校验器已建引用图，DMC/适用性/警告都是结构化字段——"抽取"就是序列化规范模型，不需要 NLP | discussions/day3 D3 |

## 4.5 框架与模型选型（Day 4，2026-07-16 增补）

| 选型 | 候选 | 决定与理由 | 出处 |
| --- | --- | --- | --- |
| **LangChain = 系统默认技术栈** | 继续无框架手写 | Yi Xin 定向：**学习目标**（借项目掌握框架）+ 默认选型。落地原则"框架管管道原语、领域逻辑自留"；Day 1–2 无等价物不强套。先前 D11 的"不重构"结论只回答了"能否修 bug"，不适用于此动机 | [discussions/day4 D12/D13](../discussions/day4.md) |
| **Qwen3-Embedding-8B = 默认 dense 模型** | MiniMax embo-01（原默认）、BGE-M3 | **三行 bake-off 用数字定**：Qwen3-8B R@5 0.985 / R@10 1.000 / MRR 0.870，胜 BGE-M3（0.910/0.970/0.833）与 MiniMax（0.500——实测长度偏置会颠倒排序，已单独立档）。8B 而非 0.6B 是 Yi Xin 效果优先的裁决；M5 Max/64GB 无成本压力 | [notes/day4-dense-bakeoff.md](../notes/day4-dense-bakeoff.md)、[notes/day4-embedding-length-bias.md](../notes/day4-embedding-length-bias.md)、D14 |
| MiniMax 降级为对照行 | 移除 | 保留实现与长度偏置证据链——"我测出了供应商缺陷并换掉它"是完整故事；成本动机的原决策被测量推翻，诚实留痕 | D14 |
| BGE-M3 保留（Day 4b 供应者） | 移除 | 它的独特价值在 dense 之外：sparse 权重（SPLADE 判据）与 ColBERT 多向量（late-interaction 判据），Vespa 是唯一全支持三表征的引擎 | D12 |
| ⚠ 风险登记：langchain-community 日落 | — | BM25Retriever 所在包已弃用维护；领域层包装使迁移成本约半天，等独立包出现再迁 | D13 |

## 4.6 生成层选型（Day 5，v0.5.0）

| 选型 | 候选 | 决定与理由 | 出处 |
| --- | --- | --- | --- |
| **答案 LLM = MiniMax-M3 chat** | Claude API（原执行计划） | Yi Xin 裁决改用 M3;配置走既有 `MINIMAX_*`。注意边界:Day 4 移除的是 MiniMax *embedding*,不覆盖 chat/生成 | [specs/day5 决策2](../specs/day5.md) |
| **严格二分拒答**（带引用回答 xor 占位符） | 分级低置信带 | INV-4 洁净 + 缩小 Day 8 攻击面;深调研的 graceful-degradation 备选被否 | specs/day5 Q2 |
| **图集成 = 索引时同步 + 接口③注入** | 图邻居检索扩展 | DM 节点 + dmRef/ICN 边幂等 upsert;检索 DM 的图谱事实作结构化列表进 prompt;多跳于 Day 9 落地（§4.10）| [ADR-0002](../adr/0002-minimal-graph-query-slice.md)、specs/day5 Q1 |
| **拒答阈值 = 实测 artifact** | 手挑常数 | 从 golden 分数分布测出(INV-5),加载时校验有限且 ∈[0,1](红队 day5 #6) | specs/day5 |
| **答案固定英文** | 跟随问题语言 | 与对外产物一致;证据语料是英文合成 XML,避免跨语引用对齐噪声 | specs/day5 Q3 |

## 4.7 服务化与 Demo 选型（Day 6，v0.6.0）

| 选型 | 候选 | 决定与理由 | 出处 |
| --- | --- | --- | --- |
| **SSE 流式 + 事后召回**（exit c） | (a) 不流式 / (b) 只推进度事件 | Yi Xin 裁决:流式提升体验,**流本身可召回**——生成完无有效引用即回撤;INV-4 约束最终结果,流式文本显式标「未确证」 | [discussions/day6 D1](../discussions/day6.md) |
| **FastAPI + Streamlit 哑客户端** | 单体 Streamlit（含 AI 逻辑） | 前端零 AI 操作、只 HTTP;保证放结构里不放约定里——测试强制 UI 不 import learnarken | specs/day6 决策1/2 |
| **路由 `def` 而非 `async def`** | 全栈 async 重构 | 同步栈(urllib/ST/reranker)写进 async 会堵事件循环;`def` 自动进线程池是正解 | 扫描 §已知的未知2 |
| **每请求重验语料,不做 lifespan 缓存** | 启动加载一次缓存 | demo 语料小,正确性压过延迟;上传即刻可查、manifest 检查诚实;缓存化牵出 index epoch(#8) | specs/day6 |
| **CSRF = Origin/Referer 门** | demo token / 自定义头 | 无需改客户端/测试;server 端客户端无 Origin 头放行,浏览器跨源带外源头 403 | [reviews/day6 #4](../reviews/day6.md) |
| **上传事务化 = staging + 原子换入** | 直接写 active | active 在校验且索引都过前不动;重传失败保住旧的有效模块(红队 #1) | reviews/day6 #1 |

## 4.8 自愈修复 Agent 选型（Day 7，v0.7.0）

| 选型 | 候选 | 决定与理由 | 出处 |
| --- | --- | --- | --- |
| **ReAct 结构化 JSON 循环（自研）** | LangChain/LangGraph agent、原生 function-calling | 工具面/沙箱/熔断/人工闸是领域安全逻辑,通用框架的自由工具调用面反而扩大攻击面;M3 的 function-calling 非标准,结构化 JSON 契约更可控 | [specs/day7](../specs/day7.md)、[discussions/day7](../discussions/day7.md) |
| **受约束工具面（6 个）** | 自由字符串/正则替换工具 | ACI 防呆:`propose_patch` 是唯一写路径且绑定锚定节点,4 个扁平 `EditOp` 由 lxml 拼 DOM——消灭"忘闭合标签"类崩溃(神经符号分工) | specs/day7 |
| **信任来源 = 校验器确定性复跑** | LLM 自评修复成功 | 生成器-验证器不共谋;修没修好由 Day 2 校验器说了算 | specs/day7 决策 |
| **默认 dry-run + `--apply` 人工闸** | 自动写入 | 宪法 §1.3 绝不静默改数据;apply 时按 rule_id 重算风险 tier + TOCTOU 复检 + 原子写入/回滚 | specs/day7 |
| 沙箱 = 应用层围栏 | OS 级隔离（容器/gVisor） | 玩具层诚实标注（INV-7）:temp-dir jail + 白名单 + setrlimit 够本切片;真隔离在切片外 | specs/day7 |

## 4.9 对抗评估选型（Day 8，v0.8.0）

| 选型 | 候选 | 决定与理由 | 出处 |
| --- | --- | --- | --- |
| **异构双裁判 Codex + agy(Gemini)** | 单裁判、MiniMax 自评 | 生成器绝不当裁判（`FORBIDDEN_JUDGES`,同族 self-preference 共谋）;裁判是"异构+人工锚定的抽查放大器",不是信任来源 | [specs/day8](../specs/day8.md)、[reviews/day8](../reviews/day8.md) |
| **交集判定（两裁判皆过才算有据）** | 并集/多数决/人工兜底 | 严格口径作 headline,分歧行显式列出 | specs/day8 决策 C |
| **行为判分确定性、不用 LLM** | LLM 判全部维度 | 答/拒/澄清 + must_not_state 是可确定性检查的;LLM 只用在非判不可的有据性上 | specs/day8 决策 A |
| **Cohen's κ 人工锚定** | 直接信裁判 | Yi Xin 标 n=30,κ codex 0.737 / agy 0.667,0.60 软门双过;单类退化显式 κ=None(偏斜陷阱) | eval/results/day8-kappa.json |
| **裁判 stdout 冻结进 artifact** | 只存分数 | 活体 CLI 会漂移;冻结原始输出使数字可从 artifact 复现（INV-5,决策 D） | specs/day8 |

## 4.10 证据链与机器可读性选型（Day 9，v0.9.0）

| 选型 | 候选 | 决定与理由 | 出处 |
| --- | --- | --- | --- |
| **llms.txt + EVIDENCE.md 主张矩阵** | 只靠 README | 验收口径:陌生 AI agent（MiniMax）只读这两个文件,5 分钟内定位任一数字的复跑命令;守卫测试防死链/数字漂移 | [specs/day9](../specs/day9.md) |
| **EVIDENCE.md 只放抽象能力声明** | 简历数字入库 | INV-1:求职私档留 `resume-master/` 指回公共锚点,公共侧绝不外指（T1 裁决） | specs/day9 决策 1 |
| **graph impact = 独立 CLI 并联选项** | 并入答案管线 | 限深 `REFS*1..N` + 环去重(VIO-7 环免疫) + fail-closed;作 Graph-RAG 并联接口**不**扩主管线（T3 裁决,INV-8 防滑点） | specs/day9 决策 2、ADR-0002 |

## 4.11 部署选型（Day 10，v1.0.0）

| 选型 | 候选 | 决定与理由 | 出处 |
| --- | --- | --- | --- |
| **选型 D:按需真栈（停机 GCP VM）** | A 免费层简化切片（执行计划原案/DR 前提）、B 托管服务替换、C 纯录播 | Yi Xin 裁决推翻免费层前提:预期流量≈0,触发本身就是兴趣信号,按需付费恰好只在有人看时花钱;**部署物=基准物**,零 INV-5 口径漂移、零 INV-7"替换后端"脚注 | [specs/day10 决策 1](../specs/day10.md)、[discussions/day10 D1](../discussions/day10.md) |
| **GCP（us-central1）** | AWS | 同规格(8 vCPU/64 GB)约便宜 20%;本地 gcloud 已认证、配额/预算权限已核 | specs/day10 决策 2 |
| **token 状态页触发** | 常驻公网、手动邮件联系 | 每收件方一 token(点击可归因到公司);页面三态(closed/starting/running)任何状态都有下一步动作;点击+就绪各通知一封 | specs/day10 决策 3 |
| **费用围栏在 VM 内** | 只靠云端预算警报 | 看门狗不依赖外部服务存活;任何歧义朝关机解;demo_guard 补 MiniMax 花费盲区(GCP 账单看不见 LLM 调用) | specs/day10 决策 4、reviews/day10 |

## 5. 有意不做的（负选型）

| 不做 | 理由 | 重新评估点 |
| --- | --- | --- |
| SPLADE / ColBERT 实现 | 切片外（Planned）；Vespa 选型已保留 ColBERT 通路 | 切片完成后 |
| RDF/SPARQL 全量知识图谱 | 切片外；最小图查询 Day 5 拉入(ADR-0002)、**多跳依赖查询 Day 9 已落地**(`graph impact`);全量 KG 仍不做 | 切片完成后 |
| S1000D → 图数据库直接映射 | 业界做法（跳过文本分块），受限于 INV-1 无真实数据，本项目走传统 RAG 分块 | discussions/day3 D5 |
| 语义 groundedness（引用蕴含判定） | ~~切片外~~ → **Day 8 已落地**(异构双裁判,评估管线);**运行时门**仍只卡逐字子串必要条件 | 运行时蕴含判定:切片外 |
| index epoch / content-hash manifest | 语料小、每请求重验够用 | 缓存化或多写并发时（红队 #8） |
| Demo 公网化 | loopback 前提原判超范围;**Day 10 公网模式已加最小围栏**(门钥/LLM 配额/上传闸,demo_guard)。JWT/限流/多租户仍不做 | 真多租户部署时 |
| vLLM 本地 serving、Rust 扩展、GNN、形式化验证 | 切片外 Roadmap | 切片完成后 |

## 6. 决策模式备忘

十天下来的选型决策呈现一个稳定模式，后续变更时应沿用：

1. **人决策、AI 供选项**：Vespa 一案 AI 推荐 Qdrant 被否；Day 6 的 SSE×fail-closed
   三选项(不流式/进度事件/召回)也由 Yi Xin 裁——决策权在人，理由完整留痕；
2. **前瞻决策显式登记**：Day 4 才用的东西（Vespa/Neo4j/MiniMax）在 Day 3
   决定并写进 discussions + local-services，避免"到时候再说"造成的隐性返工；
3. **每个选型带否决候选**：没有被拒绝的候选就不算选型，只是默认；
4. **测量推翻直觉要留痕**：MiniMax 因实测长度偏置被换掉、拒答门在玩具规模弱,
   都诚实登记——"我测出缺陷并换掉/标注它"是比隐藏更强的故事;
5. **红队发现回填选型**：Day 6 的 CSRF 门、上传事务化,Day 10 的 demo_guard
   三闸,都是红队裁决的产物,决策出处指向 reviews/——评审不是走过场,是选型的
   一部分;
6. **继承的约束要先核实再优化**：Day 10 执行计划写的"免费层"被 Yi Xin 一句
   "付费 GCP 在手"推翻——差点在假前提里做次优选型。动手前显式列约束、问清
   真实资源（discussions/day10 D1）。
