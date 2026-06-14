# Glowsky — Folder Structure & High-Level System Design

A **monorepo** (frontend + backend + shared + infra) — easiest for a small team to keep contracts in sync, share types, and ship the same images to SaaS and self-host. Tooling: pnpm workspaces (JS) + uv/Poetry (Python); Turborepo/Nx optional.

```
glowsky/
├── README.md
├── docs/                          # ← all the planning docs (this set)
├── docker-compose.yml             # local dev + simple self-host
├── .github/workflows/             # CI/CD (build, test, scan, deploy)
│
├── apps/
│   ├── web/                       # Next.js frontend (the IDE-style workspace)
│   │   ├── app/                   # routes (App Router): /workspace, /projects, /settings, marketing
│   │   ├── components/
│   │   │   ├── composer/          # sidebar chat, streaming, tool-call viz, @-mentions
│   │   │   ├── molecule/          # 2D editor (Ketcher/JSME), 2D render (RDKit-JS), diff
│   │   │   ├── viewer3d/          # Mol*/3Dmol protein-ligand & conformer views
│   │   │   ├── library/           # data-grid, property columns, filters
│   │   │   ├── notebook/          # Monaco-based notebook/code surface
│   │   │   └── ui/                # shadcn/Radix primitives, layout/panels, command palette
│   │   ├── lib/                   # api client, ws client, hooks, model-routing UI logic
│   │   └── stores/                # Zustand/RTK state
│   │
│   └── api/                       # FastAPI gateway/BFF (HTTP + WebSocket entrypoint)
│       ├── main.py
│       ├── routers/               # auth, projects, molecules, libraries, agent, llm, rag, billing, admin
│       ├── middleware/            # authz, tenant-scoping, rate-limit, secret-redaction
│       ├── ws/                    # streaming endpoints (agent tokens, job progress)
│       └── deps.py                # DI: db sessions, current-user/org, services
│
├── services/                      # Python domain services (importable libs + workers)
│   ├── core/                      # domain: users/orgs/projects/molecules/versions/hypotheses
│   │   ├── models/                # SQLAlchemy ORM + Pydantic schemas
│   │   ├── repositories/          # data access
│   │   ├── services/              # business logic (projects, versioning, provenance, RBAC)
│   │   └── migrations/            # Alembic
│   │
│   ├── agent/                     # the orchestrator (LangGraph)
│   │   ├── graph/                 # plan→tool→synthesize state machine, pause/resume
│   │   ├── registry/             # typed tool registry (schemas, validation, discovery)
│   │   ├── tools/                 # tool adapters → chemistry/rag/docking/custom
│   │   ├── tracing/               # execution trace persistence (AgentRun/Step)
│   │   └── prompts/               # system prompts, templates
│   │
│   ├── llm_gateway/               # BYO-LLM abstraction
│   │   ├── providers/             # LiteLLM integration, capability flags
│   │   ├── routing/               # task-class routing, overrides, fallbacks
│   │   ├── keys/                  # secrets-manager integration, encryption, redaction
│   │   └── usage/                 # metering/cost accounting
│   │
│   ├── chemistry/                 # deterministic core (RDKit + wrappers) — typed tool API
│   │   ├── rdkit_ops/             # canonicalize, descriptors, fingerprints, alerts, conformers
│   │   ├── generative/            # analog/R-group enum, scaffold hop, REINVENT adapter
│   │   ├── prediction/            # ADMET/physchem predictors (pluggable)
│   │   ├── docking/               # Vina/smina/gnina wrappers, pocket handling
│   │   ├── retrosynth/            # AiZynth adapter, SA/SC scoring
│   │   └── validation/            # structure validation/standardization (the safety gate)
│   │
│   ├── rag/                       # literature & document RAG
│   │   ├── ingest/                # parse/chunk/embed (PDF, PubMed, patents)
│   │   ├── retrieval/             # hybrid vector+keyword, structure-aware
│   │   └── citation/              # citation assembly
│   │
│   └── workers/                   # Celery app + task definitions (wrap the above for async)
│       ├── celery_app.py
│       └── tasks/                 # generation, docking, prediction, ingest, codegen
│
├── packages/                      # shared cross-language contracts
│   ├── shared-types/              # OpenAPI-generated TS types + JSON schemas (single source of truth)
│   └── sdk/                       # (Phase 3) public Python SDK + plugin/custom-tool interfaces
│
├── infra/
│   ├── terraform/                 # cloud infra (SaaS)
│   ├── helm/                      # enterprise self-host chart
│   ├── docker/                    # Dockerfiles (api, workers w/ chemistry deps, web)
│   └── self-host/                 # compose + air-gapped config + hardening guide
│
└── tests/
    ├── chemistry/                 # golden-set correctness suite (advisor-reviewed)
    ├── integration/               # end-to-end agent-loop tests
    └── e2e/                       # Playwright UI flows
```

---

## High-level system design notes

### Boundaries that matter
- **`chemistry/` is the deterministic firewall.** Nothing trusts an LLM-emitted structure until it passes `chemistry/validation/`. The agent reaches chemistry **only** through `agent/registry` → `agent/tools` → typed `chemistry/` APIs.
- **`llm_gateway/` is the only place a provider SDK/key is touched.** Keys decrypt in-memory here and nowhere else. Business logic never imports a provider.
- **`workers/` is where heavy/long/sandboxed work runs.** The `api/` process stays light and responsive; it enqueues and streams.
- **`packages/shared-types`** is the single source of truth for the FE/BE contract (generate TS from OpenAPI/Pydantic) — prevents drift in a fast-moving product.

### Why this shape
- **Services as importable libs + thin worker/api wrappers:** the same `chemistry`/`agent`/`llm_gateway` code runs in the API (sync paths) and in workers (async paths) without duplication. Lets us split into separate deployables later (each `services/*` can become its own container/microservice) without rewrites — start as a modular monolith, scale out by extraction.
- **Monorepo:** keeps types, contracts, and the same images aligned across SaaS and self-host; one CI; easy refactors.
- **Extensibility-ready:** `agent/registry` (typed tool contract) + `packages/sdk` are the seams where Phase-3 custom tools/agents plug in — designed now, exposed later.

### Runtime topology (deployables)
| Process | From | Scales on |
|---|---|---|
| `web` | apps/web | CDN/edge + a few replicas |
| `api` | apps/api | request load |
| `worker-chem` | services/workers (+chemistry deps) | queue depth (CPU-bound) |
| `worker-dock` | services/workers (heavy) | queue depth (CPU/GPU) |
| (later) split `agent`, `rag`, `llm_gateway` into own services as load dictates |

Start as **modular monolith** (api + workers sharing the `services/` libs) → extract hot services in Phase 2/3. This avoids premature microservice overhead while keeping clean seams.
