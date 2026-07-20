# Day 11 Learning Journal

> Human-written; AI does not ghostwrite. (INV-6) Three fixed questions — each
> answer must contain at least one concrete instance. No platitudes.

## 1. What did I learn today?

- 永远有深挖的细节。如果感觉到哪里其实不对，哪里应该有再继续一步的，一定要探索。今天的东西其实我之前就有感受到应该是有的，但是没有去继续探索。追问之后才发现是有成熟技术解决方案的。

## 2. Where was the AI wrong, and how did I find out?

- 图谱 sync 只做 MERGE 从不删除——重新索引变化过的语料后，旧边/旧节点会留在 Neo4j 里继续被检索路径读到。这是"镜像外部状态的 sync 函数忘记处理删除"这一类通用坑。
- 图扩展只对"发现节点数"设了上限，没对"种子实体数"设限——下游有界不等于入口被堵住，堵了出口没堵入口的老漏洞。
- 拒答回归闸自己没继承主流程已有的 fail-closed 纪律（Neo4j 挂了照样跑）——评估脚本/辅助工具容易被降低标准对待，这个疏漏值得记：辅助工具跟主链路要用同一套纪律。
- 两条 P2（trace 被覆盖丢溯源信息、RRF 去重丢图路元数据）是我自己独立复核抓到的，Codex 没找到——说明跨主机评审流程里"host 自己也要独立走一遍清单"这步是有真实价值的，不是走过场。
## 3. What AI proposal did I reject, and why?

严重度自我设限：红队 11 条发现里 P1/P2 我这次主动全修了，但两条 P3（词表缓存、拒答闸缺测试）我自己标了"无需处理"/"残留缺口"——本质是我下意识按严重度给自己划了条"低危可以不修"的线。这跟 Day 9 你已经立的规矩（"红队标记的全部修改"）冲突，你这次说"所有的红队发现的问题都修改"，等于再次否掉我的自我设限，而且这次连 P3 都不放过。跟 Day 9 是同一个老毛病的新变种——上次是想拖到明天，这次是想按严重度筛掉几条，本质都是我在你没要求的地方主动收窄范围。

## Today's numbers (if any)

满分10分的7分。