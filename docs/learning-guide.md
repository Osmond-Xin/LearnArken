# LearnArken Learning Guide

> 配套详解教程见 [tutorials/00-overview.md](tutorials/00-overview.md)：
> 以"零 AI 背景的资深工程师"视角逐章讲解本指南中的每项技术
> （类比、原理、调优、失败模式、面试问答），按编号顺序阅读。

## Conclusion

Treat this project as a staged learning system. Every selected technology must
leave proof in the repository:

- A minimal implementation.
- A test or fixture.
- A benchmark or evaluation result.
- A short note explaining tradeoffs and failure modes.

Do not try to master everything at once. Build the baseline first, then add one
advanced technique at a time and measure whether it actually helps.

## Selection Principles

Use these rules when choosing tools:

- Prefer boring production tools for the main path.
- Put research-heavy tools behind adapters.
- Keep one canonical data model between ingestion, validation, graph, retrieval,
  and agents.
- Use benchmarks to justify advanced retrieval and serving choices.
- Label synthetic or simplified standards work honestly as "S1000D-like" unless
  it conforms to an actual issue and schema.

## Technology Choices And Mastery Standards

| Area | Main choice | Why this choice | Alternatives to know | Mastery standard | Proof artifact |
| --- | --- | --- | --- | --- | --- |
| API | FastAPI + Python 3.12 | Strong async support, simple OpenAPI, good ML ecosystem fit | Litestar, Flask, gRPC | Can build async endpoints, streaming, dependency injection, typed errors | `apps/api`, integration tests |
| Workers | asyncio + multiprocessing | Mirrors JD requirement and covers IO-bound plus CPU-bound paths | Celery, Dramatiq, Ray | Can explain event loop vs process parallelism and avoid blocking async handlers | ingestion/indexing worker tests |
| Schemas | Pydantic | Clear canonical models and validation errors | dataclasses, attrs, msgspec | Can model DMC, publication module, findings, evidence, graph refs | schema tests and JSON snapshots |
| XML | lxml + XPath + XSD | Mature XML parsing, namespace support, validation support | xmlschema, Saxon, Java tooling | Can parse namespaced XML, validate schema, produce precise line-level findings | S1000D-like fixtures |
| Standards rules | Custom rule engine, Schematron-inspired | BREX/SNS rules need explicit auditable checks | Real Schematron, commercial CSDB tools | Can encode rule id, severity, path, message, fix hint | valid/invalid package reports |
| Metadata store | PostgreSQL | Reliable metadata, versions, audit log, transactional consistency | SQLite for local, DuckDB for analytics | Can design versioned package tables and idempotent ingestion | migration and rollback test |
| Object store | Local FS first, MinIO later | Keeps M0 simple, MinIO later simulates production object storage | S3, GCS, Azure Blob | Can store source artifacts with content hashes | reproducible package import |
| RDF graph | RDFLib first, Oxigraph later | RDFLib is easy for learning; Oxigraph gives real SPARQL service path | GraphDB, Apache Jena, Neo4j | Can model triples, named graphs, ontology classes, SPARQL property paths | RDF snapshots and SPARQL examples |
| Vector DB | Qdrant | Production service, HNSW, payload filtering, Rust implementation | Milvus, Weaviate, pgvector, Elasticsearch | Can tune HNSW and metadata filters, measure recall/latency | vector benchmark |
| ANN lab | FAISS | Best learning tool for IVF/PQ/GPU tradeoffs | hnswlib, ScaNN, DiskANN | Can compare Flat, HNSW, IVF, IVFPQ, recall vs memory | FAISS benchmark report |
| Lexical search | OpenSearch or Tantivy | BM25 baseline and searchable operational path | Lucene, Elasticsearch, Whoosh | Can explain BM25, analyzers, tokenization, field boosts | BM25 baseline eval |
| Dense embeddings | SentenceTransformers/E5/BGE via HuggingFace | Fast local experiments and broad model ecosystem | OpenAI embeddings, Cohere, Voyage | Can normalize vectors, batch encode, version embedding models | embedding metadata and eval |
| Sparse neural | SPLADE | Covers neural sparse retrieval and vocabulary expansion | uniCOIL, DeepImpact | Can explain why sparse expansion helps exact-match domains | SPLADE ablation |
| Late interaction | ColBERT | Strong retrieval quality and direct JD match | SPLADE++, cross-encoder-only | Can explain token-level MaxSim and storage/latency tradeoff | ColBERT benchmark |
| Reranking | Cross-encoder or monoT5-style reranker | High precision after broad recall | Cohere rerank, Jina reranker, custom BERT | Can measure rerank cost and quality lift | reranker ablation |
| Fusion | Reciprocal Rank Fusion | Simple, robust, score-scale independent | weighted scores, learned fusion | Can implement RRF and explain `k` sensitivity | hybrid retrieval eval |
| RAG orchestration | Custom first, LlamaIndex selectively | Keeps core logic visible; LlamaIndex useful for comparing abstractions | Haystack, LangChain chains | Can trace chunk selection, evidence budgeting, citations | answer trace JSON |
| Agents | LangGraph | Explicit stateful graph orchestration for multi-agent workflows | Semantic Kernel, AutoGen, CrewAI | Can define tool contracts, state transitions, retries, critic loop | agent trace and tests |
| Prompt optimization | DSPy optional | Good way to show measurable prompt/retriever optimization | manual prompts, LangSmith evals | Can optimize against a small golden set without prompt folklore | DSPy experiment note |
| LLM serving | vLLM first | Directly covers PagedAttention, batching, streaming, OpenAI-compatible serving | TGI, llama.cpp, Ollama | Can explain prefill/decode, KV cache, throughput vs latency | load-test report |
| NVIDIA inference | TensorRT-LLM optional lab | Strong resume keyword but hardware-dependent | ONNX Runtime, FasterTransformer | Can describe build/runtime path even if only documented locally | lab note or skipped-hardware note |
| Model format | ONNX optional for reranker/classifier | Practical deployment exercise for smaller models | TorchScript, TensorRT engines | Can export, validate numerical drift, run inference | ONNX parity test |
| Observability | OpenTelemetry + structured logs | Production proof for RAG and agents | LangSmith, Arize, Phoenix | Can trace request, retrieval, model call, citations, audit event | trace screenshots/logs |
| Performance hot path | Rust via PyO3 optional | Demonstrates latency-critical path without rewriting the project | Cython, Numba, C++ | Can profile first, then accelerate chunking/tokenization | before/after benchmark |
| Formal methods | Lean or Rocq/Coq optional | Shows formal verification awareness without derailing the core project | Isabelle, TLA+ | Can prove a small validator invariant or model ingestion state transitions | tiny proof example |

## What "Mastered" Means

For each major technology, use this four-part standard:

1. Concept: explain the core idea, tradeoff, and when not to use it.
2. Build: implement a minimal local version without hiding everything behind a
   framework.
3. Measure: produce a metric, trace, benchmark, or failing test that proves the
   behavior.
4. Debug: document at least three failure modes and how you detect them.

Resume-level mastery means you can open the repo and show code, not just name
the paper.

## Papers And Official References

### RAG And Retrieval

- [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401): core RAG idea, provenance, non-parametric memory.
- [Dense Passage Retrieval for Open-Domain Question Answering](https://arxiv.org/abs/2004.04906): dense dual-encoder retrieval baseline.
- [Sentence-BERT](https://arxiv.org/abs/1908.10084): sentence embeddings and semantic similarity basics.
- [BEIR](https://arxiv.org/abs/2104.08663): retrieval evaluation mindset and out-of-domain benchmark design.
- [SPLADE](https://arxiv.org/abs/2107.05720): neural sparse retrieval with lexical expansion.
- [ColBERT](https://arxiv.org/abs/2004.12832): late-interaction retrieval and MaxSim-style ranking.
- [HyDE](https://arxiv.org/abs/2212.10496): hypothetical document embeddings for zero-shot dense retrieval.
- [Document Ranking with a Pretrained Sequence-to-Sequence Model](https://arxiv.org/abs/2003.06713): monoT5-style reranking concept.
- [Reciprocal Rank Fusion](https://dl.acm.org/doi/10.1145/1571941.1572114): rank fusion for hybrid retrieval.

### Vector Search

- [HNSW](https://arxiv.org/abs/1603.09320): graph-based approximate nearest-neighbor search.
- [Product Quantization for Nearest Neighbor Search](https://ieeexplore.ieee.org/document/5432202): vector compression foundation.
- [Billion-scale similarity search with GPUs](https://arxiv.org/abs/1702.08734): FAISS/GPU search and IVF/PQ-style large-scale search.
- [The Faiss Library](https://arxiv.org/abs/2401.08281): modern overview of FAISS design principles.
- [Qdrant indexing docs](https://qdrant.tech/documentation/manage-data/indexing/): practical HNSW plus payload-filter indexing.
- [FAISS index selection guide](https://github.com/facebookresearch/faiss/wiki/Guidelines-to-choose-an-index): practical index tradeoffs.

### Knowledge Graphs And Semantic Web

- [RDF 1.1 Concepts](https://www.w3.org/TR/rdf11-concepts/): triples, graphs, IRIs, literals.
- [OWL 2 Overview](https://www.w3.org/TR/owl2-overview/): ontology classes, properties, individuals, reasoning profiles.
- [SPARQL 1.1 Query Language](https://www.w3.org/TR/sparql11-query/): querying RDF graphs.
- [From Local to Global: A Graph RAG Approach](https://arxiv.org/abs/2404.16130): graph-based RAG for corpus-level questions.

### Agents And Search

- [ReAct](https://arxiv.org/abs/2210.03629): interleaving reasoning and tool actions.
- [Tree of Thoughts](https://arxiv.org/abs/2305.10601): deliberate search over intermediate reasoning states.
- [Graph of Thoughts](https://arxiv.org/abs/2308.09687): graph-structured reasoning operations.
- [Language Agent Tree Search](https://arxiv.org/html/2310.04406v1): MCTS-style planning for language agents.

### Inference And Optimization

- [vLLM and PagedAttention blog](https://vllm.ai/blog/2023-06-20-vllm): practical overview of vLLM serving.
- [PagedAttention paper](https://arxiv.org/abs/2309.06180): KV-cache memory management for LLM serving.
- [Speculative Decoding](https://arxiv.org/abs/2211.17192): draft-model acceleration for autoregressive decoding.
- [TensorRT-LLM docs](https://nvidia.github.io/TensorRT-LLM/): NVIDIA inference optimization and deployment path.
- [ONNX docs](https://onnx.ai/onnx/): model exchange and runtime deployment basics.

### Technical Publication Standards

- [S1000D official site](https://s1000d.org/): official entry point for the specification.
- [S1000D downloads](https://users.s1000d.org/): specification and issue downloads.
- [ATA e-Business standards](https://ataebiz.org/standards/): ATA iSpec 2200 overview.
- [MIL-STD-40051 ASSIST record](https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=216328): official U.S. defense document record.
- [DITA 1.3 OASIS standard](https://www.oasis-open.org/standard/ditav1-3/): topic-oriented technical content standard.
- [ASD S2000M overview document](https://www.asd-ssg.org/c/document_library/get_file%3Fuuid%3Dd13a6c26-2f8e-41ea-bbf8-6f381f4225ec%26groupId%3D11317): materiel-management scope.

### Framework Docs

- [LlamaIndex docs](https://developers.llamaindex.ai/python/framework/): document and agent workflows.
- [LangGraph docs](https://docs.langchain.com/oss/python/langgraph/overview): stateful agent orchestration.
- [DSPy docs](https://dspy.ai/): structured and optimizable LLM programs.
- [Haystack docs](https://docs.haystack.deepset.ai/docs/intro): production RAG and agent pipelines.

## Operations To Implement

Each command should become a learning checkpoint:

```bash
learnarken inspect samples/package-a
learnarken validate samples/package-a
learnarken transform samples/package-a --to canonical
learnarken graph load build/canonical/package-a.json
learnarken graph query examples/queries/affected_modules.sparql
learnarken index build samples/package-a --retrievers bm25,dense,splade,colbert
learnarken query "Which procedures mention part P-1002?"
learnarken eval retrieval
learnarken eval compliance
learnarken bench ann --indexes flat,hnsw,ivf,ivfpq
learnarken serve api
learnarken serve llm --runtime vllm
```

A command is not done until it has deterministic output, at least one test, and a
short note explaining what can go wrong.

## Critical Development Steps

1. Start with legal synthetic fixtures. Do not depend on proprietary aviation or
   defense data.
2. Build the canonical model before retrieval. Bad schemas create bad RAG.
3. Write validators before LLM repair. Validators are the ground truth for
   compliance claims.
4. Keep transformations deterministic. Same input package should produce the
   same canonical JSON and RDF triples.
5. Version everything: source package, canonical model, graph triples, chunks,
   embeddings, prompts, model names, and evaluation sets.
6. Add BM25 before dense retrieval. It is the baseline and often strong in
   technical domains.
7. Add hybrid retrieval before agents. Agents cannot compensate for missing
   evidence.
8. Store answer traces from day one. Every answer should show query, retrieved
   evidence, graph facts, prompt, model, citations, and critic result.
9. Measure retrieval before generation. If Recall@k is bad, answer quality will
   be unstable.
10. Treat LLM output as untrusted. Run generated fixes through validators and
    never let agents execute arbitrary file or database operations.
11. Profile before optimization. Add Rust, Numba, ONNX, or TensorRT only after a
    benchmark identifies the bottleneck.
12. Separate "implemented" from "studied" in the README. This keeps the portfolio
    honest.

## Common Problems And Answers

| Question | Answer |
| --- | --- |
| Do I need full S1000D compliance? | No. For learning, build a transparent S1000D-like subset first. Be explicit about what is simplified. |
| What if I cannot access proprietary standard examples? | Use legal synthetic XML fixtures and public specification concepts. The value is in modeling, validation, transformation, and evaluation. |
| Why not just use one vector database? | The JD asks for retrieval expertise. You need BM25, sparse neural, dense, ColBERT, fusion, and ANN benchmarks to prove tradeoff understanding. |
| Why RDF instead of only Neo4j? | RDF/OWL/SPARQL map directly to standards, ontologies, named graphs, and compliance reasoning. A property graph can be an optional comparison. |
| Do I really need SPLADE and ColBERT? | Yes, but as experiments. BM25+dense is the product path; SPLADE and ColBERT are measured learning modules. |
| Should I use LangChain, LlamaIndex, Haystack, and DSPy together? | No. Use custom code for the core, LangGraph for agents, LlamaIndex or Haystack for comparison, and DSPy only for a small optimization experiment. |
| What if I do not have a GPU? | Implement CPU/local paths first. Mark FAISS GPU, TensorRT-LLM, and large vLLM benchmarks as hardware-dependent labs. |
| How do I prevent hallucination? | Require citations, use retrieval/graph traces, run critic checks, validate generated fixes, and fail closed when evidence is missing. |
| When is multi-agent useful here? | For tasks with separable roles: retrieve evidence, inspect graph, validate standards, simulate impact, and critique unsupported claims. |
| How much formal verification is enough? | One tiny proof is enough: for example, a validator invariant or package state-machine invariant. This shows awareness without stealing time from the core project. |
| What makes this resume-ready? | A runnable demo, benchmark tables, traces, validation reports, and a JD coverage matrix linked to concrete files. |

## Knowledge To Strengthen

Prioritize these areas:

- Information retrieval: BM25, tokenization, analyzers, embeddings, ANN, recall,
  precision, MRR, nDCG, reranking, fusion.
- XML and standards: namespaces, XSD, XPath, Schematron ideas, modular
  publications, DMC/ICN/SNS/BREX concepts.
- Semantic web: RDF triples, named graphs, OWL classes/properties, SPARQL
  filters, property paths, ontology versioning.
- LLM systems: prompt contracts, structured outputs, tool calling, citations,
  failure handling, prompt injection risks.
- Agent systems: state machines, search algorithms, tool boundaries, traceability,
  evaluation of agent decisions.
- ML engineering: HuggingFace models, PyTorch inference, batching, ONNX export,
  embedding drift, model/version metadata.
- Serving performance: prefill vs decode, KV cache, continuous batching,
  PagedAttention, prefix caching, throughput vs latency.
- Distributed systems: sharding, idempotency, consistency, retries, backpressure,
  blue/green deployments.
- Compliance engineering: audit trails, provenance, access control, PII
  detection, export-control labels, approval workflows.
- Python performance: profiling, async pitfalls, multiprocessing costs, Cython,
  Numba, PyO3/Rust extension basics.

## Suggested Learning Order

1. XML, canonical model, S1000D-like identifiers, validators.
2. BM25 retrieval and retrieval evaluation.
3. Dense embeddings and vector search.
4. Hybrid retrieval and reranking.
5. RDF/OWL/SPARQL knowledge graph.
6. Graph-aware chunking and adaptive context.
7. Agent workflows with strict tool contracts.
8. ANN benchmarks and consistency experiments.
9. vLLM serving and latency/load testing.
10. Optional labs: SPLADE, ColBERT, DSPy, TensorRT-LLM, Rust, formal proof.

## Personal Study Checklists

Before claiming a topic, answer these questions in your own notes:

- What problem does it solve in this project?
- What is the simplest baseline?
- What metric shows improvement?
- What inputs make it fail?
- What is the operational cost?
- What code file, test, or benchmark proves I implemented it?

For interviews, prepare short explanations for:

- Why BM25 is still useful in technical manuals.
- Why dense retrieval fails on exact identifiers and part numbers.
- Why reranking improves precision but hurts latency.
- Why RDF named graphs are useful for temporal publication versions.
- Why agents need deterministic validators and bounded tools.
- Why vLLM improves serving throughput through KV-cache management.
- Why hardware-dependent optimizations should be optional in a learning repo.
