# Day 8 Learning Journal 

> Human-written; AI does not ghostwrite. (INV-6) Three fixed questions — each
> answer must contain at least one concrete instance. No platitudes.

## 1. What did I learn today?

今天的开发让我意识到，即使是一个主要交由AI，类似于一句话需求的这种对抗性的需求，也需要明确的给予边界、预期、输入输出等具体的参数和信息，并且在后续需要花费大量的时间来去理解和掌握AI到底干了什么，不能让AI的内容托管，这部分现在确实是挑战。


## 2. Where was the AI wrong, and how did I find out?

诚实讲:这个 session 里没有一处是你当场指出我代码错的——你主要在做决策和给方向。我的错是被流程抓的,这恰好验证了多智能体对抗的设计:

评估器自身有 bug(我自己复测抓的):behavior_pass 用朴素子串匹配,把「25 Nm,不是 30 Nm」这种纠正误判成「肯定了 30」——凭空造了一批假缺陷,差点写进 README。
README 数字误导(诚实复测抓的):早期报的「0.917→0.979」是松 scorer + N=3 噪声。收紧后整体率其实持平(0.94→0.93),真正站得住的只是 X-01 缺陷被确定性消除。
红队(Codex)抓了 13 条我的代码洞,含 4 个 P1(裁判聚合 fail-open、提示词回显可被当裁决、裁判没做聚光灯防注入、我写的 README 违反 INV-5 可复现)。
你预防性立的规矩反而挡住了我更多潜在错误:开题就压「绝不在旧分支上开发」「别只报 judge 数字(要 κ 校准)」「不要自认为修复完成(要复跑红队)」——这三条各自对应 Day 7 的坑。


## 3. What AI proposal did I reject, and why?

- 从 judge 建议用 Codex 或 agy(单裁判,避开 Claude) 改成 Codex + Gemini 双裁判,并要求报分歧 因为多一个异构的LLM会多一个角度
- 从 分歧行用交集 + 人工兜底 改成 去掉人工兜底,纯交集,「交集后你可以判断」 因为需要尽量自动化

## Things worth remembering and sharing

- 评估非确定生成器要重复测,报稳健缺陷、不报噪声均值。MiniMax temp=0 仍非确定;N=3 下整体率是噪声,X-01「3/3→0/3」才是证据。
- 评估器自身也要被评估(evaluate the evaluator):一个子串 bug 就能造假缺陷、污染前后对比。
- 诚实数字优先于好看数字(INV-7):我主动推翻了自己写的 0.917→0.979。
- LLM-as-judge 的工程纪律:裁判 error 要 fail-closed、裁判输入要聚光灯防注入、严格解析防提示词回显、加 nonce;异构(Codex/agy)+ 人工 κ 锚定才是信任来源。
- gemini CLI 已死(IneligibleTierError)→ agy(Antigravity)才是 Gemini 通道。

## Today's numbers (if any)

10分满分得6分。