> 来源：Gemini App Deep Research，日期 2026-07-19。
> 修订：2026-07-19 由 Claude 修订——(1) 图文冲突处理立场改为与本项目 fail-closed
> 纪律一致（报告冲突并拒答，不预设图为真理）；(2) "VLM 生态格局"节改写为家族
> 画像 + 选型判据（原文把已过时型号当作当前 SOTA，具体选型以动手时模型卡为准）；
> (3) 删除模板残留免责声明。其余内容未改。

# **多模态与文档智能深度调研：从纯文本 RAG 到视觉-语言多模态架构的演进与工程实践**

## **技术文档检索的范式危机与多模态转型的必然性**

在现代复杂装备制造与航空维修领域，技术文档的数字化与智能化检索已成为提升工程效率的核心基石。然而，传统基于纯文本的检索增强生成（RAG）系统在面对高度结构化的航空文档时，正暴露出严重的架构级盲区。以航空业广泛采用的 S1000D 标准为例，该规范通过公共源数据库（CSDB）严格分离了文本数据模块与图解信息控制码（ICN）1。在这一体系下，文本往往只承担引导与流程骨架的作用，而真正的核心组装逻辑、部件空间关系以及安全警告（Warning/Caution）等关键领域知识，往往以分解图、热点（Hotspot）编号标注的形式，被“封印”在可缩放矢量图形（SVG）或计算机图形元文件（CGM）中3。  
纯文本 RAG 系统的盲区在于，当工程人员查询“如何拆卸主起落架上的 4 号螺栓”时，文本语料库中可能仅仅存在“按照图 2（ICN-XXXX）拆卸件 4”这样缺乏视觉上下文的孤立引用。从传统软件工程的角度来看，这相当于数据库中存在一个外键，但引用的目标表却不可见。由于系统无法“看到”图纸，自然无法知道件 4 究竟是螺栓、垫圈还是液压阀门，更无从得知其物理位置与拆卸的拓扑顺序4。这种“信息只在图里”的普遍现象，使得纯文本检索在处理复杂装配、排故任务时形同虚设。  
为了打破这一数据孤岛瓶颈，引入视觉语言模型（VLM）与多模态架构，使技术插图（尤其是带有明确结构语义的 SVG 分解图）能够作为一等公民进入检索与问答管线，已成为 2025 年至 2026 年间文档智能领域的确定性路线。对于已经具备带有引用与拒答能力的 S1000D 文本 RAG 系统的架构师而言，核心挑战在于如何以高度工程化、可审计且成本可控的方式实现图文联合检索。在完全隔离真实图纸、仅接触自绘合成 SVG 的特定前提下，设计一条无缝对接现有倒排索引与大语言模型（LLM）的多模态数据管道，是完成架构转型的首要任务。

## **多模态检索的技术路线版图与演进**

在将视觉信息引入检索系统的工程实践中，目前业界存在三条主干技术路线。每一条路线都代表了不同的系统边界划分与算力成本妥协，可以将其与传统软件工程中的架构演进进行类比。

### **路线一：描述后索引（Describe-then-Index）**

描述后索引路线的核心思想是在文档入库（Ingestion）阶段，利用前沿视觉语言模型充当高级的数据提取与转换微服务，将图像中的隐式视觉信息“翻译”为结构化的文本描述，随后将这些文本描述连同图纸元数据一起送入传统的向量数据库中进行存储与索引。这非常类似于传统企业内容管理系统（CMS）中，将 PDF 或图像附件通过光学字符识别（OCR）批处理转换为纯文本后，再推送到 Elasticsearch 等全文检索引擎的做法。  
在 S1000D 场景下，入库管线会通过 VLM 对每张 SVG 插图的栅格化副本生成受严格数据模式（Schema）约束的 JSON 描述，这包含了穷举的部件清单、对应的热点编号以及隐含的物理干涉警告。查询时，系统依然在原有的纯文本向量空间中进行语义相似度匹配。其主要优势在于对现有 RAG 架构的侵入性极小，且查询期的计算负载极低，响应速度达到毫秒级5。由于只在入库时调用一次昂贵的 VLM，成本完全分摊在离线数据准备期，非常适合那些更新频率低但在线并发查询量巨大的静态手册库。然而，其根本理论缺陷在于“描述的边界即检索的边界”。如果 VLM 在入库解析时遗漏了某个隐蔽的垫片编号，那么在在线查询时，无论重排器（Reranker）多么先进，该信息都已在索引中彻底丢失，极易引发大模型的推理幻觉。

### **路线二：共空间多模态嵌入（Co-spatial Multimodal Embedding）**

此路线以 CLIP（Contrastive Language-Image Pre-Training）及其 2025 年进化版 SigLIP 2 家族为代表。其算法原理是将图像和文本通过双流编码器映射到同一个共享的高维特征向量空间中，使得语义匹配的图文在多维空间中余弦距离更近5。这在软件工程中可以类比为将结构迥异的复杂对象计算出一个统一长度的哈希指纹，只需对比指纹相似度即可实现跨模态检索。  
尽管该路线在消费级自然图像与简短描述匹配上取得了革命性成功，但在面对航空手册中密集的线框技术图（Wireframe/Line art）时，却遭遇了严重的表征退化问题。由于 CLIP 类模型在神经网络末端倾向于使用全局池化层（Global Pooling），将整张图像的局部特征压缩为一个单一的密集向量（如 768 或 1024 维），这种极度的信息降维对于包含数十个细小编号、密集引线与复杂几何拓扑的 S1000D 分解图而言是毁灭性的4。原本精确的空间细节、结构层级和热点坐标在全局压缩过程中被完全抹平。即使最新的 SigLIP 2 引入了原生宽高比支持，其在细粒度技术图纸检索上的表现，依然难以支撑工业级的精确零容错匹配5。

### **路线三：视觉文档检索与延迟交互（Visual Document Retrieval & Late-Interaction）**

为了彻底克服全局池化带来的信息丢失灾难，以 ColPali 和 ColQwen 为代表的延迟交互（Late-Interaction）路线在 2024 年底至 2026 年初异军突起，并牢牢统治了包含 ViDoRe V3 在内的各大视觉文档检索基准测试榜单10。该路线彻底抛弃了繁琐且极易出错的文档布局分析与 OCR 解析管线，将整个文档页面甚至纯粹的技术图纸直接作为单一视觉信号输入。  
在底层机制上，延迟交互模型将高分辨率图像分割为均匀的微小图块（Patch），并通过先进的视觉编码器（如 Qwen2-VL 或 PaliGemma）将每个图块转化为独立的上下文感知嵌入向量。与 CLIP 压缩为单向量不同，ColPali 架构为每个文档页面保留了一个包含数百至上千个局部向量的多维矩阵表征（Multi-vector Representation）12。在用户发起查询时，文本问题同样被编码为 Token 级别的向量序列。随后，系统在检索引擎层面执行最大相似度操作（MaxSim Operator），计算查询序列中每个词向量与图像所有图块向量的最大相似度，并将这些峰值累加作为相关性终分12。这类似于在分布式数据库中避免过早的数据聚合，而是保留所有底层数据分片，在查询时再进行细粒度的分布式 Join 匹配。这种机制最大程度地保留了细微的图文空间对应关系，使得诸如“左侧第三个带有虚线标识的法兰盘”这样的复杂空间指令能够被精准检索。

| 评估维度 | Describe-then-Index (VLM 描述入文本索引) | Co-spatial (CLIP/SigLIP 共享空间) | Late-Interaction (ColPali/ColQwen 延迟交互) |
| :---- | :---- | :---- | :---- |
| **底层核心机制** | VLM 充当 ETL 提取器转纯文本，基于文本向量与 BM25 检索 | 双流深度编码器，图像与文本强制对齐到同一稠密向量空间 | 图像保留图块级多向量矩阵表征，基于 MaxSim 算子进行延迟匹配 |
| **计算与成本分账** | 入库期计算量极高（VLM 推理），查询期成本极低 | 入库与查询期计算量均适中（仅需一次单向量映射计算） | 入库期成本较高，查询期算力消耗极高（需计算巨大的多向量相似度矩阵） |
| **存储容量开销** | 极低（仅需存储生成的结构化 JSON 对应的单个文本特征向量） | 低（单向量存储，通常为 512 至 1024 维度的浮点数组） | 极高（每页或每图需存储多达上千个高维图块向量，对向量数据库内存要求苛刻） |
| **对密集线框图表现** | 强（高度依赖于 Schema 设计的完备性与 VLM 的深度解析能力） | 弱（全局池化导致表征严重退化，细小编号与连线细节完全丢失） | 极强（原生保留空间语义拓扑，在 2026 年 ViDoRe 榜单上占据绝对 SOTA 地位） |
| **引用机制与可审计性** | 极高（系统可直接引用明确的图 ID 与离散的热点字段，溯源链条清晰） | 极低（模型匹配过程为纯粹的黑盒，无法解释具体依据） | 较高（可通过比对图块相似度生成视觉热力图，逆推模型的焦点区域，但不如结构化数据直接） |
| **2026 适用场景建议** | **已有成熟文本 RAG、需重组图纸结构化元数据、且严格控制在线查询成本的必选架构** | 消费级自然图片海量搜索、宏观图像草图分类与聚类 | **包含复杂排版、大量嵌套图表且预算充足，希望彻底免除 OCR 预处理的新一代企业级系统** |

对于正在转型 AI 工程且已拥有稳定 S1000D 文本 RAG 管线的系统架构师而言，面临的图纸均为不含物理噪点的自绘合成 SVG。在这种约束条件下，强行引入存储与查询成本双高的 Late-Interaction 架构无疑是过度设计。相反，采用 **Describe-then-Index** 路线将是工程上最稳健、向下兼容性最好、且对现有代码侵入性最小的演进路径。它能最大化利用现有系统的拒绝域控制与引用机制，仅将多模态能力作为数据摄取层面的一个强大插件。

## **核心技术详解：视觉特征的结构化提取与硬绑定**

在确立 Describe-then-Index 管线后，如何确保 VLM 生成的描述不仅内容详实，而且格式严格规范、杜绝逻辑幻觉，是决定整个系统检索召回率与下游大模型问答准确率的生死红线。

### **VLM 的图像 Token 化机制与上下文成本核算**

在使用前沿 VLM 对自绘 SVG 图像进行特征提取时，首先需要深入理解不同大模型的视觉 Token 化机制。尽管 SVG 本质上是基于 XML 的标记语言，直接将代码输入大语言模型似乎是最直接的方案，但由于复杂机械图纸包含数以万计的贝塞尔曲线节点和嵌套变换矩阵，纯代码输入往往会导致大模型丧失空间感知能力并迅速耗尽上下文窗口15。因此，业界普遍的做法是将 SVG 经由无头浏览器（Headless Browser）或高保真渲染引擎栅格化（Rasterization）为指定分辨率的无损 PNG 图像，随后再输入视觉语言模型15。  
不同 VLM 在处理栅格化图像时的计费与编码机制存在显著差异。以 OpenAI 的 GPT-4o 系列为例，其采用基于预设网格的高分辨率切片（Tiling）机制。当输入一张高分辨率分解图时，模型首先提取一个包含 85 个 Token 的低分辨率全局缩略图以建立宏观语境；随后，将原始图像切分为若干个 512x512 像素的固定网格，每个网格固定消耗 170 个 Token18。这意味着一张 1024x1024 像素的工程图纸，将被切分为 4 个区块，总成本固定为 85 \+ (4 \* 170\) \= 765 个 Token19。  
相比之下，Qwen2.5-VL（2025 年发布，后续型号沿用并强化同一机制）采用了截然不同的原生动态分辨率（Naive Dynamic Resolution）机制21。它彻底摒弃了死板的 512x512 网格切割，转而将输入图像的空间尺寸智能调整为 28 像素的整数倍，并以 14x14 像素作为基础图块（Patch）进行特征编码。结合多模态旋转位置编码（MRoPE），该机制允许模型原生感知极其细长的拓扑图或极其宽广的系统连接图，不仅消除了图像强行缩放带来的特征形变，更将长序列的计算复杂度大幅降低23。在实际工程落地中，架构师必须针对自身 SVG 库的平均分辨率和长宽比分布，精准建立 Token 消耗的数学预估模型，防止因未加节制的高分辨率渲染导致入库算力预算瞬间失控。

### **结构化 Captioning 与封闭候选词表压制幻觉**

传统的 VLM 图像理解输出往往是一段充满文采却松散自由的自然语言文本，这种非结构化的“散文”在要求精准定位的航空文档检索中是灾难性的。为了彻底抑制 VLM 在识别图纸编号、指示箭头和装配连线时产生的幻觉，必须引入基于 JSON Schema 严格约束的结构化输出（Structured Outputs）技术25。  
自 2024 年 8 月起，主流模型供应商（如 OpenAI 和部分开源框架）推出了在 API 层面原生支持 strict: true 的 JSON Schema 强制执行模式。这一技术的本质是在模型自回归解码（Autoregressive Decoding）过程中，动态掩码（Mask）那些不符合 Schema 语法树的 Logits 概率，从而从数学底层保证输出 100% 契合预设的数据契约27。在 S1000D 分解图解析场景下，可以通过 Pydantic 定义极其严密的嵌套 Schema：

JSON  
{  
  "icn\_id": "ICN-GE90-12345-001",  
  "illustration\_type": "exploded\_view",  
  "components": \[  
    {  
      "hotspot\_id": "4",   
      "part\_nomenclature": "主起落架固定螺栓",   
      "spatial\_relation": "位于液压支架左下侧，紧邻件3",   
      "associated\_warnings": "拆卸前需完全释放回路液压"  
    }  
  \]  
}

通过大量运用封闭候选词表（Enum），例如将 illustration\_type 严格限制在 \["exploded\_view", "schematic\_diagram", "wiring\_diagram"\] 的枚举子集中，可以剥夺 VLM 自由发挥的空间，从根本上压制其发散性幻觉。将这种强类型的结构化解析结果转化为纯文本描述后送入倒排索引，其信息密度和检索信噪比将远超未经约束的自由文本描述。

### **描述与图文件 Checksum 绑定防漂移**

在频繁迭代的系统维护与服役周期中，技术插图（ICN）会经历多次修订。如果 RAG 系统底层的文本索引库中依然残留着旧版插图的 JSON 描述，就会产生严重的“描述漂移”（Description Drift），导致大模型根据过期图纸指导维修操作。  
在软件架构设计上，必须将 SVG 原文件的内容校验和（Checksum，通常采用 SHA-256）与生成的 JSON 描述进行硬绑定。在入库（Indexing）流水线中，生成的结构化对象必须包含一个只读属性，记录生成该描述时 SVG 的 SHA-256 哈希值。利用类似于缓存失效（Cache Invalidation）的机制，一旦 CSDB 系统感知到某张图纸的二进制流或元数据发生变更，系统会迅速重新计算哈希值，对比倒排索引中的元数据标记脏数据（Dirty Flag），并异步触发 VLM 执行重新生成任务。这确保了检索系统中的图像描述与实际存储系统中的图像本体实现最终一致性。

### **图引用的可审计设计与 Fail-Closed 拒答**

企业级智能问答系统必须具备极强的可审计性（Auditability）。在基于结构化描述生成最终用户答案的阶段，RAG 系统的生成 Prompt 应严格要求 LLM 采用特定的标识符模式进行出处引用。例如，生成的标准回答应格式化为：“操作人员需使用专用扭矩扳手移除主固定螺栓（\[引用: ICN-GE90-12345-001, hotspot 4\]）”。前端用户界面在接收到带有标准标记的回答流时，能够实时解析这些引用块。借助 S1000D 原始 SVG 中自带的 viewBox 缩放属性以及内部 XML 节点的几何坐标信息，前端框架可以通过 JavaScript 操作 DOM，动态将对应的 SVG 局部区域进行高亮显示或镜头平移，实现真正的“图文并茂”且可双向追溯3。  
此外，系统必须建立认知边界。在 Describe-then-Index 管线中，查询期检索到的仅仅是离线生成的文本描述。如果用户提出的刁钻问题（例如“图中螺栓表面的防锈涂层是否出现龟裂？”）超出了 JSON Schema 所能捕获的结构化信息域，系统设计应果断采用 Fail-closed（默认拒绝）策略。在组装上下文提示词时，必须注入不容妥协的系统指令：“如果检索到的图解描述 JSON 中未直接包含问题所需的具体属性，必须立即输出内部代码 \[OUT\_OF\_SCOPE\]，严禁依赖模型预训练参数进行常识性猜测”。一旦系统捕获到该代码，便会向用户抛出标准拒答话术，这对于容错率极低的航空工程而言是不可逾越的安全红线。

## **多模态编排：成本分账与双模查询的权衡艺术**

在构建企业级多模态 RAG 架构时，多模态编排（Multi-modal Orchestration）本质上是针对计算资源、API 调用成本与响应延迟在时间与空间维度上的精细化统筹调配。其核心矛盾在于：高质量的前沿图像理解极其昂贵且推理缓慢，如何在确保极端工程问题回答精度的前提下，不让日常查询击穿预算护栏。

### **成本分账：入库期重活 vs 查询期轻载**

对于 S1000D 技术手册这类知识资产，其读写比例（Read/Write Ratio）极度倾斜，数以万计的并发查询次数远远大于是年计的手册修订次数。因此，将多模态处理的重负荷（Heavy-lifting）强制前置到离线入库期，是极为明智的成本分账策略。  
通过在数据摄取（Ingestion）流水线中调用昂贵但逻辑缜密的当期旗舰 VLM 进行一次性的深度结构化解析，将提取的高质量特征持久化为轻量级的文本索引。这种“重写轻读”的设计使得每次终端用户的在线查询，仅需消耗极少量的纯文本 LLM Token 成本进行语义相似度匹配和文本融合生成。此举不仅将在线并发查询的延迟从几秒压缩到了数百毫秒，更将不可控的多模态 API 调用成本严格隔离在了离线的数据管道层，由运维预算统一把控。

### **触发“二次看图”的 Agentic Fallback 机制**

尽管入库期的结构化描述能够完美覆盖超过 90% 的标准维修查阅任务，但在复杂的工程排故场景下，总有长尾复杂问题是扁平化 JSON 描述无法呈现的。例如，工程师可能会问：“从这三张分解图的组装关系来看，如果液压支架发生形变，图 2 中件 4 与图 3 中件 7 是否存在物理干涉的可能？”这种涉及跨图空间拓扑重构的问题，如果仅依赖离线提取的清单描述，必然导致回答失真。  
为了解决这一痛点，多模态编排引擎需要引入动态触发“二次看图”的代理路由（Agentic Routing）逻辑。当在线生成的终端 LLM 试图基于结构化文本描述生成答案时，如果其内置逻辑判定当前信息无法支持完整推理（触发了前文所述的 Fail-closed 状态），或者检索引擎返回的最相关图纸得分处于置信度边缘的模糊阈值，编排器将瞬间挂起当前的纯文本生成链路。系统会根据检索命中的图表 ID，通过对象存储接口实时拉取原始图纸的高分辨率 PNG 副本，连同用户的具体提问，再次构建一次全新的在线 VLM 调用请求进行针对性的“复核”（Re-evaluation）。这一机制确保了昂贵的高精度在线 VLM 推理算力仅被好刃用在最复杂的刀刃上。

### **预算护栏（Budget Guardrails）的构建**

“二次看图”机制虽然赋予了系统突破文本桎梏的强大能力，但如果不加限制，极易被恶意攻击或深层逻辑死循环导致 API 账单击穿。因此，编排器必须设置极其严苛的预算护栏：

1. **并发限次与熔断（Rate Limiting & Circuit Breaking）**：在系统配置层面，强制规定单次用户会话或针对单个复杂 Query 触发二次看图的深度不得超过设定阈值（例如单次请求最多允许在线解析 2 张图纸）。一旦触达阈值，编排器立刻熔断，返回能力受限提示。  
2. **动态分辨率降级（Resolution Down-scaling）**：在拉取原始图像准备在线送入 VLM 前，系统应根据问题类型进行智能降采样。如果不涉及细微编号的读取，仅需判断宏观的部件排布，系统将强制裁剪图像尺寸，限制最大切片（Tile）分配数量，或者直接切换至低细节模式（如 OpenAI 的 detail: low，固定消耗极少 Token）获取粗粒度判定30。  
3. **调用链追踪与可观测性（Traceability）**：在微服务网格中，每一次在线的多模态 API 调用必须附带唯一的请求溯源 ID，并详细记录在日志追踪系统（如 LangSmith 或自研监控看板）中。通过监控这些指标，数据团队可以离线分析哪些类别的图纸最常触发二次看图，从而在下一周期的离线提取时针对性地扩充 Schema 字段，持续优化系统效率。

### **主流 VLM 在文档理解上的生态格局（家族画像与选型判据）**

各大闭源巨头与开源社区在视觉文档智能领域已形成分层生态。VLM 具体型号迭代极快，此处只给各家族的**分工画像与选型判据**，具体型号与能力以动手时的模型卡和自测为准：

* **OpenAI GPT 系**：结构化输出（JSON Schema strict 模式）与零容错指令遵循的成熟度高，适合作为入库期数据清洗、结构化提取的兜底基座25。  
* **Anthropic Claude 系**：复杂嵌套图表推理、信息密集工业图纸分析和多步视觉逻辑关联能力强，适合挂载在“二次看图”路由器上，专门处理疑难杂症。  
* **Qwen-VL 系**：开源阵营主力，其原生动态分辨率（Native Dynamic Resolution）与 MRoPE 设计，使其在处理极端长宽比图纸、保留细微坐标点定位能力上表现突出22。具备私有化集群部署能力时，是海量历史手册离线入库特征提取的性价比选项21。  
* **Gemini 系**：标志性的超长原生多模态上下文窗口（百万级 Token 图文交错流输入），适合需要同时跨越数十张连续系统级图纸的跨页推理任务。

选型判据按优先级排序：结构化输出的严格性 > 密集小字/编号的读取精度（用自建 10 图小测集实测，不看榜单）> 上下文窗口 > 单位图像 token 成本。

## **评估方法：从精准度测试到无损回归**

在任何新型架构进入生产环境前，建立一套严谨、可量化的自动化评估体系（Eval）是保障迭代安全的灯塔。针对多模态 RAG 系统的测评不能停留在常规的召回率统计，必须深耕领域特性。

### **看图问题黄金数据集（Golden Set）的设计陷阱**

针对 S1000D 航空插图的视觉语义特点，测试数据集的构建必须由业务专家精心构造，重点覆盖三大类极具针对性的题型：

1. **纯视觉依赖题（Image-Only）**：“请问连接起落架主轴件 A 与底座件 B 的中间过渡卡扣的编号是多少？”此类测试旨在验证离线入库期 VLM 对空间从属关系与密集编号的特征提取与序列化能力。  
2. **纯文本基线题（Text-Only）**：“操作件 A 进行拆卸时需要设定的初始扭矩参数是多少？”此类测试用于校验引入多模态索引后，传统的文本倒排检索能力是否受到干扰或发生退化。  
3. **图文冲突陷阱题（Conflict Traps）**：这是压力测试的核心。在人为构造的沙盒样本当中，图纸上的标注明确指出件 4 是一枚“安全减压阀”，但在文档正文里故意掺入噪声文本，错误地将件 4 描述为“废气排放管”。此时向系统提问“件 4 的确切工程名称及安装位置”。这一测试考察系统能否正确甄别矛盾：在受控出版物体系中，图文冲突本身就是一处数据缺陷（校验 finding），正确行为是**报告冲突并拒绝择一作答**（fail-closed），而不是预设图或文任何一方为最终真理——冲突的裁决权属于人，不属于生成模型。

### **图像引用正确率与无损回归检查**

在指标设计的考量上，除了利用强大的 LLM 裁判（LLM-as-a-Judge）来综合打分答案的相关性、完整性之外，系统独有的“图引用正确率”必须作为一票否决的硬指标单独核算。回答内容完全正确，但给出的引用链却指向了错误的图 ID 或虚构的热点编号，在航空维修等高危场景中等同于严重事故诱因。系统测评脚本可采用严密的精确匹配（Exact Match）或正则表达式提取，强制比对答案尾部 \[引用: ICN-XXX, hotspot Y\] 的真伪性。  
更为关键的是针对老业务系统的无损回归检查（Regression Check）。由于新的管线向传统的 Elasticsearch 或 Qdrant 数据库中大量注入了 VLM 提取的详细图像描述文本，这在数学上极易稀释原有纯文本知识条目的向量密度与相对距离。因此，在每次算法发布的前置验证流中，必须利用旧版只针对纯文本设计的黄金测试集运行新版系统。如果发现原本能够轻易排在 Top-3 的知识点在引入图表描述后反而掉出了检索窗口，则证明切分器（Chunker）尺寸或重排打分器的路由策略出现了严重的干扰，版本发布必须熔断。

## **失败模式与防御策略（检测与修复机制）**

在真实的严苛工程环境中，Describe-then-Index 管线必然会暴露出若干深层的失败模式。成熟的架构师必须像布置异常捕获机制一样，提前布设全景监控雷达，并为每一种失败模式准备针对性的修复方案。

### **1\. VLM 细节幻觉（编号篡改/指示箭头误判）**

**表现现象**：在处理密集的爆炸分解图时，VLM 可能会将用于指示关系的细长“引线”误认为某个细长管类部件的本体，或者在分辨率压缩导致失真的情况下，将模糊的微小编号“8”生硬地识别为字母“B”或数字“3”。 **检测手段**：在离线入库的自动化校验流中，引入多模型交叉验证（Cross-validation）。对于标注为关键安全级别（Safety Critical）的核心设备图纸，并行调用 Qwen2.5-VL 与 GPT-4o 独立进行解析。如果两个模型提取的热点列表在 ID 或关联关系上产生差异，则触发告警并挂起入库流程交由人工复核。 **修复法则**：充分利用 SVG 文件的矢量结构优势。在进入渲染流水线前，通过 Python 的 XML 解析库（如 lxml）直接剥离出 SVG 内部所有的原生文本节点（\<text\> 标签）及其坐标。将这个通过解析代码得出的、绝对正确的文本集合作为“硬编码对照表”（Anchor Check）。在 VLM 输出 JSON 后，将生成的热点编号强制与对照表进行交集比对，任何不在硬编码列表中的编号均视为模型幻觉，并执行强制覆写过滤，从而用确定性的代码逻辑兜底概率性的深度学习输出16。

### **2\. 系统间描述漂移（Description Drift）**

**表现现象**：技术图纸在源系统（CSDB）中经历了版本更迭（例如修正了某个螺母的装配位置），但由于更新未同步，RAG 系统的倒排索引检索出的依然是旧版本图纸的结构描述，导致严重的信息错位。  
**检测手段**：在在线查询引擎组装下发结果时，拦截比对检索命中的图解 CSDB 唯一全局标识符、版本号（Issue Number）以及文件体的 SHA-256 哈希值。  
**修复法则**：抛弃落后的定时批处理更新，全面实施严格的事件驱动架构（Event-Driven Architecture）。CSDB 中任何针对图纸的增删改操作，必须通过高可用消息队列（如 Kafka 甚至 Webhook）实时广播事件。RAG 系统的消费者在接收到事件后，立刻在向量数据库中对旧版描述打上“墓碑标记”（Tombstone）以阻断在线召回，并调度后台 Worker 异步重新发起针对新版图纸的特征提取任务，确保数据的最终强一致性。

### **3\. 图像 Chunk 挤占正文召回（Vector Space Crowding）**

**表现现象**：由于一张异常复杂的系统拓扑图可能被 VLM 转化为包含上千字的冗长 JSON 结构描述，在进入向量编码器后，这种高维度的超大 Chunk 包含了海量的行业通用术语（如“垫圈”、“法兰”、“固定件”）。当用户进行常规搜索时，这种图表描述由于高频词汇的堆砌，极其容易在余弦相似度计算中霸占前五名的召回席位，进而导致真正包含“装配标准与具体扭矩物理参数”的核心文本段落被无情地挤出有限的 LLM 上下文窗口35。 **检测手段**：在网关层通过 Prometheus 或类似指标系统，统计分析历史长尾 Query 召回集中图表 Chunk（Image\_Desc\_Chunks）与文本 Chunk（Text\_Chunks）的数量分布比例。如果发现特定查询下图像描述占比异常偏高，则说明触发了空间挤占。 **修复法则**：强烈建议放弃在同一个单一扁平索引中进行粗放式混合搜索。应当采用多路召回隔离策略，利用命名空间（Namespace）或元数据预过滤（Pre-filtering）强制划定图像结果的最大允许召回数量。更优雅的解法是引入“父子节点切块策略（Parent-Child Chunking）”：在生成向量索引时，仅将高度精炼的图纸概述（如“起落架全景组装分解图”）作为用于语义匹配的子 Chunk；一旦被用户查询命中，检索模块顺藤摸瓜返回未参与检索的完整冗长 JSON 详情以及周围相邻的正文段落，从而完美平衡检索精准度与上下文的丰富性35。

### **4\. 冲突陷阱题的全面失守**

**表现现象**：当系统遭到用户刻意刁难，询问图中根本不存在的奇异部件，或者提出明显违背基础物理常理的组装关系设定时，即使有结构化的描述支撑，底层负责最后生成的文本 LLM 依然会强行拼凑看似合理的“幻觉”进行迎合。  
**检测手段**：将反事实提问（Counter-factual Queries，例如问“图中最左侧的隐形推进器怎么拆”）作为 CI/CD 自动化集成测试的一部分，利用专门微调的小参数量大模型担任裁判，全天候对系统进行自动化压力测试。  
**修复法则**：在构建组装 Prompt 时必须极其严厉，强化所谓的“不迎合条款”。采用高优先级系统指令（System Message）：“你的唯一认知基于提供的 JSON 描述，如果描述字典中无法映射用户提问的关键实体，你必须立即熔断输出，返回特定拒绝代码”。同时，在执行在线查询生成时，将文本 LLM 的温度参数（Temperature）强制压低至 0.0，彻底消除由多项式采样带来的大模型发散随机性。

## **架构演进必须掌握的技巧与常见坑（Pitfalls）**

对于刚从传统软件开发转型进入 AI 领域的工程师，极易将传统的批处理思维生搬硬套到大模型开发中。以下列举在搭建多模态 RAG 系统时最容易栽跟头的 5 个深坑及破局技巧：

### **陷阱一：批量多图串图导致上下文污染（Context Contamination）**

由于网络请求具有开销，传统程序员往往倾向于合并请求。将一篇文档中的 5 张图纸拼成一张超长图，或者在单次 API 负载中同时传入数十张图让 VLM 一并提取，这在多模态理解中是致命的。由于大模型缺乏对独立图像边界的刚性物理隔离能力，极易发生注意力漂移（Attention Drift），最终张冠李戴，将图 1 的阀门编号错误映射给图 2 的部件。  
**破局技巧**：必须遵循绝对的单实例会话原则。在数据管道中，严格以单个 ICN 为绝对粒度，在独立无状态的并行进程中发起 VLM 请求，并在生成的 JSON 对象中硬编码溯源图 ID，确保数据隔离的绝对纯洁性。

### **陷阱二：渲染分辨率与 API 账单失控**

SVG 是无限缩放的矢量格式，传统开发者可能会追求极致清晰度，直接将图纸光栅化渲染为 4K 甚至 8K 级别的巨型图像流转给 VLM。由于目前按切片（Tile）或图块面积计费的模型收费逻辑，这会导致单图解析耗费数千 Token，在处理包含几十万张历史图纸的 CSDB 时，极易引发几十万美金的账单灾难19。 **破局技巧**：必须前置建立具有数学反馈的自适应图像重采样流水线（Adaptive Down-scaling）。在保证图像中最小标注清晰可辨的底线前提下（可通过前文提及的 XML 文本提取来辅助确认最小字号），算法需预先计算图像的长宽比。在送入 VLM 前，强制将最大图像尺寸裁剪并限制在模型支持的最优效率视窗内（例如强制锁定短边为 768 像素）。针对缺乏密集信息点的宏观示意图，强制降配触发 detail: low 模式，将视觉消耗锁死在固定的极低成本范围内30。

### **陷阱三：空间层级关系被拍平（Hierarchy Loss）**

在要求 VLM 生成描述时，仅简单指定要求“输出所有见到的零部件名称”。结果 VLM 吐出一个长达百项、杂乱无章的平铺字符串数组，彻底遗失了分解图最核心的“父总成包含子零件”嵌套从属关系，使得这部分数据无法支持任何有深度的工程逻辑推理。  
**破局技巧**：在构建 JSON Schema 设计时，必须强制要求 VLM 输出带有向无环图特征的树状结构（Tree-structure）。例如，利用预定义的 parent\_assembly\_id 或 sub\_components 等字段数组，通过强类型的接口约定，逼迫模型在特征提取阶段完成层级逻辑的构建与序列化。

### **陷阱四：盲目崇拜像素，忽略原生结构化富矿**

将所有的自绘 SVG 图纸等同于用手机拍摄的自然界 JPEG 图片，把所有信息一视同仁全部当作像素特征交由纯视觉网络处理，完全放弃了 SVG 文件作为纯文本标记语言本身蕴含的确定性数据。 **破局技巧**：在输入 VLM 进行代价高昂的视觉推理前，先利用成熟的静态解析库遍历一次 SVG 的文档对象模型（DOM）。提取其控制视图的 viewBox 缩放矩阵参数，以及所有包含特定业务前缀（如 S1000D 规范中定义的 apsname 热点标识符）的有效节点3。将这部分通过代码剥离出来的“100% 绝对真理”，作为上下文的先验锚点（Prior Anchors）注入给大模型的 Prompt，指示其“务必基于此给定列表进行视觉拓扑属性的补全”。这种做法不仅极大降低了模型的发散难度，更能彻底消除基础实体的幻觉识别风险。

### **陷阱五：重排器（Reranker）的视觉语义盲点**

将 VLM 生成的文本描述与普通文档一同送入 BGE 或 Cohere 等传统通用文本重排模型进行最后的打分排序。结果发现，这类重排器在涉及二维空间物理方位的自然语言查询（如“位于主轴最左侧连接处下方的螺母型号”）上完全不知所措，频频给出灾难性的错误排序。  
**破局技巧**：必须认识到通用重排模型极度缺乏对三维空间语义和工程术语的深层隐喻理解。在入库阶段通过 Prompt 指导 VLM 构建描述文本时，应当强制其使用更加显式化、强关系化的结构语态（例如明确生成“件A固定于件B之上”的图节点边关系描述），替代纯粹但模型无法理解的二维几何坐标数字。在系统趋于成熟后，必须收集领域内针对特定空间方位的用户日志，采用对比学习框架对开源重排模型（Cross-encoder）执行特定领域的二次微调适配。

## **面试高频问题：多模态 RAG 架构底层逻辑剖析**

针对积极从传统业务代码岗转型迈入 AI 基础设施工程的架构师候选人，以下 5 个深度考察多模态 RAG 系统底层逻辑的高频面试问题及破题思路，能够有效鉴别其实战深度：  
**Q1：在构建多模态 RAG 架构时，为什么直接采用基于 CLIP 的端到端双塔模型来检索复杂的密集型技术图纸，往往会遭遇毁灭性的性能退化？**

* **答题要点直击**：必须准确点出多模态表征机制的核心痛点——“信息压缩与表征崩溃（Representation Collapse）”。CLIP 架构通过对比学习机制能够高效捕获宏观语义特征，但在其网络结构的末端通常运用全局池化（Global Pooling）策略。这种策略残暴地将整张高分辨率图像极其丰富的局部空间细节和数以百计的小标注节点，硬生生压缩至一个诸如 768 或 1024 维的低维度单一密集向量中6。对于消费级风景照片，全局特征已完全能够区分意图；但在严谨的工程图纸对比中，两张复杂的引擎分解图之间可能仅仅因为角落处多画了一个细小的排气阀门，就代表了截然不同的飞机型号。这种细粒度拓扑结构与微小的文本标注信息在全局压缩的浪潮中必定荡然无存4。

**Q2：以 ColPali 为代表的延迟交互（Late-Interaction）模型相比于传统的 OCR \+ 密集检索管线，究竟取得了什么革命性的工程突破？但采用它又需要承受怎样沉重的系统代价？**

* **答题要点直击**：强调架构范式的改变——“免解析（Parser-free）范式”与“多维图块特征的长效保留”。ColPali 体系彻底抛弃了脆弱、极易引发级联错误的版面分析引擎和 OCR 流程，大胆地将整个 PDF 或图纸作为纯粹的视觉流输入并编码为数百上千个分块级别的局部向量矩阵12。由于其利用了 MaxSim 算子在在线查询阶段才进行跨模态的精细对比打分，极大地保留了原生排版的空间位置信息，在复杂嵌套图表与多模态表单上的召回率呈现碾压态势。然而，没有免费的午餐，代价极其高昂。存储容量需求飙升（每页存储上千向量，是单向量模型的百倍量级），更致命的是由于在线查询需要执行庞大的张量点积矩阵运算，导致延迟激增并疯狂吞噬 GPU 资源，因此它重度依赖类似 Vespa 或 Qdrant 这类在底层融合了特殊内核优化的专用检索引擎，对基础设施的内存带宽要求极为苛刻13。

**Q3：在采用 Describe-then-Index 管线时，你的 VLM 在离线入库阶段不可避免地会对图纸产生幻觉（例如凭空编造不存在的零件名称），作为架构师你该如何系统级地兜底防御？**

* **答题要点直击**：展示多层次防御纵深的系统思维。首道防线是**强约束 JSON Schema 控制**，利用大模型 API（如 OpenAI）的 strict: true 特性，在采样生成底层掩盖非法语义树，配合 Pydantic 构建纯粹封闭的枚举字典与强类型结构，拒绝任何格式自由发挥26。第二道防线为**跨模态数据对齐验证**，利用源 SVG 本身的 XML 特性提取所有硬编码的确定性 ID，作为白名单传递给 VLM，在 Prompt 中要求 VLM 仅对白名单中的已知实体执行特征补全，而非进行开放域识别。最后一道底线是设置极度严苛的系统认知边界（System Prompt）以及将自回归温度（Temperature）固定在零点，阻断发散空间。

**Q4：你的 RAG 系统在同时入库了文本内容与解析后的图纸 JSON 描述后，用户查询“某系统的详细安装调试步骤”，结果由于图纸描述 JSON 过于冗长且堆砌了大量通用术语，导致真正的文本步骤被挤出了 Top-K 召回列表，进而无法作为上下文提交给 LLM。这在业界叫什么现象？你会设计什么算法策略彻底根治？**

* **答题要点直击**：直接指出这属于“向量空间拥挤（Vector Space Crowding）”或特定术语的“特征向量稀释效应”。解题核心在于解除扁平化的耦合，建立结构化层次。提出父子节点层级分块策略（Parent-Child Chunking）作为最优解：在构建嵌入索引时，图片对象只应当派生出包含关键宏观信息的极简“引语块（子节点）”参与余弦空间竞争35；但在 RAG 的组装阶段，一旦这个小块被高亮命中，应用后端的元数据管理系统应当像指针一样，将被它引用的包含完整长文本 JSON 连同周边的图文语境一并捞出，送交 LLM 的提示词窗口。此外，还可以提出基于权重的元数据多路衰减，对纯图纸的召回名额施加预先设定的最高水位线隔离限制35。

**Q5：如果在执行完高精度的文本检索并喂给 LLM 描述之后，终端推理引擎依然判断当前离线生成的扁平 JSON 无法回答用户那些牵扯到极端复杂的三维空间几何干涉或者逻辑跨页问题。面对这种窘境，你的系统编排逻辑将如何优雅地执行降级或接管？**

* **答题要点直击**：考察架构设计中对系统韧性（Resilience）的处理逻辑。阐述具备前瞻性的**智能动态退让（Agentic Fallback / 路由阻断机制）**。当终端 LLM 根据上下文判断信息匮乏并抛出前文约定的 Fail-closed 拒绝异常信号时，整个 RAG 应用决不能就此放弃向用户道歉，而是应当将此异常信号作为一个状态机触发器。系统的多模态微服务会拦截该请求，动态调取关联图解在对象存储中的高保真原版 PNG 切片，直接通过专门负责实时处理复杂难题的当期旗舰大视窗 VLM 发起重载的“二次复核推理”。在回答该问题的最后，必须强调在如此激进的接管机制外部，架构师必须部署如 API 速率限制、分辨率动态降采样等熔断机制，在保障终极解答质量的同时，死守服务整体运行的成本防线。

#### **Works cited**

1. International specification for technical publications \- Logistikportalen, [https://logistikportalen.fmv.se/tjansterprodukter/S1000D/Delade%20dokument/S1000D\_Issue\_4.1.pdf](https://logistikportalen.fmv.se/tjansterprodukter/S1000D/Delade%20dokument/S1000D_Issue_4.1.pdf)  
2. R4i Writer \- CSDB Integrated S1000D Authoring \- Pennant PLC, [https://www.pennantplc.com/r4i-writer-integration-s1000d-authoring/](https://www.pennantplc.com/r4i-writer-integration-s1000d-authoring/)  
3. Scalable images with hotspot links \- Documentation Center, [https://docs.rws.com/livecontent-6-2-1269712/scalable-images-with-hotspot-links-317471](https://docs.rws.com/livecontent-6-2-1269712/scalable-images-with-hotspot-links-317471)  
4. Understanding Late Interaction Models in Multimodal Retrieval | by Mixpeek \- Medium, [https://mixpeek.medium.com/late-interaction-models-are-redefining-how-we-perform-retrieval-over-multimodal-data-not-just-55d438ba5c32](https://mixpeek.medium.com/late-interaction-models-are-redefining-how-we-perform-retrieval-over-multimodal-data-not-just-55d438ba5c32)  
5. Multimodal RAG in 2026: Retrieval Over Images, PDFs, and Text \- BigData Boutique, [https://bigdataboutique.com/blog/multimodal-rag-retrieval-over-images-pdfs-and-text](https://bigdataboutique.com/blog/multimodal-rag-retrieval-over-images-pdfs-and-text)  
6. CLIP: Teaching Vision Models to Understand Natural Language | by Dong-Keon Kim, [https://medium.com/@kdk199604/clip-teaching-vision-models-to-understand-natural-language-0eeceebdcf3c](https://medium.com/@kdk199604/clip-teaching-vision-models-to-understand-natural-language-0eeceebdcf3c)  
7. CLIP: Connecting text and images \- OpenAI, [https://openai.com/index/clip/](https://openai.com/index/clip/)  
8. OpenAI CLIP Model Explained: An Engineer's Guide \- Lightly AI, [https://www.lightly.ai/blog/clip-openai](https://www.lightly.ai/blog/clip-openai)  
9. SigLIP Embeddings: Multimodal Contrastive Learning \- Emergent Mind, [https://www.emergentmind.com/topics/siglip-embeddings](https://www.emergentmind.com/topics/siglip-embeddings)  
10. ColQwen \- Metric AI \- Kaggle, [https://www.kaggle.com/models/metric-ai/colqwen](https://www.kaggle.com/models/metric-ai/colqwen)  
11. Nemotron ColEmbed V2: Top-Performing Late Interaction Embedding Models for Visual Document Retrieval \- arXiv, [https://arxiv.org/html/2602.03992v2](https://arxiv.org/html/2602.03992v2)  
12. An Overview of Late Interaction Retrieval Models: ColBERT, ColPali, and ColQwen, [https://weaviate.io/blog/late-interaction-overview](https://weaviate.io/blog/late-interaction-overview)  
13. Transforming Document Intelligence: Leveraging ColPali and Vespa to Optimize Multimodal Retrieval \- Quantiphi, [https://quantiphi.com/blog/transforming-document-intelligence-leveraging-colpali-and-vespa-to-optimize-multimodal-retrieval/](https://quantiphi.com/blog/transforming-document-intelligence-leveraging-colpali-and-vespa-to-optimize-multimodal-retrieval/)  
14. Boost search relevance with late interaction models \- OpenSearch, [https://opensearch.org/blog/boost-search-relevance-with-late-interaction-models/](https://opensearch.org/blog/boost-search-relevance-with-late-interaction-models/)  
15. Rasterization of SVG images. The Scalable Vector Graphics (SVG)… | by Bhagyashri Kelkar | GumGum Tech Blog | Medium, [https://medium.com/gumgum-tech/rasterization-of-svg-images-43256ad77f27](https://medium.com/gumgum-tech/rasterization-of-svg-images-43256ad77f27)  
16. VGBench: Evaluating Large Language Models on Vector Graphics Understanding and Generation \- ACL Anthology, [https://aclanthology.org/2024.emnlp-main.213.pdf](https://aclanthology.org/2024.emnlp-main.213.pdf)  
17. SVG vs PNG: The Direct Comparison (When to Use Each) \- SVG Genie Blog, [https://www.svggenie.com/blog/svg-vs-png-direct-comparison](https://www.svggenie.com/blog/svg-vs-png-direct-comparison)  
18. How do I calculate image tokens in GPT4 Vision? \- API \- OpenAI Developer Community, [https://community.openai.com/t/how-do-i-calculate-image-tokens-in-gpt4-vision/492318](https://community.openai.com/t/how-do-i-calculate-image-tokens-in-gpt4-vision/492318)  
19. How LLMs See Images (and what it really costs you) | by Rajeev Ratan \- Medium, [https://medium.com/@rajeev\_ratan/how-llms-see-images-and-what-it-really-costs-you-d982ab8e67ed](https://medium.com/@rajeev_ratan/how-llms-see-images-and-what-it-really-costs-you-d982ab8e67ed)  
20. A Picture is Worth 170 Tokens: How Does GPT-4o Encode Images? \- OranLooney.com, [https://www.oranlooney.com/post/gpt-cnn/](https://www.oranlooney.com/post/gpt-cnn/)  
21. Qwen2-VL: Enhancing Vision-Language Model's Perception of the World at Any Resolution, [https://arxiv.org/abs/2409.12191](https://arxiv.org/abs/2409.12191)  
22. \[2502.13923\] Qwen2.5-VL Technical Report \- arXiv, [https://arxiv.org/abs/2502.13923](https://arxiv.org/abs/2502.13923)  
23. Qwen2.5-VL: Advanced Vision-Language Model \- Emergent Mind, [https://www.emergentmind.com/topics/qwen2-5-vl-model](https://www.emergentmind.com/topics/qwen2-5-vl-model)  
24. Qwen2.5-VL: A hands on code walkthrough | by tangbasky \- Towards AI, [https://pub.towardsai.net/qwen2-5-vl-a-hands-on-code-walkthrough-5fba8a34e7d7](https://pub.towardsai.net/qwen2-5-vl-a-hands-on-code-walkthrough-5fba8a34e7d7)  
25. Introduction to Structured Outputs \- OpenAI Developers, [https://developers.openai.com/cookbook/examples/structured\_outputs\_intro](https://developers.openai.com/cookbook/examples/structured_outputs_intro)  
26. Structured model outputs | OpenAI API, [https://developers.openai.com/api/docs/guides/structured-outputs](https://developers.openai.com/api/docs/guides/structured-outputs)  
27. How to use structured outputs with Azure OpenAI in Microsoft Foundry Models, [https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs)  
28. Introducing Structured Outputs in the API \- OpenAI, [https://openai.com/index/introducing-structured-outputs-in-the-api/](https://openai.com/index/introducing-structured-outputs-in-the-api/)  
29. Structured Output for Open Source and Local LLMs \- Instructor, [https://python.useinstructor.com/blog/2024/03/07/open-source-local-structured-output-pydantic-json-openai/](https://python.useinstructor.com/blog/2024/03/07/open-source-local-structured-output-pydantic-json-openai/)  
30. OpenAI Image Token Calculator, [https://image-token-d8ea2703afc6.herokuapp.com/](https://image-token-d8ea2703afc6.herokuapp.com/)  
31. Vision Token Estimator — GPT-4o Image Tokens, Claude & Gemini Multimodal Calculator (Online) | Spoold, [https://www.spoold.com/tools/vision-tokens](https://www.spoold.com/tools/vision-tokens)  
32. Anthropic claude-3-5-sonnet-20241022 Pricing Calculator | API Cost Estimation \- Helicone, [https://www.helicone.ai/llm-cost/provider/anthropic/model/claude-3-5-sonnet-20241022](https://www.helicone.ai/llm-cost/provider/anthropic/model/claude-3-5-sonnet-20241022)  
33. Anthropic claude-3.5-sonnet API Pricing Calculator \- TypingMind Teams, [https://custom.typingmind.com/tools/estimate-llm-usage-costs/claude-3.5-sonnet](https://custom.typingmind.com/tools/estimate-llm-usage-costs/claude-3.5-sonnet)  
34. WebCGM 2.1 \- W3C, [https://www.w3.org/TR/webcgm21/WebCGM21.html](https://www.w3.org/TR/webcgm21/WebCGM21.html)  
35. RAG Chunking: 9 Strategies That Stop “Lost Context” | by Thinking Loop | Medium, [https://medium.com/@ThinkingLoop/rag-chunking-9-strategies-that-stop-lost-context-b4777df4c908](https://medium.com/@ThinkingLoop/rag-chunking-9-strategies-that-stop-lost-context-b4777df4c908)  
36. Chunk Twice, Retrieve Once: RAG Chunking Strategies Optimized for Different Content Types, [https://infohub.delltechnologies.com/p/chunk-twice-retrieve-once-rag-chunking-strategies-optimized-for-different-content-types/](https://infohub.delltechnologies.com/p/chunk-twice-retrieve-once-rag-chunking-strategies-optimized-for-different-content-types/)  
37. Mastering Chunking Strategies for RAG: Best Practices & Code Examples \- Databricks Community, [https://community.databricks.com/t5/technical-blog/the-ultimate-guide-to-chunking-strategies-for-rag-applications/ba-p/113089](https://community.databricks.com/t5/technical-blog/the-ultimate-guide-to-chunking-strategies-for-rag-applications/ba-p/113089)  
38. Visual RAG vs OCR: ColPali for PDFs, Tables, Charts \- Particula Tech, [https://particula.tech/blog/visual-rag-vs-ocr-colpali-pdf-tables-charts](https://particula.tech/blog/visual-rag-vs-ocr-colpali-pdf-tables-charts)  
39. The code used to train and run inference with the ColVision models, e.g. ColPali, ColQwen2, and ColSmol. \- GitHub, [https://github.com/illuin-tech/colpali](https://github.com/illuin-tech/colpali)  
40. Mastering JSON Mode in the OpenAI API \- Grasp, [https://paths.grasp.study/public-courses/b76ccd23-35c2-45e0-8109-60991575adfa/modules/5911e278-c9ac-4aad-a8d7-92c6cce86139/lessons/eac79ba4-a4a1-482e-b0b1-896c4fa30904](https://paths.grasp.study/public-courses/b76ccd23-35c2-45e0-8109-60991575adfa/modules/5911e278-c9ac-4aad-a8d7-92c6cce86139/lessons/eac79ba4-a4a1-482e-b0b1-896c4fa30904)