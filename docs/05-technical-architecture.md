# Glowsky — Technical Architecture Overview

> **Status legend.** This document describes the **target** architecture, not what is built today. ✅ shipped · 🟡 partial · ⏳ planned; inline, *(planned)* means ⏳ — no code in the repo.
> **✅ Shipped in this repo:** Tauri desktop client, FastAPI API/BFF with REST + WebSocket, Core/App service, Agent Orchestrator, LLM Gateway, Celery + Redis task queue and workers, the deterministic chemistry layer as an **in-process package** with container/Vina/ADMET adapters, SQLite by default with Postgres in `docker-compose.prod.yml`, Redis, and reproducible notebook/Markdown **export**.
> **⏳ Not built yet — no code in the repo:** the RAG / Search service (no `services/rag/`), the vector store (no pgvector or Qdrant usage), object storage (no S3/MinIO client or dependency), GraphQL, and codegen / notebook **execution** (`TaskClass.CODEGEN` is routable and overridable but no code path ever sends a completion with it). Kubernetes/Helm deployment is also absent: the repo ships Docker Compose files and `infra/docker/*.Dockerfile` only. Items marked *(planned)* below have no code in the repo.

## Architectural principles
1. **Separation of probabilistic and deterministic layers.** LLMs plan/explain; a deterministic, validated **Chemistry Service** computes. The agent reaches chemistry *only* through a typed tool interface.
2. **Provider-agnostic LLM access.** A single internal gateway abstracts all LLM providers (BYO-LLM). No tool or agent hard-codes a provider.
3. **Long-running, observable agent execution.** Workflows can run for minutes (generation, docking). Execution is async, streamed, and fully traced today; durable/resumable runs are *planned* (Temporal in Phase 2 — see `10-tech-stack.md`).
4. **Same core, two deployment shapes.** SaaS (multi-tenant managed) and self-hosted/VPC (single-tenant) run the *same* services; differences are config, not forks.
5. **Heavy compute is isolated & sandboxed.** RDKit, docking, ML inference, and any code execution belong in isolated workers, never in the API process. *Today:* `POST /tools/{name}` runs every tool inline on the request thread regardless of compute class — work leaves the request thread only via `POST /jobs` / `POST /jobs/batch` onto Celery workers, and true sandboxing exists only for container tools (§7).

---

## System layers (high level)

```
┌───────────────────────────────────────────────────────────────────────┐
│  CLIENT (Tauri desktop) — IDE-style workspace                         │
│  Composer chat · 2D/3D mol viewers · library grid · ⌘K palette        │
└───────────────▲───────────────────────────────────▲───────────────────┘
                │ HTTPS / WebSocket (stream)        │
┌───────────────┴───────────────────────────────────┴───────────────────┐
│  API GATEWAY / BFF (REST + WS; GraphQL planned)                       │
│  auth · authz · rate-limit · request routing · streaming fan-out      │
└──┬───────────────┬──────────────────┬───────────────────┬─────────────┘
   │               │                  │                   │
┌──▼─────────┐ ┌───▼────────────┐ ┌───▼───────────────┐ ┌─▼─────────────┐
│ Core/App   │ │ Agent          │ │ LLM Gateway       │ │ RAG / Search  │
│ Service    │ │ Orchestrator   │ │ (BYO-LLM)         │ │ Svc (planned) │
│ projects,  │ │ plan→tool→     │ │ provider abstr.,  │ │ embeddings,   │
│ libs,users,│ │ synthesize,    │ │ routing, key mgmt,│ │ retrieval,    │
│ versions   │ │ tracing        │ │ cost/usage        │ │ citations     │
└──┬─────────┘ └───────┬────────┘ └─────────┬─────────┘ └──────┬────────┘
   │                   │  (typed tool calls)                   │
   │            ┌──────▼───────────────────────────────────────▼──────┐
   │            │  TASK QUEUE  +  WORKER POOL (async, sandboxed)      │
   │            │  Chemistry workers · Docking · ML/ADMET             │
   │            └──────┬───────────────────┬───────────────┬──────────┘
   │                   │                   │               │
┌──▼───────┐  ┌────────▼──────┐  ┌─────────▼──────┐ ┌──────▼─────────┐
│ Postgres │  │ Chemistry Svc │  │ Object Storage │ │ Vector Store   │
│ (+RDKit  │  │ (RDKit core,  │  │ (planned):     │ │ (planned):     │
│ cartridge│  │ predictors,   │  │ S3/MinIO —     │ │ pgvector/      │
│ planned) │  │ docking wrap) │  │ files, reports │ │ Qdrant         │
└──────────┘  └───────────────┘  └────────────────┘ └────────────────┘
     Redis (Celery broker + result backend, shared job store)
```

---

## Component responsibilities

### 1. Client (Tauri desktop app today; web SPA planned)
- Ships today as a Tauri 2 shell around a React 18 + Vite build (`apps/desktop/`): 8 screens selected by local component state — Composer, Design, Library, Docking, Retrosynthesis, Matched Pairs & SAR, Tools, Settings — plus a ⌘K command palette and a molecule-inspector overlay. There is no router, so no deep links. *Planned:* browser SPA, multi-tab workspace, in-app notebook surface, diff views (runs export to `.ipynb`/Markdown today via `GET /runs/{run_id}/export`; `POST /molecules/diff` exists server-side but is not surfaced in the UI).
- Real-time updates via WebSocket (agent streaming, run progress).
- Structures render client-side: 2D depiction via RDKit-JS (WASM) and interactive 2D editing via Ketcher; 3D via 3Dmol.js. 3D coordinates are server-assisted through `POST /molecules/conformer`.

### 2. API Gateway / BFF
- Single entry point. AuthN/AuthZ, request validation, tenant scoping; rate-limiting *(planned — no rate-limit code exists, see `07-security-privacy.md` §7)*.
- REST for CRUD, GraphQL *(planned)* for flexible workspace queries, **WebSocket** for streaming agent output and run progress.
- Backend-for-frontend aggregation so the client makes few round-trips.

### 3. Core / App Service
- Domain CRUD: users, orgs, projects, molecules, libraries, versions, hypotheses, comments, documents, templates.
- Versioning & provenance bookkeeping. Permissions/RBAC. Billing/metering hooks.
- *Shipped today:* 12 SQLAlchemy tables (orgs, users, memberships, api_keys, projects, libraries, library memberships, provider credentials, route overrides, audit events, molecules, agent runs) — no molecule versions, hypotheses, comments, documents or templates yet, and no billing/metering.

### 4. Agent Orchestrator (the brain)
- Receives an NL goal + context and executes it two ways today. (1) A **fixed 6-stage design pipeline**: validate seed → LLM plan → generate analogs (`generate_analogs` + `bioisosteric_replacement`) → `profile_molecule` per analog → filter against the plan's constraints and rank by MPO desirability → LLM synthesis. Exactly two LLM calls; the model only fills in `max_analogs` and the constraint numbers — the tool sequence is hard-coded. (2) A **tool-calling loop**: the *entire* registry is offered with `tool_choice="auto"` for at most 6 model turns, then a final tools-disabled synthesis call. `POST /agent/design` always runs (1); on the Composer path (`POST /agent/chat`) the choice between the two is a deterministic keyword heuristic (`looks_like_design`, `services/agent/chat.py`), never the model's. *Planned:* free-form sequence/DAG planning.
- **Tool registry:** typed, validated catalog (chemistry tools, predictors, docking, RAG *(planned)*, custom/registered tools). The LLM can only act through these schemas.
- Manages long-running runs through the task queue: `POST /jobs` and `POST /jobs/batch`, polled via `GET /jobs/{id}` and streamed live over `WS /jobs/{id}/stream` (status `queued|running|completed|failed`; the event stream adds `progress` and per-item `item` events). Persists a full **execution trace**. *Planned:* pause/resume/step-edit and cancellation — there is no cancel endpoint and no checkpointing today.
- Extensibility today is the tool layer: 22 typed built-in tools plus opt-in container tools discovered from `glowsky-tool.yaml` manifests (§7). *Planned:* custom agents/skills and a tool SDK.
- See `13-chemistry-tools-architecture.md` §2–§4 for the tool contract, registry and execution path the orchestrator calls through.

### 5. LLM Gateway (BYO-LLM)
- Unified interface over providers via **LiteLLM**. Shipped today: **Anthropic, OpenAI, Groq, and any OpenAI-compatible `local` endpoint** — the same four ids the settings API accepts. A route naming a provider with no credentials resolves to the built-in **offline mock** rather than erroring. *Planned:* xAI, Google, Together, Mistral, Bedrock/Azure/Vertex.
- **Routing** by task class (`reasoning | fast_triage | codegen`), with per-**org** overrides (`ModelRouteOverride`, unique per org+task_class) layered over env defaults (`GLOWSKY_ROUTE_REASONING` / `_FAST_TRIAGE` / `_CODEGEN`, each defaulting to `mock/mock`). *Planned:* per-project overrides, provider fallback chains, and **capability flags** gating features per model.
- **Secure key management** — org BYO keys stored Fernet-encrypted (`GLOWSKY_SECRET_KEY`, which a boot-time guard makes mandatory unless `GLOWSKY_ENVIRONMENT` names a dev tier), decrypted only at call time, never logged, only a masked hint ever returned. *Planned:* cost/usage accounting (provider token counts are returned on `CompletionResponse.usage` but never metered or persisted) and streaming pass-through — the gateway exposes only `complete()`, so the WebSocket carries run milestone events, not model tokens.

### 6. RAG / Search Service *(planned — not implemented)*
- Ingestion (PDF/text parsing, chunking, embedding), hybrid retrieval (vector + keyword), chemistry-aware retrieval (structure similarity + text), citation assembly.
- Sources: PubMed/PMC, patents (later), user documents.

### 7. Task Queue + Worker Pool
- Async execution of all heavy/long work. Job types: chemistry ops, generation, docking, ML/ADMET inference, codegen/notebook execution *(planned)*, RAG ingestion *(planned)*.
- Workers are Celery/Redis processes (in-process eager when `GLOWSKY_REDIS_URL` is unset). Autoscaling by queue depth and per-worker resource limits are *planned*; today isolation is enforced per-tool by the container runtime below, not by the worker pool.
- **Container tool runtime (shipped):** third-party tools ship as an OCI image plus a `glowsky-tool.yaml` manifest and speak a one-shot JSON stdin/stdout ABI — the image reads a JSON args object on stdin and writes `{"ok": true, "result": {...}}` on stdout. Every invocation is `docker run --rm --interactive --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --memory {mem_mb}m --cpus {cpu} --tmpfs /tmp:rw,size=256m --network none [--gpus N] [--user 65534:65534] -- {image}`, with resources from the manifest and the image ref after a `--` terminator. The manifest's `timeout_s` is enforced runner-side as a hard wall-clock kill. Egress is fail-closed: an `egress: allowlist` manifest still gets `--network none`. Registration is opt-in behind **both** `GLOWSKY_ENABLE_CONTAINER_TOOLS=true` and `GLOWSKY_TOOLS_DIR` (both off by default); the root-equivalent `/var/run/docker.sock` mount they require is added only by `docker-compose.tools.yml`, and `docker-compose.prod.yml` ships container tools off. See `13-chemistry-tools-architecture.md` §6.
- Execution architecture and caching: `13-chemistry-tools-architecture.md` §4; runtimes and the Tool SDK: §6.

### 8. Chemistry Service
- The deterministic core. RDKit-backed: canonicalization, descriptors, fingerprints, substructure/similarity, alerts, conformers, enumeration.
- Wraps predictors (ADMET models), docking engines (Vina/smina/gnina), retrosynthesis (AiZynth-class), SA/SC scoring.
- Stable typed API consumed by the orchestrator's tools. Pluggable for custom/enterprise engines.
- *Shipped today:* an in-process package (`services/chemistry/`) with **zero ML dependencies** — `rdkit>=2024.3` is the only chemistry dep; generation, bioisosteres and retrosynthesis are template/heuristic, not learned. The predictor and docking wrappers are adapter seams: `predict_admet` and `dock` are gated behind `GLOWSKY_ADMET_BACKEND` / `GLOWSKY_DOCKING_BACKEND` (both default `none` → HTTP 501). See `13-chemistry-tools-architecture.md` §10 for the 22-tool catalog.

### 9. Data stores
- **Postgres** — system of record in the production stack (`docker-compose.prod.yml`: `postgres:16-alpine` plus a `migrate` one-shot running `alembic upgrade head`). The default dev/self-host stack points the same `GLOWSKY_DATABASE_URL` at **SQLite** over the same SQLAlchemy models — 12 tables today, with portable `JSON` columns (not JSONB). On the dev path the schema is created by `Base.metadata.create_all`; Alembic is the source of truth for schema evolution and runs against either backend. Optional **RDKit cartridge** *(planned — no cartridge code today)*.
- **Vector store** *(planned)* — nothing exists yet: no vector-store dependency, no embedding or retrieval code, no RAG/Search service.
- **Object storage** *(planned)* — today files travel inline: imports take file content in the request body, exports serialize on the fly into a `PlainTextResponse`, and MOL blocks are returned in tool payloads. Nothing is persisted as a blob.
- **Redis** — Celery broker + result backend and the shared job store (`RedisJobStore`: job hash + append-only event list, 24 h TTL). Optional: with `GLOWSKY_REDIS_URL` unset, Celery runs eager in-process against an `InMemoryJobStore`. Streaming does **not** use pub/sub — the `/jobs/{id}/stream` WebSocket tails the append-only event log by index. *Planned:* a Redis (hot) tier for the result cache, which is in-process today, plus pub/sub streaming and rate-limit counters.

---

## Key flows

### Agentic design run (e.g., "generate & filter analogs")
1. Client sends goal + `@`-context over WS → Gateway → Orchestrator.
2. Orchestrator calls **LLM Gateway** (user's routed model) to produce a **plan** of tool calls.
3. For each stage it invokes the **Chemistry Service** through the tool executor (generate, validate, filter, predict, dock) — inline on the run's own task today, with the Worker Pool reserved for `POST /jobs` submissions. Milestones stream back over the run WebSocket → client.
4. Orchestrator calls LLM again to **synthesize/rank/explain**; persists molecules and the full **trace** to **Core/Postgres** (`molecules`, `agent_runs`). *Planned:* molecule versions and files to **Object Storage**.
5. Client renders results as accept/reject cards/grid.

### BYO-LLM call
Orchestrator/tool → LLM Gateway → resolve route+key for (user/org, task class) → call provider (stream *(planned)*) → meter usage *(planned)* → return. Keys decrypted in-memory only, never logged.

### RAG query with citations *(planned)*
Query → RAG Service → embed → hybrid retrieve (vector+keyword, optional structure similarity) → assemble context+citations → LLM Gateway → answer with inline references → persist sources for provenance.

---

## Cross-cutting concerns
- **Observability:** *(planned)* structured logs, metrics and distributed tracing across gateway→orchestrator→workers — the repo carries no logging, OpenTelemetry or metrics dependency today. What ships instead is the **execution trace**: every design run returns a per-step `ToolCallRecord` list that the Composer and Design screens render, and a `run_id` the client uses to pull the run's export.
- **Provenance/reproducibility:** every tool execution returns an `ExecutionRecord` — `{tool, version, compute_class, determinism, env_digest, input_hash, cache_hit, duration_ms, seed?, error?}` — carried on the `ToolResult` and folded into `AgentRun.trace`. That is what makes notebook export reproducible. *Planned:* `run_id`, worker identity and timestamps on the record itself (see `13-chemistry-tools-architecture.md` §5).
- **Caching:** deterministic tool results are cached content-addressed by `sha256(tool, version, env_digest, org_id, args, seed)` — **tenant-scoped**, because an input structure is itself IP. Tools declaring `cacheable` with `determinism = deterministic` cache on input; `seeded` tools cache on (input, seed); `nondeterministic` tools are never cached. Today the cache is an in-process dict private to each API/worker process, with no eviction or TTL (`result_cache_max` is declared in config but not wired up); *planned:* shared Redis (hot) + object storage (cold).
- **Idempotency** *(planned)*: job submission mints a fresh UUID per request, so a client retry of `POST /jobs` runs the tool twice; idempotency keys are on the roadmap.
- **Multi-tenancy:** app-layer tenant scoping — every query filters on `org_id` and cross-tenant reads return 404, never 403. There is no Postgres row-level security. Single-tenant config for self-host; same code path.
- **Security:** see `07-security-privacy.md` — key handling, data isolation, sandboxing are first-order architectural concerns, not add-ons.

## Deployment shapes
- **SaaS:** managed multi-tenant cluster (K8s) *(planned)*, autoscaled workers, managed Postgres/object store, regional data residency options.
- **Self-hosted / VPC:** Docker Compose today; Helm chart *(planned)*. Same services; customer-controlled keys, storage, and (optionally) local LLMs. Air-gap-friendly mode (local models + no external literature calls).

See also: `13-chemistry-tools-architecture.md` for the tool contract (§2), registry (§3), execution architecture and caching (§4), provenance record (§5), runtimes and Tool SDK (§6) and the tool catalog (§10); `10-tech-stack.md` for stack choices; `11-folder-structure.md` for layout.
