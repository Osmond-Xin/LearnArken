# Day 13 Learning Journal

> Human-written; AI does not ghostwrite. (INV-6) Three fixed questions — each
> answer must contain at least one concrete instance. No platitudes.

## 1. What did I learn today?

- 当前这个项目其实由于规模的话，无法承载一些真实项目的技术，比如说多线程等。但是为了演示还是要强行使用。在这种情况下需要加以说明。

## 2. Where was the AI wrong, and how did I find out?

- P1  默认的串行 runner 是 fail-fast——一个候选抛错炸掉整个 ToT 跑  
AI把并发 runner 仔细做成逐候选捕异常 fail-closed,却把朴素的默认路径留成 fail-open。加固花哨的、漏了默认的。
- P1  高危 dry-run-only 候选降级后仍可被选为 apply-ready  
AI只按自己那个消费者(eval)推理——"eval 会按 tier 区分,没事"——就 dismiss 了。漏了 tot_repair 作为通用 API,别的调用方会把 selected≠None 当可应用。
- P2  reward-hack veto 读不到源文件时 return 0.0(不 veto) 
一个 fail-closed 闸,自己的错误路径 fail-open。

## 3. What AI proposal did I reject, and why?

- AI总是希望以一些非业务上的管理的借口来屏蔽掉他应该干的活，但是实际上他并没有遵守最高级的规范。比如说这个规范，比如说这个项目整个都围绕是file close，那么但是他并没有意识到，一旦出现影响到这个最关键的指标的情况，就必修的。所以他总是倾向于这不是当天的活，或者是这不是当天的范围，来回避掉他应该做的事情。

## Today's numbers (if any)

- 十分满分打六分。