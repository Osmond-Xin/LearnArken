# Day 12 Learning Journal

> Human-written; AI does not ghostwrite. (INV-6) Three fixed questions — each
> answer must contain at least one concrete instance. No platitudes.

## 1. What did I learn today?

- 越是小的内容越要聚焦，而且实际上现在我意识到关于视频的也没有去做，所以在多媒体上只是做了图片，甚至GIF图等易构的也没有做，所以在真实的场景里会比我这个项目要复杂无数倍。但也恰恰是这种复杂性才能诞生市场。


## 2. Where was the AI wrong, and how did I find out?

- 红队的对抗是必须的，甚至应该考虑多重红队对抗，即不是一个红队，有多个红队来同时找错。

## 3. What AI proposal did I reject, and why?

- 二次看图：单次读不可信 → 多采样共识 + 锚点互验，不收敛就 fail-closed 拒答。
可复用点：任何"从不可靠模型读信息并据此行动"的场景（不止评估、也含推理/生产路径）都要共识门——是 [[honest-nondeterministic-eval]] 从评估搬到推理期的延伸。

- 回归权衡：别在 BM25 最坏值上"推测能救回"就拍板 → 先量 rerank 生产路径真数。
可复用点：accept/mitigate 决策前，量用户真正走的那条链路的真数，不在最坏代理指标上做判断。


## Today's numbers (if any)

满分10分，给6分。