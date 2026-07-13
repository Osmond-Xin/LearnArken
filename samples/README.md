# 航空技术出版物规范样例集 (Aviation Standards Samples)

本目录收集并下载了**真实的、在网上公开且有明确来源和引用的 S1000D 规范文件**。这些文件均直接下载自知名的开源项目，供你理解不同文档类型的结构。

---

## 1. 真实文件下载来源与引用

本项目不包含任何编撰/虚构的 XML，所有数据均来自以下两个 GitHub 仓库：

1. **[kibook/s1kd-tools-doc](https://github.com/kibook/s1kd-tools-doc)**：
   * 这是一个使用开源 S1000D 命令行工具链生成的标准 S1000D CSDB（公共源数据库）数据集实例。
   * 我们从中下载了描述性模块、出版模块 (PMC) 以及模块清单 (DML)。
2. **[Amplexor/oxygen-asd-s1000d](https://github.com/Amplexor/oxygen-asd-s1000d)**：
   * 这是一个用于在 SyncroSoft oXygen XML 编辑器中对 S1000D 进行结构化编辑的官方插件框架。
   * 我们从中下载了 S1000D 规范中几种极其核心的**程序性（Procedure）**、**图解零件（IPD）**和**排故分离（Fault Isolation）**数据模块的 Schema 校验模板。

---

## 2. 目录下的 S1000D 真实文件说明

文件存放在 [samples/s1000d/](file:///Users/osmond/Documents/Job/LearnArken/samples/s1000d/) 目录下，具体说明如下：

### ① 真实数据模块实例 (来自 `kibook/s1kd-tools-doc`)
* **描述性数据模块 1**：[DMC-S1KDTOOLS-A-00-00-00-00A-040B-D_EN-CA.xml](file:///Users/osmond/Documents/Job/LearnArken/samples/s1000d/DMC-S1KDTOOLS-A-00-00-00-00A-040B-D_EN-CA.xml)
  * *描述*：用于介绍 `s1kd-tools` 的概要信息。
* **描述性数据模块 2**：[DMC-S1KDTOOLS-A-01-00-00-00A-040A-D_EN-CA.xml](file:///Users/osmond/Documents/Job/LearnArken/samples/s1000d/DMC-S1KDTOOLS-A-01-00-00-00A-040A-D_EN-CA.xml)
  * *描述*：具体工具 `s1kd-syncrefs` 的使用说明，包含 `<definitionList>`（定义列表）的结构化文本。
* **出版模块 (PMC)**：[PMC-S1KDTOOLS-KHZAE-00000-00_EN-CA.xml](file:///Users/osmond/Documents/Job/LearnArken/samples/s1000d/PMC-S1KDTOOLS-KHZAE-00000-00_EN-CA.xml)
  * *描述*：定义了一本完整技术手册的树状结构目录，内部含有大量的 `<pmEntry>` 节点和指向数据模块的 `<dmRef>`。
* **数据模块列表 (DML)**：[DML-S1KDTOOLS-KHZAE-C-2017-00001.xml](file:///Users/osmond/Documents/Job/LearnArken/samples/s1000d/DML-S1KDTOOLS-KHZAE-C-2017-00001.xml)
  * *描述*：记录整个技术出版包内的所有数据模块清单。

### ② 真实 Schema 校验模板实例 (来自 `Amplexor/oxygen-asd-s1000d`)
* **程序性数据模块模板 (Procedural DM)**：[DMC-Procedural-Template-Amplexor.xml](file:///Users/osmond/Documents/Job/LearnArken/samples/s1000d/DMC-Procedural-Template-Amplexor.xml)
  * *校验 Schema*：`proced.xsd`
  * *描述*：真实程序性文档的骨架，定义了准备工作 `<preliminaryRqmts>`、主体维修步骤 `<mainProcedure>` -> `<proceduralStep>` 和收尾要求 `<closeRqmts>` 的标准结构。
* **图解零件数据模块模板 (Illustrated Parts DM)**：[DMC-IPD-Template-Amplexor.xml](file:///Users/osmond/Documents/Job/LearnArken/samples/s1000d/DMC-IPD-Template-Amplexor.xml)
  * *校验 Schema*：`ipd.xsd`
  * *描述*：备件图纸与物料对照清单的标准 XML，包含零件号、装配关系和插图引用。
* **排故与故障隔离数据模块模板 (Fault Isolation DM)**：[DMC-Fault-Isolation-Template-Amplexor.xml](file:///Users/osmond/Documents/Job/LearnArken/samples/s1000d/DMC-Fault-Isolation-Template-Amplexor.xml)
  * *校验 Schema*：`fault.xsd`
  * *描述*：维修人员在排除故障时的决策逻辑与判断流骨架。

---

## 3. 许可证与再分发（公开仓库前必读）

> [!WARNING]
> "网上公开可见"不等于"可以再分发"。两个来源的许可状态不同（2026-07-11 核查）：
>
> 1. **Amplexor/oxygen-asd-s1000d：Apache-2.0** ✅ 三个 Template 文件可以进入公开仓库，
>    保留本 README 的出处说明即可。
> 2. **kibook/s1kd-tools-doc：仓库未声明许可证** ⚠️ 默认保留全部版权，这四个
>    S1KDTOOLS 文件**不得进入公开仓库**（已在项目 `.gitignore` 中排除，仅本地学习用）。
>    公开仓库中的等价物：用 GPL-3.0 的 s1kd-tools 工具链自行生成合成数据模块，
>    或按 Week 1 计划手写合成 fixtures。

## 4. 为什么没有 ATA iSpec 2200 和 ASD S2000M 的官方 XML？

> [!IMPORTANT]
> **ATA iSpec 2200** 和 **ASD S2000M** 均属于**私有/商业机密标准 (Proprietary Standards)**：
>
> 1. **ATA iSpec 2200** 由美国航空运输协会 (Airlines for America, A4A) 维护，其 XML DTD 和 Schema 只有付费会员（通常是航空公司和 OEM 厂商）能够获取，分发这些文件属于侵权行为。
> 2. **ASD S2000M** 由欧洲航天与国防工业协会维护，用于规范军事和民用航空的物流与物料链，涉及供应链和国防信息，同样需要付费商业授权。
>
> S1000D 作为一个现代化、基于模块化 XML 的开放规范，已经成为业界的黄金标准。因此，通过研究上述公开的 S1000D 真实 XML 文件，你能够完全掌握现代航空 RAG 系统开发的数据清洗与分块策略。
