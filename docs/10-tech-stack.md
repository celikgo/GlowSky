# Glowsky — Recommended Technical Stack

Each choice lists the **recommendation**, **why**, and **alternatives considered**. Bias: proven, hireable, open-source-friendly (self-host requirement), and Python-centric where chemistry demands it.

---

## Guiding constraints
- **Chemistry forces Python.** RDKit, most ADMET/generative/docking/retrosynthesis tooling, and the scientific ecosystem are Python-first. The backend that touches chemistry **must** be Python.
- **BYO-LLM forces a provider abstraction.** No provider lock-in anywhere.
- **Self-host forces open, containerizable components.** No hard dependency on a proprietary managed-only service in the core path.
- **Long-running compute forces async + workers.** Not a request/response-only design.

---

## Frontend
**Recommendation: TypeScript + React + Next.js, with a strong component system.**
- **Framework:** Next.js (React) — mature, great DX, SSR/SSG for marketing + app shell, huge hiring pool.
- **Language:** TypeScript (non-negotiable for an app this complex).
- **State/data:** TanStack Query (server state) + Zustand or Redux Toolkit (local UI state); WebSocket client for streaming.
- **UI:** Tailwind CSS + a headless component lib (shadcn/ui / Radix). IDE-like layout (resizable panels, command palette).
- **Editor surfaces:** Monaco (code/notebook cells, the same engine VS Code/Cursor use) for the "IDE feel."
- **Chemistry rendering (client):**
  - **2D:** RDKit-JS (RDKit compiled to WASM) for depiction; **Ketcher** or **JSME** for the interactive 2D editor.
  - **3D:** **Mol\*** (modern, used by RCSB) or **3Dmol.js / NGL** for molecules and protein–ligand complexes.
  - **Data grid:** AG Grid or TanStack Table for large library views.
- **Why:** maximizes "Cursor-like" ergonomics, leverages WASM RDKit for instant client-side validation/depiction, and the chemistry viz libs are best-in-class and free.
- **Alternatives:** SvelteKit/Vue (smaller ecosystems for this use case); native desktop (Electron/Tauri) — **defer**; ship web first, wrap in Tauri later if a desktop app is demanded.

---

## Backend & Agent framework
**Recommendation: Python (FastAPI) for the core/chemistry/agent services; async workers via a task queue.**
- **API framework:** **FastAPI** — async, typed (Pydantic), great performance, OpenAPI out of the box, Python (so it sits next to RDKit).
- **Agent framework:** **Pydantic AI** or **LangGraph** for the orchestrator.
  - **LangGraph** — explicit graph/state-machine control over agent steps, good for the plan→tool→synthesize DAG, pause/resume, and durable runs. Recommended for the structured, long-running workflows.
  - **Pydantic AI** — lighter, typed, plays naturally with FastAPI/Pydantic; good if we want less framework.
  - **Decision:** start with **LangGraph** for the multi-step design workflow (durability + control); keep the tool layer framework-agnostic so we can swap.
- **LLM provider abstraction:** **LiteLLM** (one interface to Anthropic/OpenAI/xAI/Google/Groq/Together/Mistral/Bedrock/Azure/Vertex + OpenAI-compatible local Ollama/vLLM), plus our thin Gateway on top for routing/keys/metering. Avoids per-provider SDK sprawl.
- **Task queue / workers:**
  - **Celery + Redis** (mature, simple) **or** **Dramatiq** **or** an orchestrator like **Temporal** for durable, observable long-running workflows.
  - **Decision:** **Celery/Redis** for MVP simplicity; evaluate **Temporal** in Phase 2 if workflow durability/retries/visibility demand it.
- **Real-time:** FastAPI WebSockets + Redis pub/sub for streaming agent tokens & job progress.
- **Why Python everywhere server-side:** keeps chemistry, ML, agents, and API in one language/runtime; avoids a cross-language RPC boundary to RDKit.
- **Alternatives considered:** Node/TS backend with a separate Python chemistry microservice — adds a network hop and two ecosystems; rejected for MVP (revisit only if a TS-heavy team demands it). Go for the gateway — fast but pulls us off Python; not worth it early.

---

## Chemistry libraries & tools
- **Core cheminformatics:** **RDKit** (Python + JS/WASM) — the foundation: canonicalization, descriptors, fingerprints, substructure/similarity, conformers, depiction, enumeration.
- **ADMET / property prediction:** **ADMET-AI** / open models; **DeepChem** for ML utilities; pluggable interface for custom/commercial models.
- **Docking:** **AutoDock Vina / smina / gnina** (gnina adds CNN scoring). Pluggable engine interface.
- **Generative design:** **REINVENT** (or similar) for ML generative; RDKit-based enumeration for analogs/R-groups; LLM-proposed ideas validated through RDKit.
- **Retrosynthesis:** **AiZynthFinder** (open) and/or external API; **SAScore/SCScore** for synthesizability.
- **Standardization:** ChEMBL structure pipeline / RDKit standardizer for normalization.
- **Why:** all open, self-hostable, scientifically credible; we wrap them behind the typed Chemistry Service so the agent calls validated tools, not raw libraries.

---

## Database & Vector store
- **Primary DB:** **PostgreSQL** — relational integrity for the domain + **JSONB** for flexible molecule properties; mature, self-hostable, managed options everywhere.
  - **RDKit Postgres cartridge** (optional) for in-DB substructure/similarity at scale (Phase 2+).
- **Vector store:** **pgvector** to start (one fewer system; fine to ~millions of chunks) → **Qdrant** (or Weaviate/Milvus) when RAG scale demands a dedicated engine.
- **Cache / broker / pub-sub:** **Redis**.
- **Object storage:** **S3** (SaaS) / **MinIO** (self-host) for SDF, PDB, poses, notebooks, reports, uploads — S3-compatible API so the same code works in both.
- **Search (optional, Phase 2+):** OpenSearch/Elasticsearch or Postgres FTS for keyword/hybrid retrieval.
- **Why:** Postgres-centric minimizes moving parts for self-host; defer specialized stores until scale justifies them.

---

## Deployment strategy (SaaS + self-hosted)
- **Containers:** Docker for everything; **same images** for SaaS and self-host.
- **Orchestration:** **Kubernetes** for SaaS (autoscaling workers by queue depth) + a **Helm chart** for enterprise self-host; **Docker Compose** for simple self-host / dev.
- **IaC:** Terraform for cloud infra; GitOps (Argo/Flux) optional.
- **Cloud:** start on one (AWS preferred for Bedrock/Secrets Manager/EKS/S3); keep cloud-agnostic via abstractions for enterprise on Azure/GCP/VPC.
- **Secrets:** AWS Secrets Manager / HashiCorp Vault (KMS-backed) — required for BYO-LLM key storage.
- **Self-host modes:** standard (their cloud), **VPC/air-gapped** (local LLM via Ollama/vLLM, MinIO, no external literature calls).
- **CI/CD:** GitHub Actions → build/test/scan → push signed images → deploy.
- **Why:** "same services, two shapes" (per architecture doc) — config-driven, no fork.

---

## LLM integration approach
- **Single internal LLM Gateway** wrapping **LiteLLM**: handles provider routing, BYO-LLM key resolution (from secrets manager), streaming, capability flags, retries/fallbacks, and usage metering.
- **Task-class routing:** `reasoning | fast_triage | codegen | embedding | vision` → model, with per-project/org overrides and fallbacks.
- **Tool use:** rely on native function/tool-calling for capable models; gate tool-use-dependent agent features on the model's capability flags (graceful degradation for weaker/local models).
- **Embeddings:** routable too (provider or local) for RAG.
- **No provider in business logic:** tools/agents call the Gateway, never an SDK directly.

---

## Observability & quality
- **Tracing/metrics/logs:** OpenTelemetry → (Grafana/Tempo/Loki or Datadog). Every agent run has a surfaced trace ID.
- **LLM observability:** Langfuse (or similar) for prompt/trace/cost analytics — works with self-host.
- **Error tracking:** Sentry.
- **Testing:** pytest (backend), Vitest/Playwright (frontend), plus a **chemistry-correctness test suite** validated by the CADD advisor (golden inputs/outputs for tools).

---

## Stack summary (one-glance)
| Layer | Choice |
|---|---|
| Frontend | TypeScript, Next.js/React, Tailwind, shadcn/Radix, Monaco, RDKit-JS, Ketcher/JSME, Mol*, TanStack |
| Backend | Python, FastAPI, Pydantic |
| Agent | LangGraph (orchestrator) + typed tool registry |
| LLM access | LiteLLM behind internal Gateway (BYO-LLM, routing, keys) |
| Workers | Celery + Redis (→ Temporal if needed) |
| Chemistry | RDKit, ADMET-AI/DeepChem, Vina/gnina, REINVENT, AiZynthFinder, SAScore |
| DB | PostgreSQL (+JSONB, optional RDKit cartridge) |
| Vector | pgvector → Qdrant |
| Storage | S3 / MinIO |
| Cache/broker | Redis |
| Deploy | Docker, K8s + Helm (SaaS + self-host), Terraform, AWS-first |
| Secrets | AWS Secrets Manager / Vault (KMS) |
| Observability | OpenTelemetry, Langfuse, Sentry |
