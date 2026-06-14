# Glowsky — Technical Architecture Overview

## Architectural principles
1. **Separation of probabilistic and deterministic layers.** LLMs plan/explain; a deterministic, validated **Chemistry Service** computes. The agent reaches chemistry *only* through a typed tool interface.
2. **Provider-agnostic LLM access.** A single internal gateway abstracts all LLM providers (BYO-LLM). No tool or agent hard-codes a provider.
3. **Long-running, observable agent execution.** Workflows can run for minutes (generation, docking). Execution is async, streamed, resumable, and fully traced.
4. **Same core, two deployment shapes.** SaaS (multi-tenant managed) and self-hosted/VPC (single-tenant) run the *same* services; differences are config, not forks.
5. **Heavy compute is isolated & sandboxed.** RDKit, docking, ML inference, and any code execution run in isolated workers, never in the API process.

---

## System layers (high level)

```
┌──────────────────────────────────────────────────────────────────────┐
│  CLIENT (Web SPA) — IDE-style workspace                                │
│  Composer chat · 2D/3D mol viewers · library grid · notebook · diffs   │
└───────────────▲───────────────────────────────────▲───────────────────┘
                │ HTTPS / WebSocket (stream)          │
┌───────────────┴───────────────────────────────────┴───────────────────┐
│  API GATEWAY / BFF (REST + WS + GraphQL)                               │
│  auth · authz · rate-limit · request routing · streaming fan-out       │
└──┬───────────────┬──────────────────┬───────────────────┬─────────────┘
   │               │                  │                   │
┌──▼─────────┐ ┌───▼────────────┐ ┌───▼───────────────┐ ┌─▼─────────────┐
│ Core/App   │ │ Agent          │ │ LLM Gateway       │ │ RAG / Search  │
│ Service    │ │ Orchestrator   │ │ (BYO-LLM)         │ │ Service       │
│ projects,  │ │ plan→tool→     │ │ provider abstr.,  │ │ embeddings,   │
│ libs,users,│ │ synthesize,    │ │ routing, key mgmt,│ │ retrieval,    │
│ versions   │ │ tracing        │ │ cost/usage        │ │ citations     │
└──┬─────────┘ └───────┬────────┘ └─────────┬─────────┘ └──────┬────────┘
   │                   │  (typed tool calls)                   │
   │            ┌──────▼───────────────────────────────────────▼──────┐
   │            │  TASK QUEUE  +  WORKER POOL (async, sandboxed)       │
   │            │  Chemistry workers · Docking · ML/ADMET · Codegen    │
   │            └──────┬───────────────────┬───────────────┬──────────┘
   │                   │                   │               │
┌──▼───────┐  ┌────────▼──────┐  ┌─────────▼──────┐ ┌──────▼─────────┐
│ Postgres │  │ Chemistry Svc │  │ Object Storage │ │ Vector Store   │
│ (+RDKit  │  │ (RDKit core,  │  │ (S3/MinIO):    │ │ (pgvector/     │
│ cartridge│  │ predictors,   │  │ files, SDF,    │ │ Qdrant)        │
│ optional)│  │ docking wrap) │  │ PDB, reports   │ │                │
└──────────┘  └───────────────┘  └────────────────┘ └────────────────┘
        Redis (cache, queue broker, pub/sub for streaming)
```

---

## Component responsibilities

### 1. Client (Web SPA)
- IDE-style shell: Composer chat panel, multi-tab workspace, 2D editor/renderer, 3D viewer, library data-grid, notebook surface, diff views.
- Real-time updates via WebSocket (agent streaming, run progress).
- Renders structures client-side where possible; heavy depiction/coords can be server-assisted.

### 2. API Gateway / BFF
- Single entry point. AuthN/AuthZ, rate-limiting, request validation, tenant scoping.
- REST for CRUD, GraphQL optional for flexible workspace queries, **WebSocket** for streaming agent output and run progress.
- Backend-for-frontend aggregation so the SPA makes few round-trips.

### 3. Core / App Service
- Domain CRUD: users, orgs, projects, molecules, libraries, versions, hypotheses, comments, documents, templates.
- Versioning & provenance bookkeeping. Permissions/RBAC. Billing/metering hooks.

### 4. Agent Orchestrator (the brain)
- Receives an NL goal + context, plans a sequence/DAG of tool calls, executes via the tool registry, synthesizes the result, streams everything.
- **Tool registry:** typed, validated catalog (chemistry tools, predictors, docking, RAG, custom/registered tools). The LLM can only act through these schemas.
- Manages long-running runs through the task queue; supports pause/resume/step-edit; persists a full **execution trace** (plan, tool I/O, model, params, tokens).
- Hosts custom agents/skills (extensibility).

### 5. LLM Gateway (BYO-LLM)
- Unified interface over all providers (Anthropic, OpenAI, xAI, Google, Groq, Together, Mistral, Bedrock/Azure/Vertex, local Ollama/vLLM via OpenAI-compatible API).
- **Routing** by task class + per-project overrides + fallbacks. **Capability flags** (tool-use, vision, context window) gate features per model.
- **Secure key management** (encrypted, scoped, never logged). Cost/usage accounting where exposed. Streaming pass-through.

### 6. RAG / Search Service
- Ingestion (PDF/text parsing, chunking, embedding), hybrid retrieval (vector + keyword), chemistry-aware retrieval (structure similarity + text), citation assembly.
- Sources: PubMed/PMC, patents (later), user documents.

### 7. Task Queue + Worker Pool
- Async execution of all heavy/long work. Job types: chemistry ops, generation, docking, ML/ADMET inference, codegen/notebook execution, RAG ingestion.
- **Sandboxed** workers (resource limits, no ambient network for code execution, container isolation). Autoscaled by queue depth.

### 8. Chemistry Service
- The deterministic core. RDKit-backed: canonicalization, descriptors, fingerprints, substructure/similarity, alerts, conformers, enumeration.
- Wraps predictors (ADMET models), docking engines (Vina/smina/gnina), retrosynthesis (AiZynth-class), SA/SC scoring.
- Stable typed API consumed by the orchestrator's tools. Pluggable for custom/enterprise engines.

### 9. Data stores
- **Postgres** — system of record (relational domain + JSONB for flexible props). Optional **RDKit cartridge** for in-DB substructure/similarity search at scale.
- **Vector store** — pgvector (start) or Qdrant (scale) for RAG + molecular embeddings.
- **Object storage** — S3/MinIO for files (SDF, PDB, reports, notebooks, uploads).
- **Redis** — cache, queue broker, pub/sub for streaming, rate-limit counters.

---

## Key flows

### Agentic design run (e.g., "generate & filter analogs")
1. Client sends goal + `@`-context over WS → Gateway → Orchestrator.
2. Orchestrator calls **LLM Gateway** (user's routed model) to produce a **plan** of tool calls.
3. For each step, enqueues jobs to the **Worker Pool** → **Chemistry Service** (generate, validate, filter, predict, dock). Results stream back via Redis pub/sub → WS → client.
4. Orchestrator calls LLM again to **synthesize/rank/explain**; persists molecules+versions to **Core/Postgres**, files to **Object Storage**, and the full **trace** for provenance.
5. Client renders results as accept/reject cards/grid.

### BYO-LLM call
Orchestrator/tool → LLM Gateway → resolve route+key for (user/org, task class) → call provider (stream) → meter usage → return. Keys decrypted in-memory only, never logged.

### RAG query with citations
Query → RAG Service → embed → hybrid retrieve (vector+keyword, optional structure similarity) → assemble context+citations → LLM Gateway → answer with inline references → persist sources for provenance.

---

## Cross-cutting concerns
- **Observability:** structured logs, metrics, distributed tracing across gateway→orchestrator→workers; every agent run has a trace ID surfaced in the UI.
- **Provenance/reproducibility:** every generated molecule/prediction stores {tool, version, params, model, prompt-hash, timestamp, run-id}. Enables notebook export.
- **Idempotency & caching:** deterministic chemistry results cached by (input-hash, tool-version). Big win for cost and latency.
- **Multi-tenancy:** row-level tenant scoping in SaaS; single-tenant config for self-host. Same code path.
- **Security:** see `07-security-privacy.md` — key handling, data isolation, sandboxing are first-order architectural concerns, not add-ons.

## Deployment shapes
- **SaaS:** managed multi-tenant cluster (K8s), autoscaled workers, managed Postgres/object store, regional data residency options.
- **Self-hosted / VPC:** Helm chart / Docker Compose; same services; customer-controlled keys, storage, and (optionally) local LLMs. Air-gap-friendly mode (local models + no external literature calls). See `10-tech-stack.md` for stack choices and `11-folder-structure.md` for layout.
