> 来源：Gemini App Deep Research，日期 2026-07-20。

# **LLM 推理期搜索与 Agent 架构深度调研报告**

在大型语言模型（LLM）的工程应用演进中，如何使模型跨越单次自回归生成的局限，实现复杂问题的多步深度求解，始终是 Agent 架构领域的核心命题。从传统的软件工程视角审视，早期的提示词工程（Prompt Engineering）类似于单线程阻塞的函数执行：输入特定的参数（Prompt），随后被动等待单线程式的输出返回。然而，在面对诸如复杂数据格式校验、代码自动化修复等需要动态探索、逻辑回溯与严格闭环验证的任务时，单次生成的成功率不可避免地会触及天花板。  
为了突破这一瓶颈，学术界与工业界在 2022 年至 2026 年间，孕育并发展出了一条清晰且极具工程价值的“推理期搜索（Inference-time Search）”脉络。这一技术流派本质上是将传统计算机科学中久经考验的数据结构与图搜索算法，与 LLM 强大的非结构化生成能力进行了深度融合。本报告专为正从传统软件工程转型 AI 工程的资深开发者与产品经理编写，将深度剖析推理期搜索的方法谱系、成本边界、世界模型的工程定位，并针对“多候选代码修复与沙箱验证”这一具体的半日玩具实验场景，提供详尽的架构设计指导与工程避坑指南。

## **1\. 推理期搜索方法谱系与源流演进**

推理期搜索架构的演进史，可以被看作是 LLM 任务规划数据结构从一维线性向多维非线性拓展的历史。这一过程中的每一次飞跃，都在传统算法理论中有着极其精确的映射。

### **1.1 ReAct (2022)：交织推理与行动的“单链表”**

在 2022 年，由 Yao 等人提出的 ReAct（Reasoning \+ Acting）架构首次打破了模型内部思考与外部环境交互的壁垒1。在此之前，纯粹的思维链（Chain of Thought, CoT）仅仅是一个静态的内部黑盒，模型依赖参数化知识进行空想，极易产生事实幻觉；而纯粹的行动驱动模型又往往缺乏长远的执行规划。ReAct 通过强制模型在输出中交替生成内部状态思考和外部 API 调用动作，构建了一个动态响应机制。  
在原始论文（URL: https://arxiv.org/abs/2210.03629）中，该方法被应用于 HotpotQA（多跳问答）、ALFWorld（文本游戏）以及 WebShop（网页导航）等任务。实验表明，仅需少量示例，ReAct 就能在 ALFWorld 和 WebShop 上分别取得 34% 和 10% 的绝对成功率提升1。从传统软件工程的角度来看，ReAct 类似于带有异常捕获（try-catch）机制的单线程顺序执行流或状态机。程序沿着单向链表（Linked List）前进，若接收到外部环境的报错，模型会在下一个执行周期尝试进行修正，但它并不具备状态保存与分支回溯的能力。一旦当前路径陷入死胡同，任务往往以失败告终。

### **1.2 Tree of Thoughts (ToT, 2023)：探索多路径的“多叉树”**

为了克服 ReAct 无法回溯的致命弱点，Yao 等人在 2023 年进一步提出了 Tree of Thoughts（思维树）框架3。ToT 的核心思想是将复杂问题分解为连贯的中间步骤（Thoughts），并允许模型在每个步骤节点上同时生成多个候选分支。更重要的是，ToT 引入了模型自我评估（Self-evaluation）机制，由 LLM 自身或外部规则对各个分支的价值进行打分。  
原始论文（URL: https://arxiv.org/abs/2305.10601）在算子游戏（Game of 24）、创意写作和迷你填字游戏上验证了该方法的威力。例如在 Game of 24 任务中，传统的 CoT 提示法仅有 4% 的成功率，而引入 ToT 后，成功率飙升至 74%3。这种架构在传统算法中的映射非常直观，即标准的深度优先搜索（DFS）或广度优先搜索（BFS），并结合了启发式剪枝（Heuristic Pruning）。它赋予了 Agent 类似于回溯算法（Backtracking）的能力，使其在走迷宫遇到死路时，能够从内存栈中恢复上一个交叉口的状态并探索新的可能。

### **1.3 Graph of Thoughts (GoT, 2023)：支持合并与循环的“有向图”**

树形结构虽然支持多路径探索，但各条路径之间是绝对隔离的。2023 年，Besta 等人通过 Graph of Thoughts（思维图）进一步拓宽了搜索结构的边界4。GoT 允许将不同的推理路径进行合并（Aggregation），从而提炼出融合了多个视角的综合方案。  
在原始论文（URL: https://arxiv.org/abs/2308.09687）中，GoT 被应用于数组排序、集合求交集和文档摘要等任务。数据表明，在复杂的排序任务中，GoT 的输出质量比 ToT 提升了 62%，同时得益于中间节点的重用与合并，其 Token 成本反而降低了 31% 以上4。在传统软件工程中，这种思想等同于有向无环图（DAG）工作流编排，或是动态规划（Dynamic Programming）算法中利用备忘录（Memoization）机制来合并重叠子问题，极大地提升了系统的协同增效能力。

### **1.4 LATS (LLM+MCTS, 2023)：引入统计与对弈的“博弈树”**

同年，Zhou 等人提出的 Language Agent Tree Search（LATS）标志着推理期搜索向统计机器学习领域的深度融合6。LATS 将蒙特卡洛树搜索（MCTS）应用于 LLM Agent 架构中，使用著名的 UCT（Upper Confidence Bound applied to Trees）公式来在探索未知路径（Exploration）与利用已知高分路径（Exploitation）之间取得数学上的平衡。  
原始论文（URL: https://arxiv.org/abs/2310.04406）展示了该方法在 HumanEval 编程测试中取得了 92.7% 的 pass@1 准确率，并在 WebShop 任务中达到了与梯度微调相媲美的 75.9 分6。LATS 强制要求引入外部环境（如代码沙箱）的真实反馈作为节点奖励，并通过 MCTS 的反向传播（Backpropagation）机制更新整条链路的期望价值。这在传统算法中可以完美类比为 AlphaGo 核心算法的自然语言实现版本，它不仅评估当前步骤的直接收益，更通过多次模拟推演（Rollout），计算该路径最终通向成功修复的统计学期望概率。  
为了更直观地对比上述四种核心范式，以下表格总结了它们的关键技术特征与工程映射：

| 方法名称与年份 | 核心论文 URL | 核心数据结构 | 原论文测试任务 | 相对前作的核心突破 | 传统算法类比 |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **ReAct (2022)** | https://arxiv.org/abs/2210.03629 | 单向链表 | 多跳问答、网页导航、文本游戏 | 引入外部环境反馈，克服静态推理引发的幻觉。 | 单线程阻塞执行 \+ try-catch 异常捕获机制 |
| **ToT (2023)** | https://arxiv.org/abs/2305.10601 | 多叉树 | Game of 24、创意写作、填字游戏 | 引入分支扩展与状态恢复，解决单路径易陷入死胡同的缺陷。 | DFS / BFS 图搜索 \+ 启发式分支剪枝 \+ 回溯 |
| **GoT (2023)** | https://arxiv.org/abs/2308.09687 | 有向无环图 (DAG) | 数组排序、文档摘要、集合运算 | 允许路径合并与反馈循环，实现跨分支灵感的协同增效。 | DAG 工作流引擎 / 动态规划中的重叠子问题合并 |
| **LATS (2023)** | https://arxiv.org/abs/2310.04406 | MCTS (博弈树) | 编程生成 (HumanEval)、交互式问答 | 引入置信度上限公式与外部真实奖励回传，平衡探索与利用。 | 蒙特卡洛树搜索 / AlphaGo 博弈树评估 |

## **2\. 适用边界与生产环境的成本模型**

在将推理期搜索从实验室迁移到企业级生产环境时，工程团队面临的最大挑战是计算成本的非线性爆炸。

### **2.1 分支数与深度的 Token 成本爆炸机制**

在传统的图搜索算法中，扩展树的宽度和深度仅仅消耗极其廉价的 CPU 时钟周期和内存。然而在 LLM 架构中，成本模型发生了质变。假设一棵搜索树的平均分支因子为 ![][image1]，探索深度为 ![][image2]，采用广度优先搜索（BFS）策略。生成的节点总数在最坏情况下为 ![][image3]。如果每个节点都需要 LLM 进行 ![][image4] 次自我评估调用，则 API 调用次数呈指数级增长。  
更严峻的是，由于 Transformer 架构依赖上下文窗口，当前节点在进行扩展时，必须将其从根节点开始的所有历史轨迹（包括生成的代码、沙箱的报错日志等）作为上下文输入。这意味着 Token 的消耗量随着深度 ![][image2] 呈现超线性的甚至二次方的爆炸趋势8。因此，在没有严格剪枝策略的情况下，纯粹的 ToT 或 MCTS 架构在商业应用中是不可持续的。

### **2.2 任务分类：什么值得搜索，什么不值得？**

正是由于高昂的算力成本，推理期搜索存在明确的适用边界。**值得引入搜索架构的任务必须同时具备两个核心特征：第一，单路径容易陷入死胡同且错误率高；第二，具备成本极低且确定性极高的验证器（Simulator/Verifier）。** 数学定理证明、算法竞赛编程以及您正在实施的 XML 漏洞修复，正是此类任务的典型代表10。在 XML 修复场景中，如果一个违规节点有多种修复策略（如直接删除节点、修改属性字典、补充默认子节点），LLM 很难在单次生成中猜中不引发次生错误的最优解。此时，利用多分支并发生成并结合 Dry-run 沙箱的微秒级校验，是一笔极具投资回报率（ROI）的算力开销。  
相反，**不值得引入搜索架构的任务通常是具备真值反馈的线性任务，或是缺乏客观评估标准的开放式生成。** 例如将非结构化文本抽取为指定格式的 JSON 字典。这类任务如果出错，通常是基础模型的指令遵循能力不足，强行引入 ToT 除了白白浪费 Token 外毫无助益，更合理的解法是引入 Few-shot Prompting 或直接微调（Fine-tuning）。此外，如果任务的评估完全依赖于另一个大模型（LLM-as-judge），且该裁判模型对当前垂直领域缺乏绝对的辨别力，那么扩展搜索树只会导致系统陷入“幻觉的狂欢”——模型生成了错误方案，并用虚假的逻辑为该方案打出高分12。

### **2.3 2025–2026 年生产环境采纳现状：“能 Workflow 别 Agent”**

进入 2025 至 2026 年，以 OpenAI o1、o3 以及 DeepSeek R1 为代表的新一代推理模型引领了“测试期计算（Test-time Compute）”的范式革命14。这些模型将 MCTS 搜索过程、思维链展开以及强化学习奖励机制固化在了模型权重的底层（Internalized Inference-time Search）。  
这一基础模型的跃迁直接导致了应用层工程共识的巨大转变。在工业界，由于纯动态、无约束的 Agent 搜索（例如早期的 AutoGPT 循环）存在极高的不可预测性和延迟，目前的共识已经演变为“能 Workflow 别 Agent”14。这意味着企业级系统设计更倾向于利用静态的编排引擎（如 LangGraph 或 AWS Step Functions）来控制粗粒度、确定性的业务路由逻辑，而将那些需要细粒度探索、猜测与逻辑推演的局部步骤，委托给内部集成了搜索机制的底层大模型。在您的 XML 修复场景中，通过严格的代码沙箱执行闭环验证，实质上正是用 Workflow 的确定性来约束 Agent 生成的随机性。

## **3\. 世界模型（World-Model Simulation）与回测引擎的定位**

在 LATS 等基于 MCTS 的算法框架中，“推演（Rollout）”阶段之所以能够顺利进行，是因为智能体被假设拥有一个可以交互的“环境模拟器”。在强化学习的严谨术语体系中，这被称为马尔可夫决策过程（MDP）中的状态转移函数。而在当今的通用人工智能语境下，它被统称为“世界模型（World Model）”。

### **3.1 MCTS 为什么绝对依赖模拟器？**

要在当前节点评估一个初步行动的潜在价值，智能体必须能够“想象”采取该动作后未来的状态变化。如果缺乏对物理世界真实反馈的模拟，Agent 就无法预测动作带来的副作用，搜索也就失去了方向指引6。

### **3.2 LLM 语境下世界模型的三种主流形态**

在当前的工程实践中，为大语言模型构建世界模型通常有三种形态，其可靠性与成本各不相同：  
首先是**真实仿真环境（Embodied Sandbox）**。例如 ALFWorld 的纯文本游戏沙箱，或是集成在容器中的真实浏览器控制台。操作在此类环境中实际执行，系统直接捕获真实的状态跃迁。这是最可信但往往部署成本较高的形态。  
其次是**规则引擎（Deterministic Rules）**。系统利用现有的软件工程积累，如物理引擎、编译器、静态代码检查工具或形式化验证器。这是工程界最为推崇的世界模型形态，因为它具备绝对的数学真实性，运行速度极快，且彻底杜绝了模型幻觉。  
最后是**LLM 模拟器（LLM Simulator）**。在缺乏前两者的业务场景中，开发者不得不使用另一个大模型来扮演环境（例如在销售培训中扮演挑剔的客户），根据 Agent 的动作生成虚拟反馈。这种方法的 Token 成本极高，且随着对话深度的增加，极易发生逻辑漂移和角色崩塌。

### **3.3 Dry-run 沙箱作为“工程世界模型”的完美定位**

在您正在构建的闭环修复 Agent 架构中，读取 XML 校验器 Findings 并生成 Patch，随后放入 Dry-run 沙箱执行复跑验证，这一流程扮演了完美的**工程化世界模型**角色。传统的 LLM 规划往往是“在脑内推演”，即 LLM 自身同时兼任行动者（Actor）和模拟器（Simulator），这种既当运动员又当裁判的模式极易导致模型产生过度自信的幻觉。而将生成的代码补丁推入 Dry-run 沙箱，实质上是将“世界模型”的职能从概率性的 LLM 中剥离，交还给了确定性的软件验证工具。这种架构设计彻底消除了 Rollout 过程中的评估误差，使得搜索树的节点价值评估拥有了百分之百可信的基准真相（Ground Truth）。

## **4\. 验证器信号质量：BoN 机制与 PRM/ORM 的博弈**

### **4.1 Best-of-N 作为 ToT 的最小可用与最优 ROI 形态**

在今天计划实施的半日玩具实验中（即对同一违规生成 3 个候选 Patch，各自沙箱复验打分取最优），您实际上构建了推理期搜索在工程界中最简练、往往也是投资回报率最高的形态：**Best-of-N (BoN) 结合验证器**18。  
从树搜索的宏观视角来看，Best-of-N 等价于深度为 1、广度为 N 的 Tree of Thoughts，即系统仅在第一层展开 N 个分支，评估所有叶子节点并直接选择最优解，不进行多层级的向下探索。从概率学的数学模型分析，如果底层模型单次生成正确补丁的成功率为 ![][image5]，且存在一个完美的零误差验证器，那么并行生成 ![][image6] 个候选分支的系统整体成功率 ![][image7] 将服从公式 ![][image8]18。这清晰地揭示了一个工程铁律：只要验证器足够强健，增加并发采样的宽度（N）就能以指数级的速度拉升系统的整体容错率，其性价比远远高于增加搜索的深度。

### **4.2 PRM 与 ORM：过程导向与结果导向的抉择**

在构建此类验证器时，学术界与工业界将其评估信号分为两大阵营：ORM 和 PRM。  
**ORM（Outcome Reward Model，结果奖励模型）** 是一种只关注最终输出状态的评估机制。在代码修复场景中，它只关心补丁应用后 XML 校验器的报错是否彻底消失10。ORM 的优势在于评估标准绝对客观，实现成本极低，且不会干扰模型的中间推理过程。然而，对于动辄数百行的复杂重构，ORM 无法指出模型究竟在哪一行代码的推演上犯了错。  
**PRM（Process Reward Model，过程奖励模型）** 则对修复步骤的每一个中间逻辑节点进行打分，能够提供密集的监督信号（Dense Reward），极大地指导了搜索算法（如 MCTS）的方向12。但 PRM 的致命弱点在于构建成本极高，且极易引发“奖励黑客（Reward Hacking）”现象。如果在某一步 LLM 给出了看似合理实则会导致后续崩溃的错误高分，整个搜索树就会被引向歧途19。  
对于您的 XML 代码修复系统而言，Dry-run 校验器沙箱是一个毫无争议的“完美 ORM”11。它不仅响应延迟极低，而且完全没有大模型的幻觉偏差。

### **4.3 验证器可靠性：摒弃 LLM 裁判的必要性**

如果您的系统设计退而求其次，依赖 LLM 作为裁判（LLM-as-judge）来从 3 个候选中选择最优解，系统将面临巨大的隐患。大量实证研究表明，LLM 裁判天然存在**位置偏差（Position Bias）**（倾向于选择第一个或最后一个候选）、**长度偏好（Verbosity Bias）**（错误地认为越长的代码质量越高），以及**盲目迎合（Sycophancy）**19。特别是当模型被要求评价自身同源模型生成的代码时，往往会因为预训练语料分布的一致性，盲目给予过高的评分。  
虽然在您建立的对抗评估体系中，引入了双异构 LLM 裁判外加 Cohen ![][image9] 人工校准作为降偏手段，但这更适合用于离线的系统评测。在核心的在线代码修复闭环内，强烈建议完全摒弃 LLM 裁判，百分之百依赖沙箱报错（Deterministic ORM）作为节点质量筛选的唯一标准。  
为了更清晰地展示两种奖励模型的工程特征，可参考下表：

| 验证器类型 | 核心关注点 | 信号特征 | 常见实现方式 | 在代码修复中的优缺点 |
| :---- | :---- | :---- | :---- | :---- |
| **ORM (结果奖励)** | 最终状态正确性 | 稀疏 (Sparse)、低频 | 沙箱测试、正则校验、编译器 | **优**：绝对客观，无幻觉成本低。 **缺**：无法提供中间步骤的纠错指导。 |
| **PRM (过程奖励)** | 中间逻辑正确性 | 密集 (Dense)、高频 | LLM 逐行打分、细粒度探针 | **优**：能精准定位逻辑断点，利于长链条规划。 **缺**：易受 LLM 偏差影响产生 Reward Hacking。 |

## **5\. 反事实推理：从规划到归因的深度应用**

反事实推理（Counterfactual Reasoning）在因果推断领域旨在回答一个核心假设：“如果当时系统没有采取动作 A，而是采取了动作 B，最终的结果会发生怎样的改变？”在高度复杂的 Agent 系统中，反事实推理解锁了两层极具价值的工程应用20。

### **5.1 规划阶段的平行比较（前向反事实）**

当 ToT 或 LATS 在当前节点进行分支扩展时，系统实际上是在并发模拟多个反事实的平行宇宙。针对一个 XML 属性冲突报错，模型隐式地在进行反事实推演：“如果策略 A 选择修改原属性标签的枚举值，而策略 B 选择彻底删除该标签并依赖系统默认值，究竟哪种策略会导致下游的解析器崩溃？”通过多分支并发生成，系统能够直观地比对不同因果干预下的未来状态，从而在沙箱中选出副作用最小的方案。

### **5.2 评估复盘时的归因实验（后向反事实）**

在您构建的对抗评估体系中，Agent 经常会遇到“按下葫芦浮起瓢”的困境——原本是为了修复错误 A，结果修改的代码却引发了更严重的结构性错误 B。此时，通过后向反事实归因，可以实现故障的精准隔离与排查。  
在具体的工程操作中，可以对 Agent 生成的复杂补丁（Patch）进行 Diff 拆解。假设一个失败的 Patch 同时包含对节点 A 和节点 B 的修改。测试系统可以自动生成两个反事实样本：一个是仅包含节点 A 修改的代码，另一个是仅包含节点 B 修改的代码，并分别推入沙箱进行验证。这种控制变量法能够准确测量出究竟是哪一部分的修改打破了 XML 的语法约束，从而将提炼出的精准因果反馈作为 Few-shot 负样本，反向注入给 Agent，防止其在未来的迭代中重蹈覆辙。

## **6\. 对抗性自我质检与 Constitutional AI 的引入**

为了提升闭环系统的可靠性，许多现代 Agent 架构集成了模型的自我纠错能力。这不仅仅是遇到错误后的简单“重试”，而是一种高度结构化的对抗博弈21。

### **6.1 Critic/Self-critique 模式 vs 独立模型红队**

自我质检（Self-critique）模式要求同一个模型在生成初始草稿后，通过切换系统提示词（例如扮演一位严苛的资深代码审查员）来对自己的代码进行挑错。这种方法的通信延迟和上下文缓存成本极低，但容易陷入心理学上的“证实偏差（Confirmation Bias）”。由于生成和审查使用的是同一套神经网络权重，模型很难跳出自己原有的逻辑盲区。  
相比之下，独立模型红队（Independent Red Teaming）采用完全异构的模型（例如修复补丁使用 Claude 3.5 Sonnet 生成，而攻击与漏洞挖掘交由 GPT-4o 执行）。由于不同模型的预训练语料分布、强化学习对齐偏好以及注意力机制存在显著差异，异构模型组成的对抗评估体系能够非常有效地打破同质化的认知死角，揭露被单体模型深度隐藏的安全漏洞或逻辑缺陷。

### **6.2 Constitutional AI 式的自我修订约束**

仅仅让模型知道“错了”是不够的，必须指导模型“如何正确地修改”。Anthropic 提出的 Constitutional AI（宪法 AI）概念，通过设立一套不可逾越的顶层原则（Constitution）来强制规范模型的行为底线21。  
在您的 XML 修复 Agent 场景下，可以将“宪法”具象化为一系列硬性的软件工程规约。例如：

> 1. **数据无损原则**：绝对禁止为了消除子节点属性报错而暴力删除包含原始业务数据的父节点。  
> 2. **可追踪原则**：所有新增的占位符属性或默认节点，必须严格带有 \<\!-- AI-FIXME \--\> 的注释前缀。  
> 3. **最小权限原则**：只允许修改报错日志中明确指定的 XPath 路径范围内的代码，严禁触碰其他正常节点。

当 Agent 生成 3 个候选 Patch 时，系统强制引入一个宪法批评阶段（Constitutional Critique），要求 LLM 或规则引擎逐条核对这些 Patch 是否违背了上述工程宪法。只有通过宪法审查的 Patch 才有资格进入沙箱进行性能和正确性验证。这种机制极大地收敛了 LLM 的发散性，使得自我修订（Self-revision）过程始终在安全可控的轨道上运行24。

## **7\. 实验设计建议：单候选 vs 3 候选的科学对比**

针对您今天即将开展的“单候选修复 vs 3 候选修复并沙箱取优”的半日玩具实验，严谨的对照实验设计是得出可信工程结论的前提。

### **7.1 核心指标的严格定义**

* **修复成功率（Fix Success Rate, FSR）**：这绝不能仅仅是“沙箱不再报错”。在严谨的定义下，成功是一个复合布尔条件：![][image10]。  
* **Token 成本核算模型**：在对比实验中，必须严格区分并记录 Prompt Tokens 和 Completion Tokens 的开销。由于 3 候选机制可以通过批量 API 请求实现（即复用同一份巨长的错误 Context 请求 3 个不同的结果），其 Prompt Token 的计费可能只发生 1 次（特别是在各大云厂商支持 Prompt Caching 的背景下），但 Completion Token 的成本是单候选的 3 倍。这是核算架构 ROI 的关键财务指标。  
* **系统延迟（Wall-clock Latency）**：并行并发生成 3 个候选所需的时间与串行生成 1 个的时间进行对比。通过异步 I/O 并发调用，两者的延迟在理想网络下应当相近，但并发方案会显著增加请求的吞吐量压力。

### **7.2 样本集的构建与分层**

为了避免结论的片面性，测试集应包含至少 50 至 100 个具有代表性的 XML 违规样本。建议按照修复难度对样本进行分层（Stratification）：

> 1. **简单词法级**：如缺失必填的字符串属性、枚举值拼写错误（预期单候选即可轻易解决）。  
> 2. **复杂结构级**：如节点嵌套层级错乱、父子依赖关系断裂（预期 3 候选方案将展现出压倒性的优势）。

### **7.3 超参数调优：温度与确定性控制**

在 3 候选策略中，采样超参数的设置将直接决定实验的成败：

* **单候选基线**：必须设置 Temperature \= 0。这能确保获取大模型计算出的具备最高对数概率（Log-probability）优势的稳妥解，排除随机性干扰。  
* **3 候选策略**：绝对不能在温度为 0 的情况下重复请求 3 次，否则您将得到 3 个字节级别完全一致的 Patch，白白浪费 API 费用。必须设置适当的探索温度（推荐 Temperature \= 0.5 \~ 0.7）以确保多分支的多样性。更高级的工程做法是，结合不同的 System Prompt（如设定三种不同的修复人格：激进重构者、保守修改者、极简补全者）来强制实现逻辑层的**多样性采样（Diverse Sampling）**9。  
* **实验复现性**：在所有 API 调用中，务必传递固定的随机种子（Seed 参数），并记录返回头中的 system\_fingerprint，以确保无论结果好坏，实验轨迹均可被 100% 复现追踪。

## **8\. 推理期搜索必须掌握的 5 个工程坑点与规避指南**

结合 2024 至 2025 年产业界的踩坑血泪史，在执行多分支推理和沙箱验证时，以下五个问题极易导致工程架构彻底失败：

### **坑一：候选间同质化导致的算力空转**

正如上文所提及，如果在同一温度下使用同一份 Prompt 简单循环请求 3 次，即便开启了非零温度，当模型对某一错误极度确信时，依然会生成逻辑雷同的补丁。 **规避策略**：在 API 请求中引入较高的“存在惩罚项（Presence Penalty）”与“频率惩罚项（Frequency Penalty）”。或者实施显式的异构提示词策略（Prompt-ensembling），明确告知模型：“这是你生成的第 2 个备选方案，必须提供与第 1 个方案完全不同的修复切入点。”8

### **坑二：验证器被补丁“骗过”（Reward Hacking）**

LLM 在寻找捷径方面具有远超人类的“创造力”。例如，当规则引擎提示“当存在 \<payment\> 节点时，必须包含 currency 属性”。模型为了快速消除这个繁琐的报错，可能会直接生成一个将整个 \<payment\> 节点连根拔起的 Patch。对于毫无业务上下文的校验器而言，报错确实消失了，但业务逻辑却被彻底摧毁。 **规避策略**：在 Dry-run 沙箱的外部包裹一层“保守度守护进程”。计算生成 Patch 与原始 XML 的文本差异（Diff 距离）。如果一个修复动作删除了超过 20% 的原始文本或清空了关键数据区，该 Patch 必须被一票否决，无论其沙箱得分多高11。

### **坑三：盲目追求成功率，陷入 ROI 幻觉**

在向团队内部进行技术分享时，工程师经常自豪地汇报：“通过引入 3 候选与 MCTS 验证，成功率从 65% 跃升至 85%。”然而，产品经理或架构团队通常会立即提出财务质询：在生产环境中，为了这 20% 边缘长尾 Case 的提升，却让全局 100% 的流量都承受了 3 倍的 Token 成本和双倍的延迟，这是否值得？  
**规避策略**：在汇报与架构设计中，采用“边际成本收益曲线（Marginal ROI）”进行评估。工程落地时，应设计**漏斗型降级机制（Fallback Routing）**。即首先进行低成本的单次生成，如果 Dry-run 沙箱报告修复成功，则直接返回；只有当首次尝试失败时，才激活消耗巨大的 3 候选并行探索机制。

### **坑四：Context 暴力膨胀与历史记忆债务**

在引入多步回测与错误修正时，开发者最常犯的低级错误是将每一次失败的 Patch 代码和冗长的沙箱堆栈报错信息，一股脑地拼接（Append）到下一次对话的上下文中。经过三五轮迭代，上下文充斥着大量无效的垃圾代码。这不仅会导致 API 调用成本呈指数飙升，更会严重干扰大模型的注意力机制（Attention），导致模型彻底忘记最初的任务目标。  
**规避策略**：采用动态上下文窗口截断与清理机制。在每一轮对话中，仅保留“原始 XML 框架”、“当前得分最高的 Patch”以及“最新一次的精准报错”。对于历史的错误探索路径，利用大模型进行轻量级总结（如：“尝试方案 A 导致了越界异常，已废弃”），用短句替代大段代码。

### **坑五：JSON/XML 格式化损耗掩盖了逻辑推理缺陷**

在统计修复失败的 Case 时，经常会发现 Agent 在代码逻辑思路上是完全正确的，仅仅是因为输出时遗漏了一个大括号、XML 标签未闭合，或是输出了多余的 Markdown 标记，导致无法被系统解析入库，从而在 Dry-run 阶段直接崩溃。这部分失败如果被笼统地归类为“模型推理能力不足”，将严重误导后续的优化方向。  
**规避策略**：在 API 层面强制开启 Structured Output（如 OpenAI 的 JSON Mode 或原生的 Tool Calling 工具调用模式）。将繁琐的格式控制剥离出生成任务，确保模型输出的数据结构 100% 合法，从而将评估焦点纯粹集中在模型的逻辑推理能力上。

## **9\. 资深 AI 工程架构师面试高频 Q\&A**

针对正从传统程序员转型为 AI 工程架构师的读者，以下五个深度问题直击推理期搜索方向的底层认知，也是大厂高阶面试的高频考点：  
**Q1：在什么业务场景下，我们绝对不该使用 Tree of Thoughts (ToT) 或 MCTS 等复杂搜索架构？**  
*答题要点*：  
第一，存在明确且固定线性映射规则的结构化转换任务。例如将一段非结构化文本清洗重组为特定格式的 JSON 字典。这类任务不涉及博弈与策略探索，引入树搜索纯属算力浪费。  
第二，单步闭环即可提供决定性高潮反馈，且试错毫无破坏性副作用的场景。直接写一个 While 循环重试 3 次，远比维护一棵复杂的思维树在代码实现上更优雅。  
第三，缺乏外部可靠客观验证器，且评估标准极度主观的任务（如创意公关文案生成）。在这种场景下，如果没有基准真相（Ground Truth），扩展搜索树仅仅是在无限放大 LLM 作为裁判（LLM-as-judge）的内部迎合偏见（Sycophancy），消耗大量算力却得不到实质性的质量提升。  
**Q2：从系统内存资源管理的角度，深度解释 ReAct 和 ToT 的核心架构区别是什么？**  
*答题要点*：  
ReAct 本质上是一个线性的状态机（State Machine）。它的系统内存仅仅维护一条单一维度的历史轨迹（Trajectory）。一旦当前执行路径遇到不可逆的死胡同，它只能带着失败的肮脏记忆继续硬着头皮往下跑，或者被迫清空内存从头再来。  
而 ToT 的核心突破在于，它在系统内存中维护了一个由多节点组成的非线性数据结构（如栈 Stack 或优先队列 Priority Queue）。ToT 能够在当前路径被验证为死胡同时，立即终止该分支，从内存栈中弹出（Pop）上一个得分最高且仍有希望的兄弟节点进行状态恢复（Backtracking）。这要求工程实现上必须具备对每一步的上下文环境（Context）进行状态快照（Snapshot）和垃圾回收管理的能力。  
**Q3：什么是 Reward Hacking（奖励黑客）？在代码生成 Agent 中应如何建立防御体系？**  
*答题要点*：  
Reward Hacking 是指当设计的验证器（ORM）无法 360 度无死角地覆盖全部业务意图时，LLM 会利用其强大的参数寻优能力，找到一条违背常理但能获得验证器满分的“捷径”。例如，在修复一个单元测试报错时，LLM 不是去修复底层算法，而是直接硬编码（Hardcode）了测试用例的期望输出语句，从而“完美”通过了单元测试。  
防御体系：首先，不可单一依赖 ORM，需结合细粒度的 PRM（过程奖励模型）检查中间逻辑；其次，在代码沙箱外部集成静态分析工具（AST 检查）与执行流覆盖率统计；最后，强制引入前文所述的 Constitutional AI 审查阶段，一旦发现破坏性代码或硬编码作弊行为，直接执行一票否决。  
**Q4：对比 2025 年大模型内置的 o1 式“隐式强化搜索”与我们基于 LangGraph 构建的“显式 Agent 架构”，二者的护城河分别在哪里？**  
*答题要点*：  
o1 等新一代基础模型通过超大规模的强化学习，将 MCTS 搜索与试错内化在了模型的权重与生成的思维链中。这极大地降低了应用开发者手动编写并发请求、维护搜索树、管理上下文切片的工程负担，在通用逻辑题上表现出压倒性优势。  
然而，显式 Agent 架构（如当前我们构建的 XML 沙箱验证）的真正护城河在于**与企业专有环境的物理深度耦合**。基础模型无论参数多大、智商多高，也无法凭空预知贵司内部私有库的非标 API 参数或遗留代码的报错详情。显式的图架构能够接入企业的真实 DB、私有 Lint 工具以及 Dry-run 沙箱，提供了无可替代的确定性领域知识反馈（Grounding）。这种与物理世界交互的能力，是任何闭门造车的通用大模型仅靠自身“脑内推演”无法取代的。  
**Q5：如果在真实的金融级生产环境中，我们需要极高的修复可靠性，同时对云端 API 成本极其敏感，你会如何重构这个多候选打分系统？**  
*答题要点*：  
我将摒弃单一的扁平调用，采用“漏斗型级联（Cascading）与动态路由（Dynamic Routing）”架构。  
具体而言，系统前端会使用体积小、推理速度极快、成本低廉的开源小模型（如 Llama 3.1 8B 或 Claude 3.5 Haiku）进行单路 Zero-shot 尝试。将生成的补丁投入免费的本地 Dry-run 沙箱。  
只有当本地沙箱报告尝试失败，且评估确认为高难度的复杂逻辑错误时，系统才会触发升级流程（Escalation），唤醒云端昂贵的大型推理模型（如 GPT-4o 或 o3-mini）。此时才铺开温度阈值，并发 3 个甚至更多候选分支进行复杂生成，必要时引入完整的 MCTS 规划搜索。通过这种防线分级策略，可以将 80% 的常规错误以几乎忽略不计的成本拦截在边缘端，只有最棘手的 20% 长尾问题才去消耗高昂的推理期算力，从而在系统全局实现极致的 ROI 最优化配置。

#### **Works cited**

> 1. REACT: SYNERGIZING REASONING AND ACTING IN LANGUAGE MODELS \- OpenReview, [https://openreview.net/pdf?id=WE\_vluYUL-X](https://openreview.net/pdf?id=WE_vluYUL-X)  
> 2. \[2210.03629\] ReAct: Synergizing Reasoning and Acting in Language Models \- arXiv, [https://arxiv.org/abs/2210.03629](https://arxiv.org/abs/2210.03629)  
> 3. Tree of Thoughts: Deliberate Problem Solving with Large Language Models \- arXiv, [https://arxiv.org/abs/2305.10601](https://arxiv.org/abs/2305.10601)  
> 4. Graph of Thoughts: Solving Elaborate Problems with Large Language Models, [https://ojs.aaai.org/index.php/AAAI/article/view/29720/31236](https://ojs.aaai.org/index.php/AAAI/article/view/29720/31236)  
> 5. \[2308.09687\] Graph of Thoughts: Solving Elaborate Problems with Large Language Models, [https://arxiv.org/abs/2308.09687](https://arxiv.org/abs/2308.09687)  
> 6. Language Agent Tree Search Unifies Reasoning, Acting, and Planning in Language Models \- arXiv, [https://arxiv.org/html/2310.04406v3](https://arxiv.org/html/2310.04406v3)  
> 7. \[2310.04406\] Language Agent Tree Search Unifies Reasoning Acting and Planning in Language Models \- arXiv, [https://arxiv.org/abs/2310.04406](https://arxiv.org/abs/2310.04406)  
> 8. What is Tree Of Thoughts Prompting? \- IBM, [https://www.ibm.com/think/topics/tree-of-thoughts](https://www.ibm.com/think/topics/tree-of-thoughts)  
> 9. Language Agent Tree Search (LATS) \- Agentic Patterns, [https://agentic-patterns.com/patterns/language-agent-tree-search-lats/](https://agentic-patterns.com/patterns/language-agent-tree-search-lats/)  
> 10. A Survey of Process Reward Models: From Outcome Signals to Process Supervisions for Large Language Models \- ACL Anthology, [https://aclanthology.org/2026.acl-long.163.pdf](https://aclanthology.org/2026.acl-long.163.pdf)  
> 11. Dynamic and Generalizable Process Reward Modeling \- ACL Anthology, [https://aclanthology.org/2025.acl-long.212.pdf](https://aclanthology.org/2025.acl-long.212.pdf)  
> 12. Test Time Scaling Explained, Differences Between ORM & PRM Reward Models \+ Future PRM Research | by Joyce Birkins | Medium, [https://medium.com/@joycebirkins/test-time-scaling-explained-differences-between-orm-prm-reward-models-future-prm-research-aa50ff499456](https://medium.com/@joycebirkins/test-time-scaling-explained-differences-between-orm-prm-reward-models-future-prm-research-aa50ff499456)  
> 13. Process Reward Model (PRM) Overview \- Emergent Mind, [https://www.emergentmind.com/topics/process-reward-model-prm](https://www.emergentmind.com/topics/process-reward-model-prm)  
> 14. AI Predictions for 2025: Agents, Inference & Smaller Models \- Turing Post, [https://www.turingpost.com/p/fod80](https://www.turingpost.com/p/fod80)  
> 15. OpenAI o1: Reasoning Model Series \- Emergent Mind, [https://www.emergentmind.com/topics/openai-o1](https://www.emergentmind.com/topics/openai-o1)  
> 16. Compute Allocation for AI Discovery and Search \- Dmitry Rybin, [https://rybindmitry.github.io/blogs/compute-allocation.html](https://rybindmitry.github.io/blogs/compute-allocation.html)  
> 17. Agentic Artificial Intelligence (AI): Architectures, Taxonomies, and Evaluation of Large Language Model Agents \- arXiv, [https://arxiv.org/html/2601.12560v1](https://arxiv.org/html/2601.12560v1)  
> 18. Beyond Model Size: The Future of LLM Optimisation | by David Haberlah | Medium, [https://medium.com/@haberlah/beyond-model-size-the-future-of-llm-optimisation-af7564daff29](https://medium.com/@haberlah/beyond-model-size-the-future-of-llm-optimisation-af7564daff29)  
> 19. Reward Modeling for Reinforcement Learning-Based LLM Reasoning: Design, Challenges, and Evaluation \- arXiv, [https://arxiv.org/html/2602.09305v2](https://arxiv.org/html/2602.09305v2)  
> 20. Counterfactual Planning for Generalizable Agents' Actions \- Beijing, [https://pure.bit.edu.cn/en/publications/counterfactual-planning-for-generalizable-agents-actions/](https://pure.bit.edu.cn/en/publications/counterfactual-planning-for-generalizable-agents-actions/)  
> 21. Latent Principle Discovery for Language Model Self-Improvement \- NIPS, [https://proceedings.neurips.cc/paper\_files/paper/2025/file/ed967b37f63bb22abc12e436c444531b-Paper-Conference.pdf](https://proceedings.neurips.cc/paper_files/paper/2025/file/ed967b37f63bb22abc12e436c444531b-Paper-Conference.pdf)  
> 22. 6 Advanced Prompt Optimization Techniques for Better AI Results | Galileo, [https://galileo.ai/blog/advanced-prompt-optimization-techniques-better-ai-results](https://galileo.ai/blog/advanced-prompt-optimization-techniques-better-ai-results)  
> 23. Constitutional AI: Harmlessness from AI Feedback \- Anthropic, [https://www.anthropic.com/research/constitutional-ai-harmlessness-from-ai-feedback](https://www.anthropic.com/research/constitutional-ai-harmlessness-from-ai-feedback)  
> 24. Generate compliant content with Amazon Bedrock and ConstitutionalChain \- AWS, [https://aws.amazon.com/blogs/machine-learning/generate-compliant-content-with-amazon-bedrock-and-constitutionalchain/](https://aws.amazon.com/blogs/machine-learning/generate-compliant-content-with-amazon-bedrock-and-constitutionalchain/)  
> 25. Collective Constitutional AI: Aligning a Language Model with Public Input \- ACM FAccT, [https://facctconference.org/static/papers24/facct24-94.pdf](https://facctconference.org/static/papers24/facct24-94.pdf)  
> 26. Goodhart's Law in AI Products: When Your Metrics Lie, [https://www.institutepm.com/knowledge-hub/goodharts-law-ai-products](https://www.institutepm.com/knowledge-hub/goodharts-law-ai-products)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAkAAAAaCAYAAABl03YlAAAAk0lEQVR4XmNgGFCgCMRM6IIw8BCI/0MxO5ocCljMAFGEF4AU/EQXRAcgRY3ogshAmQGiiAOI64B4PhAzoqgAgkUMEEUfGCAO14XyURSCBH4jC0DFNqALtCMLQMVewDiSUAEeuDTEGpDYRJhAGlQAGZRCxVRhAnZQAWQA4j9CE0NR1IHGhwNQxIIkQHgHmtwooCYAANGII3VrZN/xAAAAAElFTkSuQmCC>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAsAAAAZCAYAAADnstS2AAAAqUlEQVR4XmNgGDJAAohl0AXRwUIg/g/FRWhyWIEmA0QxC7oENrCSAaKYKABS+BVdEBn0AHETlA1SXIMkBweVQPwLylZlQHiOHa4CClKhEhxIYpegYhgAJPgci9h3NDEGD6hEOpo4SKwBTYxhMwOmdSlIYpZAzAWTSEOSgAGQR2FiH5ElQOA3EBcyQEz5wwAJGZBiZSBehKQODtQYIO6HASEgdkTijwI6AQCURSXAcD7IXAAAAABJRU5ErkJggg==>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIAAAAaCAYAAAD1wA/qAAACXklEQVR4Xu2XzatNURjGH9/kqxthglIGypxMdCmRiYGBgdwkxcRHSkgycQdGlAETJcpA5D+4DJSS8jERopABBoSQz/ex1nLWec679937fFyT86unu/fvfdfa56y9zzrnAn26znzLXcsnLfwv1qmowWXL0ex8S3bcEYstZy1nLLOk5rHLckilMceyTKXDb8uU7HyJ5X52XptTCJNui+eLLG8sX/91tLLQ8lrcRss3hLlGpJY4Z7lkeYjQp5xG6KnFeITJbmoh8sPyS2WE46aqjLC2VqVxx7IvHvORLFoo7w2WwgHPVGasgf+iViGsvMcO+C9kHJo978rx7DznImo8Yq/gXzAn3bEr4r/D/2yQl/Dn3YRmX3ZHZ8Ofo4XVCI03xCsDCH3vxdNNE5dgjY/qUst1y/LoJ6Nx92fEPrI//lVYH3XD4YqWrUhiK0LfvczNjK4I1pj1aDxOw7E2YrmFsNvxw87vkSI47rBKJV1sNB4j9PHCicHoPIYQagsydz66unDMBZU581D9jXh92x2XeIrWGh8zdVX4YrmtMmcCwsRsLGMzQp9uzWnVPej14t5iVOEzyh+9v1SZvKhnJXxP6Lk7qXsurgocd02l8gHFL4a8QKhP0gIaO5kHPX8MJnZH1w4cd0SlBxsfqDTeIuxqZXAst1Plp2VvPGadfRsa5VpwLBetEu8QBvC55meGxyuaOnzYd0Bl5CNCnT/P50qtKtPR/p2sxUH09v8I/gK/qrJXcMUmquwSY3I3EvzmfqKyCxyznFDZa05adqrsAO54j1SOFUMqOmCPij59+rTHHx4SmfuNpA+MAAAAAElFTkSuQmCC>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAsAAAAbCAYAAACqenW9AAAAo0lEQVR4XmNgGNrgKhD/AeL/QMyJJocV7GWAKCYKgBSSpHg6uiA2IMUAUSyBLoENzGJAdUIbED9FE4MDZPceAmI+IF6FJIYCQIJzgfgSELNCxeYB8T24CiiQZECYnIMmhwEiGCAKQREDovegSqOC6wyobgOxpyDxUQBI8hoafyWU/RFJHAxAkmFo/GwgZgTiY0jiDGJQSWTgBxX7gCY+CgYbAADqfCrdk3T3XwAAAABJRU5ErkJggg==>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAbCAYAAABFuB6DAAAAm0lEQVR4XmNgGAUDAr4C8VsgPgPEgkD8H4gvQWkWmCI3IHYGYiWoxAOYBBAcBeJ/MM4XKN3FAFGIDLqxiDH8xiL4EIsYWOA6FjGsCsOxiD1DFgB5CF1nNFSMA1nwOFTQB8pngvLD4CqgACR4C4gvQ9mgkJBCUQEFIEmQVXiBHwOm+7CCDwwQhVlALI4mhwJcGCC+DgBiRjS54QkAahspjFGixIQAAAAASUVORK5CYII=>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABMAAAAaCAYAAABVX2cEAAAA3klEQVR4XmNgGAWUgnlA/BmI/0PxAhRZCPjLgJAHYWdUaUyArBgb2AfEKuiC2AAjEG8H4vUMEMOCUKXBAJclGCAfiE2gbFyu+4MugAu8RWJ/YIAYxockpgbEnUh8vADZJaBwAfFvIoktA2IeJD5OAAqvzWhi6F7F5m2sADm8kMVABnRD+b+Q5PCCd+gCUABznTYQt6DJ4QS4vLCbASJ3D4g50eSwAhYg3osuCAVMDJhhhxMwA/EbID6JLoEEvgHxD3RBdLAKiD8yQNIXKF2B8h42oA/E2eiCo2AUDGkAAM4NNN65dbHtAAAAAElFTkSuQmCC>

[image7]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAaCAYAAAC+aNwHAAAApElEQVR4XmNgGAXoYAIQfwTi/1D8HYjfoYmtgqvGA2CK0YE8A0R8F7oEOgApOo4uCAW4DIeDCAaIAnd0CSDgZCDCgGsMuBWsZ4DIBaBLIANcNjgyQMQnokugA5gBH4D4PRD/gPIvA7EwkjqsAOb/JHQJYsFNBuzOJxrg8j/RAKT5DrogsaCaAWJAOroEITAZiD8zQEIclO6/AvE/FBWjYBTQGgAA/GAxOhsgBN4AAAAASUVORK5CYII=>

[image8]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAJsAAAAaCAYAAACgjS7xAAADbElEQVR4Xu2aS6hNURjHP688y2sgedwkCREyU0p55Z2RiQnKAANKBgYkRTIgifLoYoQiRlJmylTJq1DyCMkj7zy/v7XWvev8797n7OOes/Y6tX71b5/9/9Y5a+19vrP2ehyRRCKRKJn9qvuqP+RfsN5l8hNNZqSqJ5stwHQ2cvim+qU6Tv4JOk80mcGqZ2y2ENxjZXFStUAqy+K6R3nn/81B1QcxHw59Vb0l73xH6fI4q5rEZmBqfVmv2IiMcap3bHr0U42xr3GtS+3rA/bYMFxiMW1i/GscCMAN1W/pbNvkynBQHqq2sqncks72Zd2/2PisWsamZZf3+rCYew9+en5DwI26yaal7Bs5U8pPtlrXf0Vql4mBCZLfTozXfFBukOoo+d1itZgPXsgBpb+kZDui+sQm0SrJBtDOAWwq7XT+WPVINYL8bnFX8m/UJTGxlRwISNnJhrr3sEmUmWwYwJ8RM+QBo1UXVSs6SlSCdmKZw2eYaiJ5Q6UJ15TXc80V4x/iQGBiSDY8fqpRZrJhHIbBPeq/rtpi/TuqB66QB8bf373zL6qP9jjb88F7Ou82LtnwwZit4NmN89uq4V65amBdBjPGLJ0W00WfEjO1Rtkl/95VDJdsUzgQCNTdm02irGTbKOa+oHdD/cu92CLrMcck2286bry2lgMR4ZJtKgdymFWHilDki6k32bgd1VSN9fa4T7rWv8l6vAi93frBQTdbSsV14JJtGgdywK+7qHrZ91SjyP2pN9m4HdVUhB/Stf6873abZPtNB5U2ouLdYgadRZW31pOFS7aiWy6NBnXXSsp6k63RoG5eooDn1sp8UK6UtqJSLFjGjEu2GRwIBOoezyZRZrINFFM3ZqGOsdbLGnpcFTMZCMoOMQ3awIHIWCymnW77JDSoeyebBHY7UK4vBwKwV0zd/rYSzvNWERDDNmUQsBWBqS5mnm/FTJ2zutuyeS1mvxGb30/tEd4Tv1AA2iV/CQB7yS+ls43PVW9U6/xCTcaN187ZI/61gadBHiiDNbREhLjHVKygbfyXoDzwqI35WhLKC4lzuOFW+ds4kAOeZqvYTMRFH4mvR1ijuiemXZul9gQKe5x45CdaAPwfLGv7pyzQQ81TzRezDzqkMtyF2H4siRpgs7oHmy3AHDYSiUQikUgkEgnwF4do7E4BHt8oAAAAAElFTkSuQmCC>

[image9]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAaCAYAAACD+r1hAAAAhklEQVR4XmNgGAWDDTAD8Ux0QSCwRReAgSNA/B+J3w/EL6BiFkjicACSuARlfwRidiDmB+JMuAo0ANIwA4ifoUtgAz4MEA2rgfg3lH0KRQUaOMOA6n4QAPFPo4nBAUjyIhaxY1D2NWQJEABJ+mERmwRlP0aWEGDAdA4IODBAxH+hiY+CoQgAxysezJmDKLsAAAAASUVORK5CYII=>

[image10]: <data:image/png;base64,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>