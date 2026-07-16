# Day 4 未知点扫描与必会知识点深讲

> **AI-generated**（Claude，实现方助手），2026-07-15。学习流程 v2 第 1c 步（扫）。
> 方法：Anthropic《A Field Guide to Claude Fable: Finding Your Unknowns》的
> 未知象限法——把四类"未知"显式化。对照材料：
> [官方 Deep Research 报告](../gemini-deepresearch/day4-混合检索系统架构调研.md)
> （2026-07-15 由 Yi Xin 在 Gemini 客户端跑得；审阅勘误见其文件头与
> [REVIEW.md](../gemini-deepresearch/REVIEW.md)）、
> [教程 03](../tutorials/03-embeddings-and-vector-search.md)、
> [教程 04](../tutorials/04-advanced-retrieval.md)、Day 3 已有代码与讨论记录。
> 注：早先的 agy 模拟版报告（day4-report.md）已被官方报告取代；本文引用的
> "报告"均指官方版，与模拟版结论冲突处以官方版为准（见 §4.7）。

## 0. 方法：四个象限怎么用在今天

| 象限 | 含义 | 今天的处理 |
| --- | --- | --- |
| Known knowns | 已掌握、可直接用 | §1 清点，不再花时间 |
| Known unknowns | 知道自己不知道 | §2 变成 SPEC 必答题清单 |
| Unknown knowns | 以为自己懂、其实理解有偏 | §3 逐条纠偏（最危险的一类） |
| Unknown unknowns | 压根没想到的 | §4 调研报告扫出来的新信息 |

## 1. 已知区清点（Day 3 已经给你的，不用重学）

- **BM25 与保标识符分词**：`retrieval/bm25.py` 已实现，且您已通过 Day 3 基准表
  理解了它的价值——这正好是报告"坑 3"（标识符查询 dense 退化）的解药，我们已经持有。
- **评估体系**：Recall@k / MRR / nDCG、人工 golden set（32 题）、固定种子——报告
  §5.3 讲的指标惯例您已实操过一轮。
- **分块**：报告"建议四"（按 XML 结构切、别用固定长度）就是 Day 3 已做的
  structure-aware 分块——调研报告独立印证了 D1 决策。

## 2. Known unknowns：今天开工前必须消除的显式未知（= SPEC 必答题）

> **当日结算（2026-07-15 晚）**：#1（端点形状 + 不对称编码）和 #6（模型名与
> 维度）已由实测探针**解决**——native `{texts, type}` 形状、`embo-01`、1536 维、
> 向量已 L2 归一化、`type` 确认是不对称开关（同文本 db vs query 余弦 0.860）。
> #3（BM25 归属）、#4（重排器位置）、#5（语义分块）已由 Yi Xin 裁决。
> #2（Vespa schema 部署）仍是当天最大的新领域，但因 Q3/Q4 裁决而大幅简化。
> 全部结论见 [specs/day4.md](../specs/day4.md) 的 Probe findings 与
> Adjudicated decisions 两节。

1. **MiniMax embedding 端点形状**（[local-services.md](../local-services.md) 开口项）：
   OpenAI 兼容 `/embeddings` 还是原生 `texts + type: db/query`？
   ⚠ 官方报告已**证实机制**：`type="db"`（入库）vs `type="query"`（查询）就是
   MiniMax 的**不对称编码**开关——混用会造成 Recall 15–20% 量级的隐性折损
   （报告数字，方向性参考）。这不是可选参数，而是**写错就全盘检索退化**的
   开关。验证端点时必须实测两种 type 的向量确实不同。
2. **Vespa schema 怎么部署**：容器只起了 config server，应用包（schema +
   rank-profile）从未部署过。这是今天最大的新领域。
3. **BM25 归属**：搬进 Vespa（报告"建议二"的 first-phase 一体化路线）还是保留
   进程内 rank-bm25 只在 Python 层做 RRF？影响消融表口径与延迟数字的可比性。
4. **重排器**：Vespa global-phase 内嵌 ONNX（报告路线）vs Python 层跑
   bge-reranker（执行计划原路线）。前者优雅但多一层 ONNX 导出的新知识，
   小语料下收益存疑。
5. **语义分块**进不进消融表主表（Day 3 D1 遗留）。
6. **MiniMax embedding 模型名与向量维度**：官方报告给出 `embo-01`
   （1536 维、约 4096 token 输入上限），但其引用来源较弱（Grokipedia、
   第三方仓库）——维度数字直接决定 Vespa schema 里 `tensor<float>(x[1536])`
   的定义，**必须先调一次真实 API 确认模型名与维度再写 schema**。

## 3. Unknown knowns：容易"以为懂了"的四个纠偏

### 纠偏 1：向量检索不是"更好的搜索"，是"另一路召回"

传统程序员直觉：新技术取代旧技术（如 InnoDB 取代 MyISAM）。错。教程 04 §0 和
报告 §1 的共同结论：dense 和 BM25 是**互补的两路**，各有对方治不了的死角
（同义改写 vs 精确标识符）。今天做的不是升级，是**并联加一路，再学会合并**。
消融表存在的意义就是证明"并联 > 任何单路"。

### 纠偏 2：RRF 不是加权平均

直觉写法 `0.7*dense + 0.3*bm25` 是错的：BM25 分数无上界、cosine 在 0–1，
分数空间不可通约（类比：把"毫秒延迟"和"错误率"直接相加）。RRF 只用**排名**：
`score = Σ 1/(k+rank)`，k=60 是 2009 年论文的实证常数，**不要调它**
（教程 04 §4、报告"坑 4"一致）。面试一句话：RRF 用排名回避了跨系统分数
归一化这个无解问题。

### 纠偏 3：重排器不是"更好的 embedding"

双塔（bi-encoder）：query 和 doc **各自**编码，向量可预计算、可建索引，O(N) 可扩展；
交叉编码器（cross-encoder）：query+doc **拼在一起**过一遍 Transformer，精度高但
每对都要现算，**无法建索引**（教程 04 §1"什么时候让 query 和 document 见面"）。
所以它只能出现在管线末端对 Top-k 精排。类比：召回是 `WHERE` 索引扫描，
重排是拿到候选行后逐行跑昂贵的存储过程——你绝不会对全表跑存储过程。

### 纠偏 4：小语料下"延迟数字"的含义不同

报告"建议三"的延迟预算（200–300ms）是生产级语料的框架。我们的语料只有几百个
chunk：HNSW 与暴力扫描没有可测差别，p50 延迟主要由 **MiniMax API 网络往返**
主导。消融表的延迟列要如实解释这一点（INV-7 诚实分层），不许把玩具规模的
延迟当作架构结论。

## 4. Unknown unknowns：调研扫出的、教程未覆盖或强调不足的

1. **L2 归一化 → 内积等价**（报告"坑 1"）：向量入库前做 L2 归一化，cosine 就
   等价于内积，SIMD 快一倍。**落地点**：Vespa schema 的 `distance-metric`
   选择（`angular` vs `dotproduct` vs `prenormalized-angular`）必须与是否
   归一化一致——选错不是慢，是**错**。教程 03 未讲这一层。
2. **不对称编码**（报告"坑 2"）：见 §2.1，已并入端点验证项。这是本次扫描
   发现的**最高价值未知**——它把两个独立的开口项（端点形状、检索质量）连成
   了一个问题。
3. **Vespa 是搜索引擎而非纯向量库**（报告 §3.3）：BM25、HNSW、RRF、甚至
   ONNX 重排都能在引擎内完成（phased ranking）。这解释了 D2 选型时"运维重"
   的另一面——重是因为它把整条管线都吞了。今天至少要读懂 rank-profile 的
   first-phase/global-phase 概念，哪怕不全用。
4. **Matryoshka（MRL）套娃向量**（报告 §4）：新一代模型允许按内存预算截断
   维度。对今天不构成行动项，但面试高频新词，值得记住一句话解释。
5. **MTEB 榜单的欺骗性**（报告 §3.1）：垂直领域（航空/医疗）通用榜单参考价值
   有限——这恰好是"为什么要自己做消融实验"的行业级论据，可写进 README 消融
   表的动机段。
6. **DMC 独立字段 + 网关硬过滤**（官方报告）：与其把 DMC 拼进 chunk 文本
   （模拟版报告的建议，有污染 embedding 输入、扰动 Day 3 评估口径的副作用），
   官方报告给出更干净的方案——schema 里为 DMC 设独立 `string` 字段
   （`match: word/exact`），查询网关用正则识别"纯标识符查询"，识别到就在
   YQL 里附加精确匹配强约束（hard filter），先剪枝再向量检索。两案作为
   SPEC 选项让人裁决，我倾向后者。
7. **RRF 在 Vespa 里的正确位置（勘误）**：agy 模拟版报告曾建议在
   first-phase 写 `reciprocal_rank_fusion(...)`——**错误**。官方报告 +
   Vespa phased-ranking 文档：RRF 类归一化函数（`reciprocal_rank(feature, k)`）
   只在 **global-phase** 可用（需要跨分片的全局排名才有意义）。
   > **事后更新（当日晚，SPEC Q3/Q4 裁决后）**：此条对"引擎内融合"仍然成立，
   > 但**已不适用于本项目架构**——Yi Xin 裁定重排器放 Python、BM25 留进程内，
   > 因此 Vespa 只做稠密向量存储，RRF 是 Python 层融合两个排名表。
   > 连带好处：schema 塌缩成"一个 embedding 字段 + 过滤属性"，首次 Vespa
   > 部署的风险大幅下降。详见 [specs/day4.md](../specs/day4.md)。

## 5. 报告勘误与红线冲突（对照本项目宪法）

官方报告的完整勘误（5 条）已标注在
[报告文件头部](../gemini-deepresearch/day4-混合检索系统架构调研.md)，全套
10 份报告的审阅结论见 [REVIEW.md](../gemini-deepresearch/REVIEW.md)。
与宪法直接相关的两条在此重申：

| 报告内容 | 校正 |
| --- | --- |
| "用 MiniMax-M3 反向生成 1500 条 Query + 人工校验" | 方向合规（AI 起草、人判定）但规模是生产框架：本项目按 32 题人工 golden set 执行，不扩产（execution-plan Day 3、eval/golden/README）。 |
| 延迟预算 / Top-1000 召回 / Top-100 重排等数量级 | 生产语料假设；本项目数百 chunk 玩具规模，数字按比例缩放、原则不变，消融表如实标注（INV-7）。 |

## 6. 今天必须掌握的三个核心点（深讲版）

> 对应每日循环 1b 步"列出 3 个实现时要验证的概念"——以下是我的候选，
> 最终取舍在您。

### 核心 1：HNSW——向量世界的跳表

（教程 03 §3 + 报告 §3.2）多层图：顶层稀疏"高速公路"快速跨越大区域，逐层下沉到
底层稠密图做精细搜索。和跳表的完全同构：都是"上层稀疏索引加速、底层全量保真"。
两个参数值得在 Vespa schema 里认出来：`max-links-per-node`（图的连接密度，
内存 vs 召回）、`neighbors-to-explore-at-insert`（建图质量 vs 建图速度）。
**验证动作**：部署 schema 后用一条已知答案的查询对比 HNSW 结果与暴力扫描结果，
确认召回未损。

### 核心 2：RRF——用排名做民主投票

两路召回各交一张排名表，每个文档得分 = Σ 1/(60+它在各表的名次)。没进某路
前 k 名就在那路得 0。数学性质：名次差在头部放大（第 1 vs 第 10 差很多）、
尾部压缩（第 100 vs 第 110 几乎没差）——这正是"头部共识为王"的设计意图。
**验证动作**：手工构造两路各 3 个文档的迷你例子，手算 RRF 分数，再对程序输出。

### 核心 3：消融表的"阶段-指标"对应关系

四行表不是四个平行系统，是一条管线的四个开关组合。评估时指标各司其职：
召回阶段看 **Recall@10**（网里有没有鱼），重排阶段看 **nDCG@10 / MRR**
（鱼排没排在最上面）。预期形态（面试可讲）：dense 行在同义改写题上救回
BM25 的失分、在标识符题上丢分；hybrid 行两头兼顾；+rerank 行主要抬 nDCG/MRR
而非 Recall——**如果 rerank 抬了 Recall，说明实验设计有 bug**（重排不产生新候选）。
这条判断规则是红队攻击评估方法时的第一道自检。

## 7. 衔接实践

1. 您读完 [day4-report.md](day4-report.md) 与教程 03/04 后，从 §6（或自选）定下
   3 个"实现时要验证的概念"，写入 `docs/specs/day4.md` 决策层；
2. §2 的 6 个显式未知就是 SPEC 必答题清单，其中 1（端点+不对称编码）和
   6（向量维度）需要先对真实 API 各发一次验证请求；
3. 我在 SPEC 就绪前不动实现（CLAUDE.md 前置条件）。
