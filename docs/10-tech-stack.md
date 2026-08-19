# Glowsky — Recommended Technical Stack

Each choice lists the **recommendation**, **why**, and **alternatives considered**. Bias: proven, hireable, open-source-friendly (self-host requirement), and Python-centric where chemistry demands it.

**Status markers** describe what is in the repo at v0.0.1: ✅ shipped · 🟡 partial (a seam or a subset is in, the rest is not) · ⏳ planned / not started. Anything unmarked is a recommendation, not a commitment.

---

## Guiding constraints
- **Chemistry forces Python.** RDKit, most ADMET/generative/docking/retrosynthesis tooling, and the scientific ecosystem are Python-first. The backend that touches chemistry **must** be Python.
- **BYO-LLM forces a provider abstraction.** No provider lock-in anywhere.
- **Self-host forces open, containerizable components.** No hard dependency on a proprietary managed-only service in the core path.
- **Long-running compute forces async + workers.** Not a request/response-only design.

---

## Frontend
**Recommendation (as built): TypeScript + React 18 + Vite, shipped as a Tauri 2 desktop app.**
- **Shell:** Tauri 2 (`apps/desktop/src-tauri/`, crate `tauri 2.11.2`) — a Rust host around the OS webview, so binaries stay small and installs are native.
- **Framework:** React 18 + Vite 6 SPA (`apps/desktop/`, TypeScript 5.6). Navigation is a single screen-key state (`useState<NavKey>` in `src/App.tsx`) switching among 8 screens — deliberately not a router, so there are no URLs or deep links yet.
- **Language:** TypeScript (non-negotiable for an app this complex).
- **State/data:** plain React state (`useState`) + a hand-rolled typed client, `src/lib/api.ts` (739 lines, 29 methods) wrapping `fetch` and raw `WebSocket`. No server-state library yet.
- **UI:** hand-written CSS custom properties — a Twitter-"Dim" token palette in `src/theme/tokens.css` layered by `global.css` and `App.css`. Layout is a fixed sidebar + content grid with a ⌘/Ctrl+K command palette. Resizable panels are not implemented; Tailwind + shadcn/Radix remain the fallback.
- **Editor surfaces:** no code editor in-app — notebooks are generated server-side and downloaded. Monaco is deferred.
- **Chemistry rendering (client):** 2D depiction via **RDKit-JS** (`@rdkit/rdkit` 2025.3.4-1.0.0, WASM); interactive 2D editing via **Ketcher 3.15.0** (Indigo in a Web Worker). JSME was not used. 3D via **3Dmol.js ^2.5.5** (lazy-loaded) for conformers and protein–ligand poses; Mol\*/NGL were considered.
- **Data grid:** plain semantic tables today (`table.datatable`). AG Grid or TanStack Table when library views need virtualization.
- **Why:** maximizes "Cursor-like" ergonomics, leverages WASM RDKit for instant client-side validation/depiction, and the chemistry viz libs are best-in-class and free.
- **Alternatives:** Next.js (React) — the original recommendation, for SSR/SSG marketing plus an app shell; **superseded**, because the product shipped desktop-first, so it is the web/marketing surface that is deferred, not the desktop shell. SvelteKit/Vue — smaller ecosystems for this use case. Electron — bundles its own Chromium, so heavier binaries than Tauri's system-webview approach.

---

## Backend & Agent framework
**Recommendation: Python (FastAPI) for the core/chemistry/agent services; async workers via a task queue.**
- **API framework:** **FastAPI** — async, typed (Pydantic), great performance, OpenAPI out of the box, Python (so it sits next to RDKit).
- **Agent framework:** **none today** — the orchestrator is hand-written against the typed tool registry (`services/agent/`).
  - `DesignOrchestrator.run()` is a fixed six-stage design loop: validate seed → [LLM] plan → generate analogs (R-group + bioisosteric) → profile → filter/rank by MPO → [LLM] synthesize.
  - `ToolCallingAgent.run()` is a bounded native tool-calling loop (`max_steps=6` by default, then one final tool-free synthesis call) over the whole registry.
  - Both take an `emit` callback whose milestone events are relayed by the `/agent/design/stream` and `/agent/chat/stream` WebSocket endpoints.
- **Why no framework:** the plan→tool→synthesize flow is short and fixed, so a graph engine buys little today, and the tool layer stays framework-agnostic either way.
- **Revisit LangGraph / Pydantic AI when** we need durable runs, pause/resume, or branching multi-agent flows (Phase 2).
- **LLM provider abstraction:** **LiteLLM** (one interface to Anthropic/OpenAI/xAI/Google/Groq/Together/Mistral/Bedrock/Azure/Vertex + OpenAI-compatible local Ollama/vLLM), plus our thin Gateway on top for routing and key resolution (usage metering ⏳). Avoids per-provider SDK sprawl. Shipped, but Glowsky surfaces exactly **four** providers today — `anthropic`, `openai`, `groq`, `local` — plus a deterministic offline mock; the rest are LiteLLM's reach, not ours.
- **Task queue / workers:**
  - **Celery + Redis** (mature, simple) **or** **Dramatiq** **or** an orchestrator like **Temporal** for durable, observable long-running workflows.
  - **Decision ✅:** **Celery/Redis** for MVP simplicity — shipped, and eager in-process when `GLOWSKY_REDIS_URL` is unset, so the zero-dependency dev mode needs no broker. Evaluate **Temporal** in Phase 2 if workflow durability/retries/visibility demand it.
- **Real-time (milestones, not tokens):** three FastAPI WebSocket endpoints — `/agent/design/stream`, `/agent/chat/stream` and `/jobs/{id}/stream`. The agent sockets relay the orchestrator's milestone events; the job socket tails the shared append-only event log (Redis-backed when `GLOWSKY_REDIS_URL` is set, in-memory otherwise). ⏳ token-level LLM streaming and a Redis pub/sub fan-out.
- **Identity:** Glowsky is a *relying party* — it verifies platform-issued RS256 JWTs from nakitte-carbon-auth (PyJWT + a cached `PyJWKClient` against the service's JWKS, audience `carbon-platform`, optional `iss` enforcement, 30 s leeway) and never stores passwords or issues its own tokens; `/auth/login`, `/auth/refresh`, `/auth/tenants` and `/auth/select-tenant` merely proxy to carbon-auth. The token's `sub`/`tenant_id`/`roles[]` become the request principal, with roles collapsed to owner|editor|viewer, and the tenant's org/user/membership mirror JIT-provisioned.
- **Why Python everywhere server-side:** keeps chemistry, ML, agents, and API in one language/runtime; avoids a cross-language RPC boundary to RDKit.
- **Alternatives considered:** Node/TS backend with a separate Python chemistry microservice — adds a network hop and two ecosystems; rejected for MVP (revisit only if a TS-heavy team demands it). Go for the gateway — fast but pulls us off Python; not worth it early.

---

## Chemistry libraries & tools
- **Core cheminformatics ✅:** **RDKit** (Python + JS/WASM) — the foundation: canonicalization, descriptors, fingerprints, substructure/similarity, conformers, depiction, enumeration. `rdkit>=2024.3` is the *only* chemistry dependency in `pyproject.toml`; RDKit-JS, Ketcher and 3Dmol.js carry the client side.
- **ADMET / property prediction 🟡 (adapter seam):** an `ADMETBackend` Protocol whose default `NotConfiguredADMET` raises rather than guess. `GLOWSKY_ADMET_BACKEND=rdkit` wires the 7-endpoint `RDKitQSPRADMET` backend — of those, only Delaney ESOL solubility is a published regression; the other six are rule/logistic heuristics. **ADMET-AI** ships as an example sandboxed container tool (`examples/tools/admet_ai/`) — it registers as its own `admet_ai` tool when container tools are enabled, not behind the `ADMETBackend` seam. ⏳ DeepChem and custom/commercial models.
- **Docking 🟡 (adapter seam):** the same refusing default; `GLOWSKY_DOCKING_BACKEND=vina` wires the **AutoDock Vina** subprocess backend (smina works today via `GLOWSKY_VINA_BIN`). **gnina CNN scoring is not implemented.**
- **Generative design ✅ (template-based, not ML):** 10 R-group analog rules + 6 bioisostere rules + 1 aza-walk scaffold hop, all RDKit reaction SMARTS; LLM-proposed ideas are validated through RDKit, never trusted as emitted. ⏳ **REINVENT** (or similar) for ML generative.
- **Retrosynthesis ✅ (template-based):** 7 named one-step disconnections scored by an explicit heuristic building-block test (`heavy_atoms <= 12 and sa_score <= 3.5`); **SAScore** for synthesizability. ⏳ **AiZynthFinder**-class route search, external route APIs, and SCScore.
- **Standardization ✅:** RDKit `MolStandardize` — LargestFragmentChooser → Uncharger → sanitize, conservative and deterministic. ⏳ the fuller ChEMBL structure pipeline.
- **Why:** all open, self-hostable, scientifically credible; we wrap them behind the typed Chemistry Service so the agent calls validated tools, not raw libraries. The seams matter as much as the backends: `predict_admet` and `dock` are advertised to the LLM but refuse (HTTP 501) until an operator picks a backend, so Glowsky never fabricates a number it cannot compute.

---

## Database & Vector store
- **Primary DB 🟡:** **PostgreSQL** — relational integrity for the domain + JSON columns (JSONB-ready) for flexible molecule properties; mature, self-hostable, managed options everywhere. It is the production target (`docker-compose.prod.yml`) rather than the default; SQLite is what an unconfigured install gets.
  - **RDKit Postgres cartridge ⏳** (optional) for in-DB substructure/similarity at scale (Phase 2+).
- **ORM & migrations ✅:** SQLAlchemy 2.0 (`DeclarativeBase` models, portable `JSON` property bags) + Alembic; `psycopg[binary]` as the Postgres driver. The migration chain is linear — `11fad528ae5a` → `cf931554414c` → `f68490608234` (head) — across 12 tables. `tests/test_migrations.py` guards drift three ways: autogenerate-compare against `Base.metadata`, `upgrade head` → `downgrade base`, and offline render against the `postgresql+psycopg` dialect.
- **SQLite for dev/simple self-host ✅:** the default stack sets `GLOWSKY_DATABASE_URL: sqlite:////data/glowsky.db`, and a bare local process falls back to `sqlite:///glowsky.db`. `docker-compose.prod.yml` switches to `postgres:16-alpine` and gates both `api` and `worker` on a one-shot `migrate` service. Same code path, same models — only the URL changes.
- **Vector store ⏳:** **pgvector** to start (one fewer system; fine to ~millions of chunks) → **Qdrant** (or Weaviate/Milvus) when RAG scale demands a dedicated engine. No RAG path exists yet.
- **Cache / broker / pub-sub 🟡:** **Redis** — the Celery broker/backend and the cross-process job store today; the tool result cache is still in-process, and nothing uses pub/sub.
- **Object storage ⏳:** **S3** (SaaS) / **MinIO** (self-host) for SDF, PDB, poses, notebooks, reports, uploads — S3-compatible API so the same code works in both. Today those artifacts are generated on demand and streamed back, never stored.
- **Search (optional, Phase 2+) ⏳:** OpenSearch/Elasticsearch or Postgres FTS for keyword/hybrid retrieval.
- **Why:** Postgres-centric minimizes moving parts for self-host; defer specialized stores until scale justifies them.

---

## Deployment strategy (SaaS + self-hosted)
- **Containers ✅:** Docker for everything; **same images** for SaaS and self-host — two Dockerfiles in `infra/docker/` (`api`, `docking`) serve every service.
- **Orchestration 🟡:** **Docker Compose** ships for simple self-host / dev — four root files combined with `-f` overlays (dev, prod, tools, docking), not Compose `profiles:`. ⏳ **Kubernetes** for SaaS (autoscaling workers by queue depth) and a **Helm chart** for enterprise self-host.
- **IaC ⏳:** Terraform for cloud infra; GitOps (Argo/Flux) optional. Nothing is written yet.
- **Cloud ⏳:** start on one (AWS preferred for Bedrock/Secrets Manager/EKS/S3); keep cloud-agnostic via abstractions for enterprise on Azure/GCP/VPC. Nothing is deployed yet.
- **Secrets ⏳:** AWS Secrets Manager / HashiCorp Vault (KMS-backed) for BYO-LLM key storage. Today the stored provider keys are Fernet ciphertext under `GLOWSKY_SECRET_KEY` — fail-fast if unset outside dev, and no rotation path yet.
- **Self-host modes 🟡:** standard (their cloud), **VPC/air-gapped** (local LLM via Ollama/vLLM, MinIO, no external literature calls). The `local` provider covers any OpenAI-compatible Ollama/vLLM endpoint today; object storage is not wired, and there are no external literature calls to switch off yet.
- **CI/CD ⏳:** GitHub Actions → build/test/scan → push signed images → deploy. Nothing is wired yet — the repo carries no CI configuration of any kind, so `make test` on a developer machine is the only gate today.
- **Why:** "same services, two shapes" (per architecture doc) — config-driven, no fork.

---

## LLM integration approach
- **Single internal LLM Gateway ✅** wrapping **LiteLLM** (`services/llm_gateway/`): resolves the route for a task class, loads the org's BYO-LLM key, dispatches, and normalizes the response. When the routed provider has no credential it degrades to the deterministic offline mock rather than failing, so the product always runs with zero keys. ⏳ retries/fallback chains, capability flags, and usage/cost metering — token counts come back on the response but are never persisted.
- **BYO-LLM key resolution ✅:** per-org credentials stored as Fernet ciphertext (see Secrets, above) and resolved through `CredentialResolver` → `KeyStore`, with the `GLOWSKY_*_API_KEY` env values as the fallback. ⏳ a managed secrets manager behind the same interface.
- **Task-class routing ✅:** exactly **three** classes ship — `reasoning | fast_triage | codegen` — each resolving to a `provider/model` from `GLOWSKY_ROUTE_*`, overridable per org (`model_route_overrides`, edited on the Settings screen). `codegen` is routable and surfaced, but no code path issues a completion with it yet. ⏳ `embedding` and `vision` classes, per-project overrides, and fallback chains.
- **Tool use ✅:** native function/tool-calling — the registry's schemas ride the request as `tools`, and the model's `tool_calls` come back provider-agnostic, so the offline mock exercises the same loop. ⏳ capability flags to gate tool-use-dependent features (graceful degradation for weaker/local models).
- **Embeddings ⏳:** routable too (provider or local) for RAG — not built; there is no embedding route and no vector store yet.
- **No provider in business logic ✅:** tools/agents call the Gateway, never an SDK directly — no provider SDK is imported anywhere outside `services/llm_gateway/`.

---

## Observability & quality
- **Tracing/metrics/logs ⏳:** OpenTelemetry → (Grafana/Tempo/Loki or Datadog). Nothing is instrumented yet. What ships instead is an in-band, per-run tool trace: every design run returns a list of `ToolCallRecord`s (tool, version, compute class, duration, cache hit) that the desktop renders beside the result.
- **LLM observability ⏳:** Langfuse (or similar) for prompt/trace/cost analytics — works with self-host.
- **Error tracking ⏳:** Sentry.
- **Testing 🟡:** pytest for the backend — 199 test functions across 26 files (209 collected, the delta being parametrize expansion) — and Vitest for the desktop — 13 tests across 5 files, run by `pnpm test` from `apps/desktop/`, which no Makefile target invokes. Chemistry correctness is covered by known-molecule assertions per module (`tests/test_chemistry.py`, `test_retrosynthesis.py`, `test_mmp.py`, …). ⏳ Playwright end-to-end coverage and a CADD-advisor-signed golden set.

---

## Stack summary (one-glance)
| Layer | Choice | Status (v0.0.1) |
|---|---|---|
| Frontend | TypeScript, React 18 + Vite 6 in a Tauri 2 shell, hand-written CSS tokens, RDKit-JS, Ketcher 3.15, 3Dmol.js | ✅ shipped |
| Backend | Python, FastAPI, Pydantic | ✅ shipped |
| Agent | hand-written orchestrator + bounded tool-calling loop over the typed tool registry (LangGraph/Pydantic AI deferred) | ✅ shipped |
| Auth / identity | External **nakitte-carbon-auth** RS256 JWTs verified with PyJWT + cached JWKS; JIT org/user/membership provisioning; no local credential store | ✅ shipped |
| LLM access | LiteLLM behind internal Gateway (BYO-LLM, routing, keys) | ✅ shipped — four providers (`anthropic`, `openai`, `groq`, `local`) + an offline mock; usage/cost metering ⏳ |
| Workers | Celery + Redis (→ Temporal if needed) | ✅ shipped — eager in-process when `GLOWSKY_REDIS_URL` is unset |
| Chemistry | RDKit (Python + RDKit-JS); ADMET & docking behind adapter seams — RDKit-QSPR + Vina shipped, ADMET-AI as a container tool; template-based generative/retrosynthesis; SAScore. REINVENT/AiZynthFinder/gnina/SCScore planned | 🟡 partial |
| Tool sandbox | Docker one-shot `docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --network none --tmpfs /tmp:rw,size=256m --user 65534:65534` (plus per-manifest `--memory`/`--cpus`) + `glowsky-tool.yaml` manifests, one-JSON-object stdin/stdout ABI — opt-in via `GLOWSKY_ENABLE_CONTAINER_TOOLS` + `GLOWSKY_TOOLS_DIR` | ✅ shipped |
| DB | PostgreSQL (+JSON property bags, optional RDKit cartridge) | 🟡 SQLAlchemy 2.0 + Alembic shipped; SQLite is the default, Postgres 16 only in `docker-compose.prod.yml`; cartridge not started |
| Vector | pgvector → Qdrant | ⏳ not started |
| Storage | S3 / MinIO | ⏳ not started |
| Cache/broker | Redis | 🟡 Celery broker/backend + shared job store shipped; the result cache is still in-process |
| Config | pydantic-settings, all env-driven under the `GLOWSKY_` prefix (27 settings) | ✅ shipped |
| Deploy | Docker, K8s + Helm (SaaS + self-host), Terraform, AWS-first | 🟡 Docker Compose shipped (4 root files over 2 Dockerfiles in `infra/docker/`); Kubernetes, Helm, Terraform and GitOps not started |
| Secrets at rest | **Shipped:** cryptography/Fernet over `GLOWSKY_SECRET_KEY` for stored BYO-LLM keys (fail-fast if unset outside dev). **Planned:** AWS Secrets Manager / Vault (KMS) | 🟡 partial |
| Observability | OpenTelemetry, Langfuse, Sentry | ⏳ not started |

*Status is as of v0.0.1. Rows marked "not started" are recommendations, not commitments; where Status contradicts Choice, Status is authoritative.*
