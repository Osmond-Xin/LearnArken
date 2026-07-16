# **深度调研报告：AI 时代技术文档与可核查代码仓库设计指南**

## **背景：招聘方与技术评审的 AI 代理化迁移**

在软件工程演进的历程中，开发者体验（Developer Experience，简称 DX，指开发者在创建、维护或测试软件时的整体交互体验）的受众群体正在经历一次根本性的范式转移。传统架构下，代码仓库的对外呈现（如 README 文件、贡献指南、变更日志）主要面向人类开发者与开源贡献者。其设计逻辑高度依赖视觉层级、动态徽章（Badges）、表情符号以及精心排版的段落，以传递项目的活跃度与核心价值。然而，随着大型语言模型（Large Language Models, LLMs）与人工智能代理（AI Agents）在技术招聘和代码评审流程中的深度渗透，“人读 README、机器读什么”已经从一个理论探讨演变为极其迫切的工程挑战。  
当前，企业招聘方和顶级开源社区正大规模采用 AI 代理作为筛选候选人与评估项目质量的第一道关卡。行业数据的演变清晰地揭示了这一趋势。例如，开源技术招聘工具 hiring-agent 已经部署了一条成熟的“简历到评分（Resume-to-Score）”自动化流水线。该系统不仅能够将 PDF 格式的简历精准解析为结构化的 Markdown 数据，还能通过 API 自动深入候选人的 GitHub 仓库，抓取提交频率、代码质量、开源项目贡献等深层信号1。更进一步，诸如 GitHub Talent Matcher 这样的 AI 代理，会基于候选人的代码仓库活动，自动提取其核心技术栈，预估雇佣成本，并计算其与特定岗位的匹配度得分3。  
在这一背景下，如果开发者的项目仓库缺乏“机器可读性”，便会在 AI 代理的初步筛查中被判定为“信息缺失”或“无法核查”。传统那些充满冗长营销词汇、缺乏语义结构定义、甚至证据链断裂的仓库，无法有效传递开发者的真实能力。因此，将传统项目改造为“招聘方及其 AI 代理可核查”的形态，不仅是技术文档标准的必然升级，更是资深产品经理和传统程序员在转型 AI 工程时，建立个人技术品牌与供应链信任的核心基础设施。

## **llms.txt 标准详解：起源、规范与生态走向**

为了解决大模型在推理（Inference，即模型接收提示并生成输出的阶段）时效性与上下文理解难题，Answer.AI 的联合创始人 Jeremy Howard 于 2024 年 9 月正式提出了 /llms.txt 标准5。该标准旨在为 AI 代理提供一个高度浓缩、富含语义信息的项目导览图，降低解析复杂 HTML 页面带来的上下文窗口（Context Window，即模型一次能处理的最大文本量）消耗。

### **规范结构与技术逻辑**

/llms.txt 是一个必须放置在网站或代码仓库根目录下的纯文本 Markdown 文件。之所以选择 Markdown 而非 XML 或 JSON，是因为 Markdown 是当前大型语言模型的“通用语（Lingua Franca）”，其在保持机器可解析性的同时，依然具备极高的人类可读性6。标准的 llms.txt 文件包含严格排序的特定模块：  
首个模块是强制要求的 H1 标题，用于明确声明项目或站点的名称。紧随其后的是一个 Blockquote（引用块）摘要，该摘要通常包含一到三句极其简练的总结，为 AI 提供理解后续所有文件链接所需的核心上下文。随后，开发者可以加入可选的纯文本段落以补充项目背景。核心部分是由 H2 标题划分的文件映射列表，规定格式为包含链接和简短描述的 Markdown 列表（如 \[文件名称\](URL): 补充说明）。规范还引入了一个具备特殊语义的 \#\# Optional 章节，向 AI 发出明确的资源调度信号：当上下文窗口紧张时，代理可以安全地丢弃该章节下的非核心链接6。

### **与传统爬虫协议的类比分析**

为了深刻理解 llms.txt 的架构定位，将其与经典的 Web 爬虫协议进行对比是极其必要的。

| 协议标准 | 目标受众与解析器 | 核心机制与格式 | 核心工程目的 |
| :---- | :---- | :---- | :---- |
| robots.txt | 传统搜索引擎爬虫（如 Googlebot） | 权限控制指令（Allow / Disallow） | 划定站点的抓取边界，防止隐私泄漏与服务器过载，完全不涉及语义上下文6。 |
| sitemap.xml | 传统搜索引擎爬虫 | 穷举式 URL 列表（XML 结构） | 强调绝对的完整性，帮助搜索引擎发现所有深层链接，不包含人类或 AI 友好的语义描述6。 |
| llms.txt | 大语言模型与自治 AI 代理 | 语义策展与链接映射（Markdown 结构） | 强调信息密度的提纯与优先级排序。为每个入选链接提供上下文描述，以最小的 Token 消耗换取最高的理解准确度6。 |

基准测试数据进一步证明了这种设计的优越性。在相同的字符预算下，纯净的 Markdown 格式相比保留了 HTML 标签的原始网页，能够多覆盖 4 到 6 倍的有效文档内容，从而在 AI 理解力测试中取得显著更高的分数7。

### **2025–2026 年采纳现状与反模式**

截至 2026 年，llms.txt 已经获得了开源社区和商业工具的广泛采纳。知名文档生成框架如 Sphinx、VitePress 和 Docusaurus 均已集成官方或第三方插件，支持在持续集成（CI）阶段自动生成该文件5。同时，Apify 等数据提取平台也推出了专门的 Actor 工具，用于自动遍历多层级网站并输出标准化的 llms.txt10。在宏观层面，关于在 2026 年将该协议纳入 W3C 官方标准的提案讨论正在加速，这标志着生成式引擎优化（Generative Engine Optimization, GEO）正式成为 DX 领域的关键分支9。  
然而，在实际采纳过程中，业界关于格式选择的探讨并未停止。例如在 Typst 开源项目的采纳讨论中，部分维护者提出 Markdown 在作为严格的机器规范格式时存在解析不稳定的隐患，甚至探讨了 JSON 或 YAML 作为替代方案的可能性12。尽管如此，考虑到现有 LLM 训练语料的分布特征，Markdown 依然是目前最优的工程折中方案。  
在重构项目仓库时，开发者极易陷入将 llms.txt 视作营销文案的反模式。人类开发者习惯于在 README 中使用“革命性的、极速的、下一代”等修饰语，但对于 LLM 而言，这类缺乏信息熵的词汇不仅稀释了关键语义，还浪费了宝贵的 Token 预算。最佳实践要求开发者必须使用客观、干瘪且精准的陈述句，直接说明架构约束、输入输出格式及核心依赖。

## **证据链设计：可复现性声明的工程化**

在 AI 参与的招聘与项目评审中，无论是声称“测试覆盖率达到 95%”还是“系统吞吐量提升至 10k TPS”，缺乏底层证据支撑的自述声明都将被评估系统直接标记为“高风险”或“不可信”。AI 代理具备独立执行命令和核验数据的能力，这要求项目仓库必须具备极高的透明度。EVIDENCE.md 便是解决这一信任危机的核心设计，它将宏观对外的声明通过强类型映射表与仓库内的微观证据紧密绑定。

### **Evidence Mapping 的组织方式**

一个专业的 EVIDENCE.md 并非松散的开发日志，而是一套具备法律或审计级别严谨性的证据追踪矩阵。行业领先的量化投资与合规评估项目（如 investor-harness 和 nisify）为我们提供了成熟的证据分级分类模板13。这些项目将证据按照可信赖度与验证成本进行严格区分。  
在技术仓库的改造中，开发者应当建立如下的映射分类体系：

| 声明分类 (Claim Category) | 定义与验证标准 (Definition & Validation) | 工程化证据容器 (Engineering Evidence) |
| :---- | :---- | :---- |
| 公开事实 (Public Facts) | 状态稳定、可通过外部权威 API 或区块链浏览器直接无状态验证的基础事实。 | 智能合约部署地址、NPM 包发布版本号及其不可篡改的校验和（Checksum）。 |
| 审计披露 (Disclosures) | 明确对应到特定版本测试报告或合规扫描的精确数值。 | CI/CD 流水线生成的测试覆盖率报告（如 lcov.info），并附带生成该报告的 Git Commit Hash。 |
| 合理推演 (Derived Logic) | 基于基础数据通过特定算法推导出的性能或架构结论。 | 必须包含推导链路的复现脚本路径（如 scripts/benchmark.sh）及所用冻结数据集的版本。 |
| 待核验假设 (Hypotheses) | 尚未经过生产环境长周期验证的实验性设计。 | 明确标注为“实验性”，并提供基准对比的初步探索日志。 |

### **可复现性声明的工程落地**

为了消除评估代理在核验过程中的障碍，每一项关键指标必须实现彻底的“数字到复跑命令”的映射。这种工程化要求开发者规避“容器谬误（Container Fallacy）”。根据决策证据成熟度模型（DEMM）的定义，容器谬误是指系统虽然生成了庞大的执行日志（即证据的容器），但当外部审计代理针对某一特定决策提出具体核查请求时，这些杂乱的日志却缺乏属性级的重构能力，导致证据无效15。  
为了防范这一谬误，声明与证据的映射必须达到指令级的精确。如果项目声明在某一特定负载下内存泄漏为零，EVIDENCE.md 中不能仅仅贴出一张图表，而必须提供一段可在标准化 Docker 环境中无副作用执行的验证指令。同时，所有的测试必须挂载精确到 SHA-256 哈希值的数据集快照，确保 AI 代理在任何时刻复跑都能获得与声明完全一致的结果。

### **供应链信任与 Co-Authored-By 诚实标注**

在向 AI 工程师转型的过程中，候选人不可避免地会在项目中大量使用诸如 GitHub Copilot 或 Claude 等智能编码助手。此时，如何向雇主证明自身的能力，便转化为了供应链信任（Supply Chain Trust）的管理问题。  
掩盖 AI 的参与不仅是不切实际的，在专业的自动化代码溯源工具面前也是极其脆弱的。行业最佳实践提倡“激进的透明度”。在每次将 AI 生成的实质性代码合并入主分支时，开发者应在 Git 提交信息中利用标准的署名机制（如 Co-Authored-By: AI Agent \<bot@agent.ai\>）进行诚实标注。这种做法不仅建立了清晰的代码出处（Provenance）追踪，更向评审方的 AI 代理证明了候选人具备极高的工程伦理标准以及成熟的混合智能协作管理能力。

## **AI 协作工作流的对外表述**

当一个项目仓库中 80% 的具体实现代码均由 AI 自动生成时，传统程序员转型产品或高级工程师的核心价值便从“代码编写”转移到了“规格制定（Specification）”与“判断决策（Judgment）”上。如何向雇主无可辩驳地证明这一分工的真实性，是 AI 协作工作流说明文档 需要解决的核心命题。

### **不可伪造的人类产出：决策记录与裁决日志**

在 AI 代理包揽了繁重实现的架构中，雇主考察的是人类开发者的业务抽象能力与技术边界把控力。为此，开发者必须在仓库中留下“不可伪造的人类产出（Unforgeable Human Output）”。  
架构决策记录（Architecture Decision Records, ADRs）是展示这种能力的最佳载体。AI 擅长根据明确的提示生成某个特定数据库的连接池代码，但 AI 无法独立权衡企业的历史技术债务、特定周期的预算约束以及团队的维护能力。人类工程师需要撰写详尽的 ADR，记录“在当时的环境约束下，为什么驳回了 AI 提议的微服务架构，而坚持采用模块化单体”。  
此外，保留对抗性审查与纠偏日志（Correction Logs）同样至关重要。开发者应在工作流文档中展示 AI 初始生成的带有安全漏洞或逻辑缺陷的代码片段，并详细记录自己是如何通过识别缺陷、重构上下文提示、甚至是调整测试用例，最终引导 AI 输出安全可靠的代码。这种由人类发起的裁决（Adjudication）过程，是证明开发者正在“驾驭”AI，而非被 AI 降维替代的铁证。

### **Adversarial Validation（对抗性验证）的语境演变**

在撰写高级 AI 工作流文档并向雇主阐述系统架构时，精确使用行业术语能够极大提升专业度。其中，**Adversarial Validation（对抗性验证）** 一词的含义在传统机器学习与现代自治 AI 代理治理（Governed-AI）中存在着根本性的区别。  
在传统的机器学习（ML）领域，对抗性验证是一种用于检测训练集与测试集之间是否存在分布偏移（Distribution Shift）的数据诊断技术。其经典做法是将训练集与测试集混合，分别打上二元标签，随后训练一个判别模型。如果该模型能够轻易区分数据来源，则说明两者分布差异显著，模型泛化将面临风险。  
然而，在 2025 至 2026 年的 AI 代理安全与软件工程交叉领域，该术语经历了彻底的重构。在诸如 Parallax 架构范式与 Audn 等自动化红蓝对抗安全工具的语境下，对抗性验证演变为一种“架构层面的安全隔离与执行拦截机制”16。它基于“认知与执行分离（Cognitive-Executive Separation）”的核心原则。  
在这种现代语境中，防御系统假设进行推理与规划的 AI 代理随时可能被提示注入（Prompt Injection）或外部恶意数据攻破。因此，在代理的“思考系统”与最终的“执行引擎”之间，必须强制插入一个独立的、无状态的验证层（Shield）。这个验证层以纯粹的对抗心态运作，它不与代理共享任何上下文或信任基础，通过逐步升级的渐进确定性（Graduated Determinism）策略——从确定性的静态 YAML 规则拦截、到无大模型的机器学习分类器，最终兜底到人类参与的审批（Human-in-the-Loop）——来严密审查每一次 API 调用或数据库写入请求17。在作品集中展示这种级别的对抗性验证架构，将向安全与工程主管传递出候选人具备构建企业级高可信 AI 系统能力的强烈信号。现代代理信任边界模型（Agent Trust Boundary Model）同样强调，模型可以提出建议，但运行时环境必须拥有绝对的授权边界18。

## **当前主流与未来：AI 可读文档的生态走向**

除了供外部大型语言模型被动抓取和建立索引的 llms.txt，AI 时代的工程规范正在迅速向主动约束并指导自治代理行为的方向演进。

### **agents.md 与技能封装的崛起**

在解决多个 AI 编码助手（如 GitHub Copilot、Cursor、OpenAI Codex 等）配置文件严重碎片化的问题上，agents.md 在 2025 年脱颖而出，并迅速成为行业公认的开放标准19。该规范由 OpenAI 等巨头推动，并随后移交至 Linux 基金会旗下的 Agentic AI 基金会进行长期维护，目前已被超过六万个开源仓库采用20。  
agents.md 被誉为“面向代理的 README”。其核心设计哲学是极简主义与工具无关性：无需复杂的目录层级、无需特定的前置元数据（Frontmatter），完全采用纯 Markdown 编写。它为深入仓库内部协助开发的 AI 代理提供有关代码风格、依赖注入规则、测试运行器命令以及开发环境配置的全局指导19。高级实现（如 OpenAI Codex）甚至支持层次化的继承机制，允许在单体仓库（Monorepo）的子目录下使用 AGENTS.override.md 进行局部规则覆盖19。  
与此同时，以 Anthropic 提出的 Agent Skills（通常体现为 SKILL.md 文件）为代表的另一种生态规范也在蓬勃发展23。与全局约束的 agents.md 不同，技能模型强调通过文件夹将特定的操作程序、测试脚本和参考模板封装为独立的模块。AI 代理采用“渐进式披露（Progressive Disclosure）”机制：在启动阶段仅加载极其轻量的元数据与描述，只有当用户的意图匹配该技能时，代理才会将完整的 SKILL.md 指令读入宝贵的上下文窗口23。通过在作品集中熟练部署这些规范，开发者能够无可辩驳地证明其项目具备极高的“可代理化水平（Agentic Readiness）”。

### **作品集仓库被 AI 评估的必然趋势**

面向未来的技术招聘，人力资源的初步筛选正不可逆转地交由评估代理（Evaluation Agents）执行。这意味着，人类招聘官或许只会审阅那些已经被 AI 工具打上高匹配度标签的精选仓库。在这个生态下，没有配置容器化构建脚本、缺乏持续集成流程的仓库将在自动化测试流水线中直接崩溃；而缺乏 llms.txt 进行上下文引导、缺乏 EVIDENCE.md 提供信任链条的项目，则会被评估模型判定为“黑盒”或“噪音”，导致候选人潜藏的核心亮点永远无法呈递到人类决策者眼前。

## **必须掌握的技巧与坑：5 个常见错误**

在将传统项目仓库重构为高度适配 AI 代理审查标准的过程中，开发者极易因为思维惯性而跌入以下五个常见的工程陷阱：

1. **将 llms.txt 写成公关与营销文案**  
   人类阅读者可能习惯于被“这是一款采用下一代革命性架构、颠覆行业的极致性能工具”等修辞吸引。但在 AI 代理的语境中，这类营销词汇是致命的反模式。它们不仅极大地稀释了文档的语义密度，还无谓地占用了 Token 预算。开发者必须彻底转向工程师视角的精准表达，使用极度干瘪、明确的陈述句，直接界定项目的技术栈依赖、输入输出契约以及绝对的系统边界。  
2. **证据链断链与硬编码依赖**  
   在 EVIDENCE.md 的初始构建中，开发者可能引用了某个测试日志文件。然而随着后续代码的大规模重构或目录调整，该日志文件被意外移动或删除，导致 AI 代理在回溯验证时遭遇死链。这种断链在审计系统中会立刻触发严重的不信任警报。优秀的重构应在 CI/CD 流水线中强制植入自动化死链检测与证据完整性校验步骤，确保任何导致证据路径失效的提交都将被拒绝合并。  
3. **宏观声明与底层证据数据不一致**  
   这是一个极具破坏性的信任陷阱。例如，仓库的 README 宣称“缓存命中率提升了 40%”，但当评估代理顺着证据链查找到最终的基准测试日志时，却发现实际提升仅为 32%。在人类审查中，这或许会被视为统计口径的轻微误差，但在严苛的机器核验下，直接触发数据伪造或“诚实度缺失”的判定。为了杜绝此类现象，所有的关键指标声明都不应在文档中手写硬编码，而应在持续构建流程中，通过模板引擎从唯一的真实数据源（如基准测试生成的 JSON 结果文件）中动态注入。  
4. **忽视多语言与本地化带来的上下文膨胀** 部分开发者利用自动化爬虫工具生成 llms.txt 时，未对站点的多语言结构进行干预，导致工具将诸如 /en-us/、/fr-fr/ 等所有本地化变体页面全部纳入文件映射列表25。对于依赖 Token 效率的大模型而言，这会造就一个体积庞大但内部包含高达 90% 重复语义的灾难性文件。标准的防范措施是，对提供给 AI 的文件映射进行严格去重，仅保留单一核心语言（通常为技术标准的英语）的规范化 URL 集合，以保障上下文窗口的极致纯净。  
5. **未利用内联属性解决表格的语义歧义** 当项目包含复杂的对比数据（如竞品性能对比或定价表格）时，单纯使用传统的 Markdown 表格可能导致检索增强生成（RAG）系统在向量切分时丢失表头上下文，从而产生“将竞品的劣势张冠李戴给本项目”的灾难性幻觉。前沿的解决思路是采用类似于 data-llm 的自定义内联属性提案，将标准化的结构数据（如 JSON 映射）直接嵌入相关的 HTML 元素中，从而在底层提供不可磨灭的语义消歧义上下文，防范上下文破碎26。

## **面试高频问题**

在资深产品经理与传统程序员向 AI 工程师转型的面试场景中，招聘方及辅助评估系统通常会围绕“AI-first 工作流与项目可核查性”提出极其尖锐的问题。以下五个高频问题及其答题要点，构成了候选人自证能力的核心防御体系：

### **问题 1：如果你的作品集仓库中 80% 的具体实现代码是由 AI 代理生成的，我作为招聘方，如何评估你个人的真实工程水平？**

**答题要点**：必须将面试官的视角从底层代码编写引导至高阶的系统治理。明确阐述在混合智能开发中，“架构设计、系统边界定义以及伦理规范约束”才是不可伪造的人类核心产出。主动引导面试官审查仓库中的 EVIDENCE.md 以及架构决策记录（ADRs），详细说明自己是如何进行数据域的拆分、如何定义模块间严格的契约接口，并通过呈现包含丰富人类思辨的审查日志，证明自身具备在极高抽象维度上监督、控制并重构 AI 提议的架构师能力。

### **问题 2：我们在你的项目中同时观察到了 README.md、llms.txt 和 agents.md，请深刻阐述它们在系统生态中的分工与设计初衷。**

**答题要点**：这三者分别对应完全不同的受众与交互时机。README.md 面向人类用户与贡献者，其使命是通过视觉化的组件、流程图和安装向导提供直观的宏观概览。llms.txt 则是面向外部检索大模型和搜索引擎的静态快照，通过极简的结构提供项目知识体系的索引与导览，降低被动检索时的 Token 消耗。而 agents.md 是动态的、面向开发环境内部 AI 助手的行为宪法，它强制规定了代理在生成代码时必须遵循的代码规范、测试用例构建指令以及环境依赖约束，是驱动代理规范化行动的引擎。

### **问题 3：你在工作流文档中强调了系统采用“Adversarial Validation（对抗性验证）”来保障高阶代理的安全。这与我们在传统机器学习训练中谈论的分布偏移检测究竟有何不同？**

**答题要点**：必须展现出对不同时代技术语境的精准把握。明确指出，传统机器学习中的对抗性验证是数据科学家在离线阶段使用的一种分类器手段，用于检测训练集与测试集的数据分布差异。而在当今的自治 AI 代理治理（Governed-AI）中，对抗性验证指的是一种“认知系统与执行系统强制物理或逻辑分离”的深度防御架构（如 Parallax 范式）。它在假设规划代理已经被恶意注入的前提下，引入一个完全独立的、具有渐进确定性拦截能力的验证屏障，在操作实际触达数据库或外部网络前进行阻断，两者在所处阶段、面对的威胁模型以及工程实现上有着天壤之别。

### **问题 4：如果随着业务迭代，你的测试数据集发生了更新，你如何向我们保证 EVIDENCE.md 中的历史证据链不会悄无声息地失效或被篡改？**

**答题要点**：直击证据持久化与状态隔离的痛点。阐述系统引入了不可篡改的数据快照（Snapshots）与哈希绑定机制。在 CI/CD 自动化流水线中，任何一次针对关键指标的基准测试，都会将执行该测试的命令、代码版本的 Git Commit Hash，以及当时所用数据集的 SHA-256 校验和进行强绑定。即便未来的数据集发生了全量更新，审计者依然能够通过提取历史版本的代码与冻结的数据快照，完全无差别地复现当时的测试结论，彻底消灭“容器谬误”带来的信任危机。

### **问题 5：回顾你在 AI-first 研发链路中的实践，你认为传统程序员向 AI 工程转型的最大壁垒是什么？你的仓库又是如何跨越这一壁垒的？**

**答题要点**：提升回答的哲学与工程高度。指出最大的壁垒绝不是对某种新框架语法的掌握，而是思维模式的蜕变：从编写过程式、命令式的死板指令（Imperative Code），向设计声明式的上下文（Declarative Context）、定义完备的工具契约以及构建坚不可摧的验证护栏（Validation Guardrails）转变。强调自己提交的可核查仓库本身就是跨越这一壁垒的工程学实体证明：它不再是一堆静态代码的堆砌，而是一个高度透明、规则明确、且对自治代理充满包容与限制的现代化混合智能协作系统。

#### **Works cited**

1. interviewstreet/hiring-agent: AI agent to evaluate and score resumes. \- GitHub, [https://github.com/interviewstreet/hiring-agent](https://github.com/interviewstreet/hiring-agent)  
2. Hiring Agent: AI-Powered Resume Scoring with GitHub Signals | AIToolly, [https://aitoolly.com/ai-news/article/2026-06-26-interviewstreet-unveils-hiring-agent-an-ai-powered-pipeline-for-explainable-resume-scoring-and-githu](https://aitoolly.com/ai-news/article/2026-06-26-interviewstreet-unveils-hiring-agent-an-ai-powered-pipeline-for-explainable-resume-scoring-and-githu)  
3. GitHub Talent Matcher | Agent.AI, [https://agent.ai/agent/gitHub-talent-matcher](https://agent.ai/agent/gitHub-talent-matcher)  
4. From Open Source to Open Roles: AI-Powered Recruitment Agent \- DEV Community, [https://dev.to/pppp606/from-open-source-to-open-roles-ai-powered-recruitment-agent-141o](https://dev.to/pppp606/from-open-source-to-open-roles-ai-powered-recruitment-agent-141o)  
5. GitHub \- AnswerDotAI/llms-txt: The /llms.txt file, helping language models use your website, [https://github.com/answerdotai/llms-txt](https://github.com/answerdotai/llms-txt)  
6. What is llms.txt and Why Every Website Needs One in 2026 \- Qwestyon, [https://www.qwestyon.com/blog/what-is-llms-txt-and-why-every-website-needs-one](https://www.qwestyon.com/blog/what-is-llms-txt-and-why-every-website-needs-one)  
7. Llms.txt for documentation \- Ubuntu Discourse, [https://discourse.ubuntu.com/t/llms-txt-for-documentation/79900](https://discourse.ubuntu.com/t/llms-txt-for-documentation/79900)  
8. Python source \- llms-txt, [https://llmstxt.org/core.html](https://llmstxt.org/core.html)  
9. What is llms.txt? Guide for GEO & AI Content Control | Savvy, [https://savvy.co.il/en/blog/wordpress-seo/llms-txt-guide/](https://savvy.co.il/en/blog/wordpress-seo/llms-txt-guide/)  
10. GitHub \- apify/actor-llmstxt-generator: The /llms.txt Generator Actor 🕸️ extracts website content to create an llms.txt file for AI apps like LLM fine-tuning and indexing. Output is available in the Key-Value Store for easy download and integration into workflows., [https://github.com/apify/actor-llmstxt-generator](https://github.com/apify/actor-llmstxt-generator)  
11. What The June 2026 W3C Proposal To Standardize llms.txt Means, [https://www.pravinkumar.co/blog/w3c-llms-txt-standard-proposal-june-2026-webflow-2026](https://www.pravinkumar.co/blog/w3c-llms-txt-standard-proposal-june-2026-webflow-2026)  
12. Proposal: Adopt llms.txt Standard for Enhanced LLM Accessibility of typst code · Issue \#5840, [https://github.com/typst/typst/issues/5840](https://github.com/typst/typst/issues/5840)  
13. nisify/docs/manual-evidence.md at main \- GitHub, [https://github.com/clay-good/nisify/blob/main/docs/manual-evidence.md](https://github.com/clay-good/nisify/blob/main/docs/manual-evidence.md)  
14. evidence.md \- joansongjr/investor-harness \- GitHub, [https://github.com/joansongjr/investor-harness/blob/main/core/evidence.md](https://github.com/joansongjr/investor-harness/blob/main/core/evidence.md)  
15. Decision Evidence Maturity Model for Agentic AI: A Property-Level Method Specification, [https://www.researchgate.net/publication/404542383\_Decision\_Evidence\_Maturity\_Model\_for\_Agentic\_AI\_A\_Property-Level\_Method\_Specification](https://www.researchgate.net/publication/404542383_Decision_Evidence_Maturity_Model_for_Agentic_AI_A_Property-Level_Method_Specification)  
16. Audn.AI, [https://audn.ai/](https://audn.ai/)  
17. Parallax: Why AI Agents That Think Must Never Act \- arXiv, [https://arxiv.org/html/2604.12986v1](https://arxiv.org/html/2604.12986v1)  
18. AI Agent Architecture: The Trust Boundary Model | aakashx, [https://www.aakashx.com/blog/agent-trust-boundary-model-ai-agent-architecture/](https://www.aakashx.com/blog/agent-trust-boundary-model-ai-agent-architecture/)  
19. agents.md: The Complete Guide to the Open Standard for AI Coding Agents | PRPM, [https://prpm.dev/blog/agents-md-deep-dive](https://prpm.dev/blog/agents-md-deep-dive)  
20. What is Agents Md Standard? \- YouTube, [https://www.youtube.com/watch?v=OozoHlE9aqY](https://www.youtube.com/watch?v=OozoHlE9aqY)  
21. AGENTS.md, [https://agents.md/](https://agents.md/)  
22. AGENTS.md — a simple, open format for guiding coding agents \- GitHub, [https://github.com/agentsmd/agents.md](https://github.com/agentsmd/agents.md)  
23. Agent Skills Overview \- Agent Skills, [https://agentskills.io/home](https://agentskills.io/home)  
24. Specification \- Agent Skills, [https://agentskills.io/specification](https://agentskills.io/specification)  
25. Multilingual sites handling \+ Tool listing proposal · Issue \#108 · AnswerDotAI/llms-txt, [https://github.com/AnswerDotAI/llms-txt/issues/108](https://github.com/AnswerDotAI/llms-txt/issues/108)  
26. Proposal: HTML data-llm Attributes for Enhanced AI Content Understanding \#77 \- GitHub, [https://github.com/AnswerDotAI/llms-txt/issues/77](https://github.com/AnswerDotAI/llms-txt/issues/77)