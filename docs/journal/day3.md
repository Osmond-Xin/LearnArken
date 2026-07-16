# Day N Learning Journal — <date>

> Human-written; AI does not ghostwrite. (INV-6) Three fixed questions — each
> answer must contain at least one concrete instance. No platitudes.

## 1. What did I learn today?

- 今天的核心是chunk和embedding，但是今天并没有做chunk的操作，而是做chunk的选型。所以未来需要深度的review代码，因为虽然我设计了，但是AI执行的如何，chunk是否是按照我的规划操作，我并不知晓。
- Chunk目前使用的是按照结构切分，至于入门的按照长度切分，标准长度，按照自然段切分的这种形式，由于当前系统是针对S1000D，所以先作为舍弃。
- 今天的核心应该是让我意识到架构设计在初期就应该完善，包括数据库，即现代的向量数据库的选型，Graphig的选型，要确保它是符合行业标准且能够向后兼容的，能够兼容我所要的大量的特性。

## 2. Where was the AI wrong, and how did I find out?

- spec没有写完。AI就急于的要向前推进了，我制止了，让它去review。
- 红队没有跟随流程自然发起。我要求Claude补充在他的claude.MD文件中，以确保能够自然启动。
- 默认的讨论会记录到文档中，AI并没有启动，这是个问题，我发现后要求它启动了。

## 3. What AI proposal did I reject, and why?

- 在最初向量数据库和图存储的选型中，AI都挑的是最轻量级的，我要求的是挑的行业主流的。
- AI把一个更改建议说是明天再改，我的要求是一旦发现问题就直接修改。

## Today's numbers (if any)

10分满分，今天6分。