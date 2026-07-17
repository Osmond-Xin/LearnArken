# Day 5 未知点扫描 — 带引用的 RAG 问答

> **AI-generated**（Claude 实现方，2026-07-16，研→读→扫 第三步）。交叉引用：
> `docs/gemini-deepresearch/day5-RAG System Deep Research.md`（官方 DR 报告，
> 2026-07-15 生成）、tutorials/05-rag.md、tutorials/07-llm-fundamentals.md、
> tutorials/06 §9（图谱×RAG 接口）。按 Anthropic "Finding Your Unknowns"
> 四象限做盲区扫描。

## 象限扫描

### 已知的已知（今天要动手的）

- 结构化 Prompt 三区（系统指令 / 证据区 XML 隔离 / 引用格式契约）——报告 §3。
- Chunk-ID 标注式引用 + 应用层确证（citation ⊆ 检索集，二次反查）——我们的
  chunk_id 是确定性哈希，天然是引用主键；DMC/XPath 从 chunk 元数据回填，
  不让 LLM 复述（复述必漂移）。
- Answer trace 五跨度（trace_id / 检索 / 重排 / LLM payload / 生成+引用映射）
  ——教程 05 §5 称之为本项目招牌设计。
- 拒答双防线：重排分数阈值短路（不调 LLM）+ 结构化输出 `is_answerable`
  fail-closed（INV-4）。

### 已知的未知（动手前要定）

1. **MiniMax-M3 chat 端点的真实形状**。Day 4 的教训：embeddings 端点是
   MiniMax-native 而非 OpenAI 兼容，`type` 是真开关。chat 端点参考实现在
   FollowTheBig（OpenAI-ish + X-Proxy-Token），但**结构化输出/JSON mode 是否
   支持、如何触发，未经实测**——按 Day 4 Q1 先例：先小 demo 探测再实现。
2. **重排分数阈值定多少**。报告陷阱二：过松假阳性、过紧变摆设。必须用
   golden set 测量（answerable 的 top-1 分数分布 vs no-answer 的分数分布，
   找分离点），不许拍脑袋（INV-5 精神）。bge-reranker 输出是 logit，
   不是 [0,1] 概率——阈值要在同一标度上测。
3. **引用漂移的测量**：golden set 上 citation ⊆ 检索集是必要条件，但
   citation 是否指向"真正支撑答案的那个 chunk"需要 groundedness 抽查
   （计划里的人工 20 例，Yi Xin 做）。
4. **图谱同步的最小形状**：chunk 已带 dmRefs/ICN 钩子，Neo4j 空库在跑。
   同步粒度是 DM 级节点（DM→DM 引用边、DM→ICN 边）还是 chunk 级？
   查询时图谱事实以何种形式进 prompt（教程 06 §9 接口③：结构化列表）？

### 未知的已知（容易带错旧直觉的）

- "dense 模式 zero-hit 恒为 0" ⇒ **检索层没有天然拒答信号**，Day 3 的
  token-overlap 拒答直觉在这里失效——拒答信号必须来自重排分数或 LLM 判断，
  这正是 Day 4 结论"真拒答是 Day 5 答案层职责"的兑现。
- LLM 会为了迎合引用格式**捏造真实存在的 chunk_id**（报告陷阱一）——
  "格式合法"≠"引用正确"，确证机制不可省。
- 温度设 0 ≠ 确定性输出（服务端仍可能非确定）；测试不能假设逐字节可复现，
  要断言结构性质（引用集合、拒答布尔），不断言全文。

### 未知的未知（预埋观测点）

- 间接提示注入（报告陷阱三，OWASP LLM01）：我们的语料是自产合成 XML，
  今天风险低，但 chunk 文本进 prompt 的那一刻攻击面就存在——证据区用
  随机定界符包裹（Spotlighting）成本极低，先埋上；Day 8 对抗评估会攻这里。
- MiniMax 服务端行为漂移（Day 4 length-bias 的教训）：trace 落盘 payload
  与模型版本标识，异常时可归因"手册错/没召回/幻觉"三选一（报告 §3）。

## 必须吃透的点（面试级）

1. **引用为什么不能让 LLM 复述元数据**：chunk_id→(DMC, XPath) 的映射在
   系统侧是确定的，让模型只输出短 ID、应用层回填元数据，把"漂移面"压缩到
   一个短字符串的匹配上——这是 Chunk-ID 模式安全性的来源（报告 §3 引用模式）。
2. **fail-closed 的纵深**：阈值短路（不花钱、不暴露攻击面）→ 结构化
   is_answerable（模型自证）→ 引用确证（程序自证）。任何一层亮红灯都回
   占位符，绝不降级到模型内部知识（宪法 INV-4）。
3. **图谱与文本的分工**（教程 06 §9）：关系问题查图、内容问题查文本；
   图谱事实作为结构化上下文与文本证据互补（接口③），不是替代检索。
