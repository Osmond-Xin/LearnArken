# LearnArken Visual Map

## Conclusion

这份图谱把项目拆成三层理解：

1. **系统架构**：数据从技术出版物进入，经过标准校验、图谱、检索、Agent、推理服务，最后形成可审计答案。
2. **知识领域**：哪些是标准知识，哪些是数据库/索引，哪些是底层模型，哪些是调优操作，哪些是工程选型。
3. **学习顺序**：先搭标准化数据和评估闭环，再逐步加高级检索、知识图谱、多智能体和推理优化。

## System Architecture

Source: [docs/diagrams/architecture-flow.mmd](diagrams/architecture-flow.mmd)
Rendered: [architecture-flow.svg](diagrams/rendered/architecture-flow.svg)

![System architecture](diagrams/rendered/architecture-flow.svg)

```mermaid
flowchart TD
  Samples["samples/\nXML, PDF, images, parts data"] --> Ingestion["Ingestion service\nXML/PDF/image parsing\nICN metadata extraction"]
  Ingestion --> Canonical["Canonical publication model\nDM, PM, parts, tasks,\nwarnings, refs, versions"]

  Canonical --> Validation["Validation pipeline\nBREX/SNS checks\nreference checks\napplicability checks"]
  Canonical --> Indexing["Indexing pipeline\ngraph-context chunks\nsparse+dense+ColBERT indexes"]

  Validation --> DependencyGraph["Dependency graph\nmodule refs, media refs,\npart refs, version diffs"]
  Validation --> Findings["Validation findings\nrule id, severity,\nsource path, fix hint"]

  DependencyGraph --> RDF["RDF/OWL knowledge graph\nnamed graphs, SPARQL,\ntemporal versions"]
  Indexing --> Search["Search infrastructure\nBM25/SPLADE\nQdrant HNSW\nFAISS IVF/PQ lab\nColBERT store"]

  RDF --> Orchestrator["Adaptive RAG orchestrator\nHyDE, fusion, rerank,\ncontext budget, citations"]
  Search --> Orchestrator
  Findings --> Orchestrator

  Orchestrator --> Agents["Multi-agent reasoning\nReAct, ToT, GoT, MCTS\nstandards agent, graph agent,\ncritic, judge"]
  Agents --> Inference["Inference service\nvLLM/TGI adapter\nstreaming, prefix cache,\nspeculative decoding lab"]
  Inference --> API["FastAPI + UI\nanswers, traces,\naudit records, reports"]

  API --> Evaluation["Evaluation dashboard\nRecall@k, MRR, nDCG,\ngroundedness, compliance"]
  Evaluation -.feedback.-> Indexing
  Evaluation -.feedback.-> Agents
  Evaluation -.feedback.-> Inference
```

## Knowledge Domain Map

Source: [docs/diagrams/learning-domain-map.mmd](diagrams/learning-domain-map.mmd)
Rendered: [learning-domain-map.svg](diagrams/rendered/learning-domain-map.svg)

![Knowledge domain map](diagrams/rendered/learning-domain-map.svg)

```mermaid
flowchart LR
  subgraph D0["业务与标准域"]
    S1000D["S1000D\nDMC, PM, ICN, BREX, SNS"]
    Adjacent["ATA iSpec 2200\nASD S2000M\nMIL-STD-40051\nDITA"]
    Compliance["ISO/AS9100\n21 CFR Part 11\nGDPR/HIPAA\nITAR/EAR"]
  end

  subgraph D1["数据工程域"]
    Parse["XML/PDF/image parsing\nnamespaces, XPath, XSD"]
    Model["Canonical model\nPydantic schemas\nversioned packages"]
    Validate["Rule engine\nvalidation findings\ndependency graph"]
  end

  subgraph D2["数据库与索引域"]
    Pg["PostgreSQL\nmetadata, versions,\naudit log"]
    Obj["Object storage\nsource files,\ncontent hashes"]
    KG["RDF/OWL store\nSPARQL, named graphs"]
    Lexical["Lexical index\nBM25, SPLADE"]
    Vector["Vector DB\nQdrant HNSW"]
    Faiss["FAISS lab\nFlat, HNSW, IVF, PQ, GPU"]
  end

  subgraph D3["检索与RAG算法域"]
    Chunk["Graph-context chunking"]
    Dense["Dense embeddings\nE5/BGE/SBERT"]
    ColBERT["ColBERT\nlate interaction"]
    Fusion["RRF fusion\nhybrid retrieval"]
    Rerank["Cross-encoder rerank\nmonoT5-style rerank"]
    HyDE["HyDE\nquery expansion"]
    Context["Adaptive context\ncitation assembly"]
  end

  subgraph D4["底层模型与推理域"]
    HF["HuggingFace\nTransformers, tokenizers"]
    Torch["PyTorch\nbatching, inference,\noptional DDP/FSDP notes"]
    VLLM["vLLM/TGI\nPagedAttention,\ncontinuous batching"]
    TRT["TensorRT-LLM\noptional NVIDIA lab"]
    ONNX["ONNX\nsmall model export"]
  end

  subgraph D5["多智能体与推理搜索域"]
    ReAct["ReAct\ntool use + reasoning"]
    ToT["ToT\nbranching plans"]
    GoT["GoT\ndependency reasoning graph"]
    MCTS["MCTS/LATS\nsearch over actions"]
    Critic["Adversarial critic\njudge, evidence gap checks"]
  end

  subgraph D6["工程选型与运维域"]
    API["FastAPI\nasync API, streaming"]
    Frameworks["LangGraph\nLlamaIndex/Haystack\nDSPy"]
    Obs["OpenTelemetry\nstructured logs\nanswer traces"]
    Deploy["Docker/K8s sketch\nblue-green deploy\nload test"]
    Rust["Optional Rust/PyO3\nlatency hot path"]
    Formal["Optional Lean/Rocq\nsmall invariant proof"]
  end

  D0 --> D1
  D1 --> D2
  D2 --> D3
  D4 --> D3
  D3 --> D5
  D2 --> D5
  D1 --> D5
  D4 --> D5
  D5 --> D6
  D3 --> D6
  D6 -.observes.-> D1
  D6 -.observes.-> D3
  D6 -.observes.-> D5
```

## Concept Classification

Source: [docs/diagrams/concept-classification.mmd](diagrams/concept-classification.mmd)
Rendered: [concept-classification.svg](diagrams/rendered/concept-classification.svg)

![Concept classification](diagrams/rendered/concept-classification.svg)

```mermaid
flowchart TB
  Root["LearnArken 技术概念"]

  Root --> Standards["领域标准\n学会读懂和建模规则"]
  Standards --> StandardsItems["S1000D, DMC, BREX, SNS,\nICN, PM assembly,\nATA/iSpec, S2000M, MIL, DITA"]

  Root --> DataStores["数据库与索引\n系统依赖的持久化能力"]
  DataStores --> StoreItems["PostgreSQL: metadata/audit\nObject store: raw artifacts\nRDF store: triples/SPARQL\nOpenSearch/Tantivy: BM25\nQdrant: HNSW vectors\nFAISS: IVF/PQ/GPU experiments"]

  Root --> LLMCore["底层模型能力\n模型调用、表示和推理加速"]
  LLMCore --> LLMItems["HuggingFace, embeddings,\nrerankers, ColBERT,\nvLLM/TGI, PagedAttention,\nONNX, TensorRT-LLM"]

  Root --> Tuning["需要调优的操作\n用评估指标驱动参数选择"]
  Tuning --> TuningItems["chunk size/overlap\nBM25 analyzer/field boost\nHNSW M/efSearch\nIVF nlist/nprobe, PQ bytes\nRRF k, rerank topN\nHyDE prompt/context budget\nvLLM batching/cache settings"]

  Root --> FrameworkChoice["开发过程中的选型\n框架只服务于可验证目标"]
  FrameworkChoice --> FrameworkItems["FastAPI: API\nPydantic: schemas\nLangGraph: agents\nLlamaIndex/Haystack: RAG comparison\nDSPy: prompt/retrieval optimization\nRust/PyO3: optional hot path"]

  Root --> Evaluation["评估与证明\n决定能不能写进简历"]
  Evaluation --> EvalItems["Recall@k, MRR, nDCG\ncitation coverage\ngroundedness\ncompliance precision/recall\nlatency/throughput\naudit traces"]
```

## Learning Dependency Plan

Source: [docs/diagrams/learning-roadmap.mmd](diagrams/learning-roadmap.mmd)
Rendered: [learning-roadmap.svg](diagrams/rendered/learning-roadmap.svg)

![Learning roadmap](diagrams/rendered/learning-roadmap.svg)

```mermaid
flowchart TD
  P0["P0 基础工程\nrepo skeleton, CLI,\nfixtures, tests"] --> P1["P1 标准建模\nS1000D-like XML\nDMC/ICN/PM/BREX/SNS"]
  P1 --> P2["P2 数据管线\ncanonical JSON\nvalidation findings\nRDF triples"]
  P2 --> P3["P3 基础检索\nBM25 baseline\nretrieval eval"]
  P3 --> P4["P4 向量检索\ndense embeddings\nQdrant HNSW\nFAISS baseline"]
  P4 --> P5["P5 高级RAG\nSPLADE, ColBERT,\nRRF, rerank, HyDE,\nadaptive context"]
  P2 --> P6["P6 知识图谱\nOWL/RDF ontology\nSPARQL\nversioned named graphs"]
  P5 --> P7["P7 多智能体\nReAct tools\nToT/GoT/MCTS labs\ncritic + judge"]
  P6 --> P7
  P7 --> P8["P8 推理与运维\nvLLM/TGI serving\nstreaming, cache,\nload test, traces"]
  P8 --> P9["P9 作品集收尾\nbenchmark tables\narchitecture diagrams\nJD coverage matrix"]

  P3 -.quality gate.-> G1["Gate: Recall@k baseline stable"]
  P5 -.quality gate.-> G2["Gate: hybrid beats baseline"]
  P7 -.quality gate.-> G3["Gate: critic catches unsupported claims"]
  P8 -.quality gate.-> G4["Gate: latency and audit trace recorded"]
```

## How To Read The Map

- **先看 System Architecture**：理解项目怎么跑起来。
- **再看 Knowledge Domain Map**：理解每项技术属于哪个领域，以及谁依赖谁。
- **然后看 Concept Classification**：区分数据库、底层 LLM、调优项、开发框架和评估项。
- **最后看 Learning Dependency Plan**：按依赖顺序学习和实现，避免一上来就陷进 vLLM、ColBERT 或 MCTS。
