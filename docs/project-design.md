# LearnArken Project Design

## Conclusion

Build this project as a **Technical Publication Intelligence Platform**:

1. Ingest S1000D, ATA iSpec 2200, ASD-SPEC 2000M, MIL-STD-40051, and DITA-like
   technical-publication samples.
2. Transform them into a canonical publication model.
3. Validate structure, references, BREX/SNS-like rules, and dependency graphs.
4. Build both a vector index and an RDF/OWL knowledge graph.
5. Answer technical and compliance questions with graph-augmented hybrid RAG.
6. Use multi-agent critic workflows to find evidence gaps, invalid references,
   outdated procedures, and standard-compliance issues.
7. Expose the whole system through production-shaped APIs, evaluation, tracing,
   and deployable inference services.

The goal is not to build a full enterprise S1000D suite. The goal is to create
a credible learning system where every major JD keyword has a visible artifact:
code, tests, benchmark, diagram, dataset, or demo.

## Product Scenario

User story:

> A maintenance engineer uploads aircraft or defense technical-publication data.
> The system validates the data package, constructs a dependency and knowledge
> graph, indexes the content, and answers questions with cited source fragments,
> standard checks, and an agent-generated risk review.

Example questions:

- "Which data modules are affected if this part number changes?"
- "Does this procedure violate a BREX/SNS rule?"
- "Find every maintenance task that mentions this component and explain the
  dependencies."
- "Compare the current procedure with the previous version and list safety
  critical differences."
- "Generate a draft correction and have critic agents review it."

## Architecture

```text
samples/
  technical publications, XML, PDF, images, parts data
        |
        v
ingestion service
  XML/PDF/image parsing, ICN extraction, metadata normalization
        |
        v
canonical publication model
  data modules, publication modules, parts, tasks, warnings, references
        |
        +--------------------+
        |                    |
        v                    v
validation pipeline       indexing pipeline
  BREX/SNS checks           graph-context chunks
  reference checks          sparse index
  dependency graph          dense index
  temporal diff             ColBERT index
        |                    |
        v                    v
RDF/OWL knowledge graph   vector/search services
  SPARQL                    BM25/SPLADE
  temporal versions         HNSW/IVF/PQ
  graph embeddings          reranking
        |                    |
        +---------+----------+
                  v
          adaptive RAG orchestrator
          HyDE, fusion, rerank, context budget
                  |
                  v
          multi-agent reasoning layer
          ReAct, ToT/GoT, MCTS experiments,
          world-model simulation, critic review
                  |
                  v
          API + UI + evaluation dashboard
```

## Repository Shape

Planned structure:

```text
apps/
  api/                    FastAPI service
  worker/                 async ingestion and indexing workers
  ui/                     optional review/search UI
packages/
  publication_model/      canonical schemas and domain types
  standards/              S1000D/ATA/MIL/DITA adapters and validators
  ingestion/              XML, PDF, image, CGM/ICN metadata ingestion
  retrieval/              chunking, sparse+dense+ColBERT, rerank, HyDE
  graph/                  RDF/OWL ontology, SPARQL, graph embeddings
  agents/                 ReAct, ToT, GoT, MCTS, critic workflows
  inference/              vLLM/TGI adapters, caching, routing
  evaluation/             metrics, golden sets, benchmark runners
  observability/          traces, audit log, provenance
rust/
  chunker/                optional latency-critical chunking/tokenization
infra/
  docker-compose.yml      Postgres, object storage, graph store, search
  k8s/                    deployment sketches
docs/
  adr/                    architecture decision records
  standards-notes/        learning notes for each publication standard
tests/
  fixtures/               small legal sample packages
  integration/
benchmarks/
  retrieval/
  inference/
```

## Core Modules

### 1. Standards-Aware Ingestion

Purpose: prove grounding in S1000D and adjacent publication standards.

Capabilities:

- Parse S1000D-like XML data modules and publication modules.
- Extract DMC, ICN, issue info, applicability, warnings, cautions, procedures,
  figures, tables, and cross references.
- Model simplified BREX and SNS rules.
- Add adapters for ATA iSpec 2200, MIL-STD-40051, DITA, and ASD-SPEC 2000M-like
  parts data.
- Build a package-level dependency graph.

Artifacts:

- Canonical Pydantic models.
- XML fixtures.
- Validator tests.
- A report showing valid and invalid sample packages.

### 2. Transformation And Validation Pipeline

Purpose: demonstrate production data engineering rather than just prompting.

Capabilities:

- Convert source documents into canonical JSON and RDF triples.
- Validate references, part links, media links, applicability, and rule sets.
- Produce machine-readable validation findings.
- Support evaluator-critic refinement: a model proposes fixes, validators and
  critic agents reject unsupported or non-compliant changes.

Artifacts:

- `learnarken validate samples/package-a`
- `learnarken transform samples/package-a --to canonical`
- Validation golden tests.
- Before/after transformation examples.

### 3. Graph-Augmented RAG

Purpose: cover advanced RAG, hybrid retrieval, and knowledge graphs.

Capabilities:

- Graph-contextualized chunking: chunks include DMC, task, component, procedure
  step, parent publication module, references, and temporal version.
- Hybrid fusion:
  - BM25 baseline.
  - SPLADE-style sparse retrieval.
  - Dense embeddings.
  - ColBERT late-interaction retrieval.
  - Reciprocal-rank fusion.
- Cross-encoder reranking.
- HyDE query expansion.
- Adaptive context orchestration: choose graph facts, chunks, tables, and prior
  versions based on query type.
- RDF/OWL ontology and SPARQL queries.
- Entity-relation extraction for components, tasks, tools, parts, warnings, and
  references.
- Temporal graph versioning for publication updates.
- Optional GNN embeddings for graph-aware retrieval features.

Artifacts:

- Retrieval benchmark comparing BM25, dense, hybrid, hybrid+rerank, and
  graph-enhanced RAG.
- SPARQL examples.
- Answer traces with citations.
- Failure analysis report.

### 4. Production Vector Search Lab

Purpose: turn vector search keywords into measurable experiments.

Capabilities:

- HNSW index through Qdrant or hnswlib.
- FAISS IVF and PQ experiments.
- Optional FAISS GPU benchmark when hardware is available.
- Simulated distributed sharding by collection, publication, and version.
- Real-time consistency experiment: ingest update, index update, query visibility,
  and rollback behavior.

Artifacts:

- Recall/latency benchmark.
- Index parameter comparison.
- Consistency test.
- ADR explaining when to use HNSW vs IVF/PQ.

### 5. Multi-Agent Reasoning Layer

Purpose: show agentic reasoning without making the system vague.

Agents:

- Retrieval agent: plans evidence gathering.
- Standards agent: checks S1000D/BREX/SNS and adjacent standard rules.
- Graph agent: writes SPARQL and inspects dependency paths.
- Counterfactual agent: asks "what changes if this module/part/version changes?"
- Critic agent: attacks unsupported claims and missing citations.
- Judge agent: produces final grounded answer and risk score.

Algorithms to implement:

- ReAct for tool-using question answering.
- Tree of Thoughts for alternative answer plans.
- Graph of Thoughts for dependency exploration.
- Small MCTS experiment for procedure-repair planning.
- World-model simulation over dependency graph changes.

Artifacts:

- Agent traces.
- Unit tests with mocked tools.
- Comparison of single-agent vs multi-agent answer quality.
- Adversarial self-critique examples.

### 6. Inference And Serving

Purpose: demonstrate practical LLM operations.

Capabilities:

- FastAPI gateway with async request handling.
- vLLM or TGI adapter for local/open model serving.
- Prompt and prefix caching.
- Streaming responses.
- Speculative decoding experiment if supported by selected model/runtime.
- TensorRT-LLM notes or optional lab, depending on hardware.
- Zero-downtime deployment pattern: blue/green or rolling model endpoint switch.

Artifacts:

- Load-test results.
- Latency dashboard.
- Cache-hit benchmark.
- Deployment runbook.

### 7. Evaluation, Compliance, And Observability

Purpose: make the project look production-ready.

Capabilities:

- Retrieval metrics: Recall@k, MRR, nDCG.
- Answer metrics: citation coverage, groundedness, exactness, contradiction rate.
- Standards metrics: validation precision/recall on known bad packages.
- Audit log for source, model, prompt, retrieved evidence, and final answer.
- Versioned datasets and reproducible benchmarks.
- Compliance-inspired controls:
  - ISO 9001/AS9100-style quality records.
  - 21 CFR Part 11-style audit trail and electronic approval simulation.
  - GDPR/HIPAA-style PII detection and redaction.
  - ITAR/EAR-style export-control tag propagation.

Artifacts:

- `learnarken eval retrieval`
- `learnarken eval compliance`
- OpenTelemetry traces.
- Audit-log examples.

## Technology Choices

Recommended stack:

- Python 3.12, FastAPI, asyncio, multiprocessing.
- Pydantic for canonical schemas.
- lxml for XML parsing.
- RDFLib or Oxigraph for RDF/SPARQL.
- Qdrant for service-oriented HNSW vector search.
- FAISS for IVF/PQ/GPU benchmark labs.
- OpenSearch or Tantivy for BM25.
- PyTorch and HuggingFace Transformers for embeddings/rerankers.
- ColBERT for late-interaction retrieval experiments.
- LlamaIndex for document indexing abstractions where useful.
- LangGraph or LangChain for agent orchestration.
- DSPy for prompt/retrieval optimization experiments.
- vLLM or TGI for local model serving.
- Docker Compose for local infrastructure.
- Optional Rust extension for chunking/tokenization hot paths.
- Optional ONNX export for reranker or classifier deployment.

Avoid trying to use every framework everywhere. Use each one where it creates a
clear artifact.

The detailed rationale, mastery standard, reading list, operation checklist, FAQ,
and learning priorities are maintained in
[learning-guide.md](learning-guide.md).

Architecture and learning-domain diagrams are maintained in
[visual-map.md](visual-map.md).

## Milestones

### M0: Foundation

Deliver:

- Repo skeleton.
- CLI entrypoint.
- Docker Compose for local services.
- Small sample technical-publication package.
- Architecture decision records.

Proof:

- `make test`
- `learnarken inspect samples/package-a`

### M1: Standards Model And Validators

Deliver:

- Canonical publication model.
- S1000D-like DMC, PM, ICN, SNS, and BREX validators.
- Dependency graph extraction.

Proof:

- Valid package passes.
- Invalid package produces precise findings.
- Tests cover each rule.

### M2: Transformation Pipeline

Deliver:

- XML to canonical JSON.
- Canonical JSON to RDF triples.
- Versioned package snapshots.

Proof:

- Deterministic transform snapshots.
- SPARQL queries answer basic package questions.

### M3: Hybrid RAG

Deliver:

- Graph-context chunker.
- BM25, dense, SPLADE-style sparse, ColBERT retrieval.
- Fusion and cross-encoder reranking.
- HyDE and adaptive context builder.

Proof:

- Benchmark table shows quality and latency tradeoffs.
- Answers include citations and graph facts.

### M4: Knowledge Graph RAG

Deliver:

- RDF/OWL ontology.
- Entity-relation extraction.
- Temporal graph versioning.
- Optional GNN embedding experiment.

Proof:

- Query answers dependency and version-impact questions.
- Graph features improve retrieval on selected benchmark cases.

### M5: Vector Search Operations

Deliver:

- HNSW service index.
- FAISS IVF/PQ benchmark.
- Sharding simulation.
- Real-time consistency tests.

Proof:

- Recall/latency charts.
- Update visibility and rollback tests.

### M6: Multi-Agent System

Deliver:

- ReAct agent with retrieval, SPARQL, validation, and diff tools.
- ToT/GoT planner experiments.
- MCTS repair-planning experiment.
- Critic and judge agents.

Proof:

- Agent traces show tool calls and rejected unsupported claims.
- Multi-agent mode improves compliance tasks over baseline.

### M7: Inference Optimization

Deliver:

- vLLM/TGI service adapter.
- Prefix caching and streaming.
- Load test.
- Blue/green endpoint switching.

Proof:

- Latency and throughput report.
- Deployment runbook.

### M8: Portfolio Demo

Deliver:

- End-to-end demo script.
- Evaluation dashboard.
- Final README with architecture, screenshots, benchmark tables, and lessons.

Proof:

- One command runs the demo.
- One page maps project artifacts to JD requirements.

## JD Coverage Matrix

| JD item | Project evidence |
| --- | --- |
| Graph-contextualized chunking | Chunker attaches DMC, task, entity, refs, version metadata |
| BM25/SPLADE + dense + ColBERT | Retrieval benchmark with each retriever |
| Cross-encoder reranking | Reranker stage and ablation |
| HyDE | Query expansion path with evaluation |
| Adaptive context orchestration | Context builder chooses chunks, graph facts, tables, versions |
| HNSW/PQ/IVF/GPU ANN | Qdrant/HNSW plus FAISS IVF/PQ/GPU lab |
| Distributed sharding | Simulated shard router and consistency tests |
| RDF/OWL/SPARQL | Ontology, triples, SPARQL tool |
| Entity-relation extraction | Extractor and graph ingestion |
| Temporal graph versioning | Versioned publication snapshots and diffs |
| GNN embeddings | Optional graph embedding benchmark |
| ReAct/ToT/GoT/MCTS | Agent experiments with traces |
| World-model simulation | Dependency-impact simulator |
| Counterfactual reasoning | Version/part-change what-if agent |
| Adversarial self-critique | Critic agent and groundedness checks |
| S1000D transformation | XML fixtures, DMC/PM/ICN model, transform pipeline |
| BREX/SNS validation | Rule engine and invalid fixture tests |
| Dependency graphs | Package dependency graph and impact analysis |
| Evaluator-critic refinement | Model proposal plus validator/critic loop |
| vLLM/TensorRT-LLM/TGI | vLLM/TGI implementation, TensorRT-LLM optional lab notes |
| PagedAttention/prefix caching/speculative decoding | Runtime experiment and benchmark notes |
| Parallelism/deploys | Serving runbook and deployment pattern |
| Python asyncio/multiprocessing | API and worker implementation |
| Rust/C++ latency path | Optional Rust chunker extension |
| HuggingFace/PyTorch/ONNX | Embeddings, reranker, optional ONNX export |
| LangChain/LlamaIndex/DSPy/Haystack | LlamaIndex retrieval, LangGraph agents, DSPy optimization, optional Haystack comparison |
| ISO/AS9100/21 CFR/GDPR/HIPAA/ITAR | Audit trail, quality records, data classification, redaction |

## Success Criteria

This project is resume-ready when it has:

- A runnable end-to-end demo.
- At least one valid and one invalid technical-publication package.
- A standards validation report.
- A dependency graph visualization or SPARQL query examples.
- Retrieval benchmarks with ablations.
- Agent traces with critic review.
- Inference latency benchmark.
- A final README that links each JD requirement to code and measured results.

## Resume Positioning

Recommended resume line after implementation:

> Built a standards-aware technical-publication RAG platform with S1000D-style
> validation, RDF/SPARQL knowledge graph augmentation, hybrid sparse/dense/ColBERT
> retrieval, cross-encoder reranking, multi-agent critic workflows, and
> vLLM-backed serving with evaluation and audit traces.

Keep the wording honest: only list features after they have code, tests, and a
demo artifact in this repository.
