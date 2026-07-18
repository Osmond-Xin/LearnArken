# Day N Learning Journal — <date>

> Human-written; AI does not ghostwrite. (INV-6) Three fixed questions — each
> answer must contain at least one concrete instance. No platitudes.

## 1. What did I learn today?

- 如何给招聘方的AI展示，确实是我曾经没有想过的一个问题。而今天完整地补足了这条流程。我应该考虑到，在招聘的环节中，越来越多的人给予对方自己的项目，而这些项目必须得是AI友好，并且能够让AI迅速地浮现出来，从而体现出你对于AI first的理解和实践。所以这个是今天最主要的一个收获。
- AI确实是比较倾向于缓解，而不是刨根究底地解决问题，这个一定要多加坚持否则就很容易被AI带偏。

## 2. Where was the AI wrong, and how did I find out?

- 自动红队闸(Codex,独立模型) 抓出我实现里的真缺陷:
    - P1 路径爆炸 —— 我用 REFS*1..N 变长路径 + min(length(p)),会枚举全部 trail,稠密/环图会 DoS。我当时以为"Neo4j trail 语义天然安全"就够了,只想到深度没想到广度。
    - P1 证据守卫形同虚设 —— 我只 pin 了 6 个数字,却让 EVIDENCE.md 宣称"任意数字可核查";其余能悄悄漂移测试还绿。
    - P2 死链守卫自身有 INV-1 洞 —— 我写的守卫本意是保护"证据链诚实",却没查"链接是否在 repo 内",../resume-master/… 会通过。我写的安全闸自己漏了它要防的那类东西。
- 还有 malformed 响应不 fail-closed、exists 混淆索引/悬挂节点、target 未消毒等。
我自己的测试 抓出两个我自己的错:depth=1 的期望值写反了(以为 {A,B} 实际只有 {A});bakeoff JSON 的 overall 嵌套层我漏了。
## 3. What AI proposal did I reject, and why?

我在红队 Part 1 的"建议处置"里,主张把 #2 的完整修法(全量数字守卫)推到 Day 10,拿 INV-8 当借口只做个小的。你一句"红队标记的全部修改"直接否掉了。

结果:完整修法(未注册数字守卫)其实很干净、工作量不大。我低估了它、高估了推迟的合理性。 这是我一个反复出现的倾向:一遇到"红队说要改",就下意识援引 INV-8 想缩范围/拖延,哪怕全修很便宜。



## Today's numbers (if any)

10分满分，今天能够达到7.5。