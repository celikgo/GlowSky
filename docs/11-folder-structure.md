# Glowsky — Folder Structure & High-Level System Design

A **monorepo** (frontend + backend + shared + infra) — easiest for a small team to keep contracts in sync, share types, and ship the same images to SaaS and self-host. Tooling today: Python is packaged with pip + setuptools via `pyproject.toml` — `make venv && make install` creates `.venv313` and does an editable `pip install -e ".[dev]"`; there is no uv.lock or poetry.lock. JS is pnpm, but only inside `apps/desktop` (the repo's only `package.json`); its `pnpm-workspace.yaml` declares no `packages:` list, so this is not yet a cross-package workspace. uv/Poetry and Turborepo/Nx remain optional future upgrades — none are configured today.

**Status markers used throughout this doc:** ✅ shipped · 🟡 partial · ⏳ planned.

---

## As built today

```
glowsky/
├── README.md
├── LICENSE                        # Apache-2.0
├── Makefile                       # 21 targets (venv, install, test, run, worker, demo, …)
├── pyproject.toml                 # pip + setuptools; requires-python >=3.11,<3.14
├── .env.example                   # documents 22 of the 27 GLOWSKY_* settings — GLOWSKY_ENVIRONMENT
│                                  #   ships commented out, since unset already means production
├── alembic.ini                    # script_location = %(here)s/migrations
├── docker-compose.yml             # dev stack: redis + api + worker, SQLite, socket-free
├── docker-compose.prod.yml        # standalone: postgres + redis + migrate + api + worker
├── docker-compose.tools.yml       # overlay: mounts docker.sock, container tools ON
├── docker-compose.docking.yml     # overlay: swaps the Vina image onto api + worker
│
├── docs/                          # ← all the planning docs (this set)
├── migrations/                    # Alembic env.py + versions/ — 3 revisions, head f68490608234
│
├── apps/
│   ├── api/                       # main.py (all 38 HTTP + 3 WS routes as @app decorators),
│   │                              #   deps.py, schemas.py — that is the whole backend app
│   └── desktop/                   # Tauri 2 + React 18 + Vite client — src/ + src-tauri/
│
├── services/
│   ├── core/                      # 6 flat modules: models, db, config, auth, nakitte_auth, crypto
│   ├── agent/                     # 4 flat modules: orchestrator, tool_loop, chat, schemas
│   ├── llm_gateway/               # 6 flat modules: gateway, providers, routing, keys,
│   │                              #   credentials, types
│   ├── chemistry/                 # 14 flat modules + __init__.py, plus adapters/
│   ├── tools/                     # spec, registry, catalog, executor, … + runtimes/ + queue/
│   └── reporting/                 # markdown.py + notebook.py — run → report / notebook export
│
├── examples/
│   ├── docking/                   # 1HSG receptor + ligand PDBs for the Vina overlay
│   └── tools/                     # 5 example container tools (3 of them logistics)
│
├── infra/docker/                  # api.Dockerfile + docking.Dockerfile
├── scripts/demo.py                # end-to-end offline demo run
└── tests/                         # 26 flat test_*.py (199 test functions) + conftest.py
```

## Target layout (Phase 2/3)

The block below is the shape we grow into; entries not present in the as-built tree above are not implemented yet.

```
glowsky/
├── README.md
├── docs/                          # ← all the planning docs (this set)
├── alembic.ini                    # Alembic config (script_location = %(here)s/migrations)
├── migrations/                    # Alembic env.py + versions/ (3 revisions, linear chain)
├── docker-compose.yml             # local dev + simple self-host (+ .prod / .tools / .docking)
├── .github/workflows/             # ⏳ CI/CD (build, test, scan, deploy) — no CI in the repo today
│
├── apps/
│   ├── desktop/                   # ✅ Tauri 2 + React 18.3 + Vite 6 desktop client (ships today)
│   │   ├── src/App.tsx            # single useState<NavKey> switch — no router, no URLs
│   │   ├── src/screens/           # 8 screens: Composer, Design, Library, Docking,
│   │   │                          #   Retrosynthesis, Matched Pairs & SAR, Tools, Settings
│   │   ├── src/components/        # Sidebar, TopBar, CommandPalette (⌘K), MoleculeInspector,
│   │   │                          #   MoleculeStructure (RDKit-JS 2D), Molecule3D + DockingPose3D
│   │   │                          #   (3Dmol.js), MoleculeDepiction, KetcherEditor + modal
│   │   ├── src/lib/               # api.ts (hand-written HTTP + WebSocket client), rdkit.ts, mol3d.ts
│   │   ├── src/theme/             # tokens.css + global.css — no component library
│   │   └── src-tauri/             # 10-line Rust webview shell (lib.rs), zero #[tauri::command]
│   │
│   ├── web/                       # ⏳ (planned, SaaS) Next.js hosted SPA — not in the repo today
│   │
│   └── api/                       # ✅ FastAPI gateway/BFF (HTTP + WebSocket entrypoint)
│       ├── main.py                # 41 routes — 38 HTTP + 3 WebSocket — all as @app decorators
│       │                          #   on one FastAPI instance; no APIRouter, no include_router
│       ├── schemas.py             # 25 Pydantic request/response models
│       ├── deps.py                # DI: db sessions, current_principal / require_write, loaders
│       └── (middleware/)          # ⏳ authz, tenant-scoping, rate-limit, secret-redaction as their
│                                  #   own package — today only CORSMiddleware, added in main.py
│
├── services/                      # Python domain services (importable libs + workers)
│   ├── core/                      # ✅ domain + platform primitives (flat modules, no sub-packages)
│   │   ├── models.py              # all 12 SQLAlchemy tables in one file
│   │   ├── db.py                  # engine, SessionLocal, session_scope(), init_db()
│   │   ├── config.py              # pydantic-settings Settings: 27 env fields, env_prefix GLOWSKY_
│   │   ├── auth.py                # Principal, write-role set, seed_local_tenant(), audit()
│   │   ├── nakitte_auth.py        # RS256 platform-JWT verify (JWKS) + JIT tenant provisioning
│   │   └── crypto.py              # Fernet encrypt/decrypt/mask + fail-fast secret-key guard
│   │
│   ├── agent/                     # ✅ the orchestrator (hand-written; no agent framework)
│   │   ├── orchestrator.py        # 6-stage design loop: validate → plan (LLM) → generate
│   │   │                          #   (R-group + bioisosteres) → profile → filter/rank (MPO)
│   │   │                          #   → synthesize (LLM); emits the tool-call trace
│   │   ├── tool_loop.py           # tool-calling agent over the whole services/tools
│   │   │                          #   registry (function-calling, max_steps=6)
│   │   ├── chat.py                # Composer turn: design / chat / need-seed routing
│   │   └── schemas.py             # DesignConstraints / DesignPlan / ToolCallRecord /
│   │                              #   Candidate / DesignRunResult
│   │
│   ├── llm_gateway/               # 🟡 BYO-LLM abstraction (flat modules, no sub-packages)
│   │   ├── gateway.py             # the entrypoint the rest of the codebase calls
│   │   ├── providers.py           # LiteLLM integration (lazy import) + the offline mock
│   │   ├── routing.py             # 3 task classes (reasoning / fast_triage / codegen), overrides
│   │   ├── keys.py credentials.py # env fallback keys + per-org Fernet ciphertext, redaction
│   │   ├── types.py
│   │   └── (usage/)               # ⏳ metering/cost accounting — nothing meters tokens today
│   │
│   ├── chemistry/                 # ✅ deterministic core (RDKit) — flat, typed module API
│   │   ├── validation.py          # the safety gate: largest-fragment + uncharge,
│   │   │                          #   canonical SMILES + InChIKey
│   │   ├── properties.py fingerprints.py similarity.py search.py scaffolds.py
│   │   ├── generative.py bioisosteres.py            # reaction-SMARTS templates, not ML
│   │   ├── retrosynthesis.py synthesizability.py    # 7 retro templates + Ertl/Schuffenhauer SA score
│   │   ├── medchem.py mmp.py conformers.py io.py
│   │   └── adapters/              # Protocol seams; default backend raises BackendNotConfigured
│   │       ├── admet.py admet_rdkit.py             # GLOWSKY_ADMET_BACKEND=rdkit
│   │       ├── docking.py vina.py                  # GLOWSKY_DOCKING_BACKEND=vina
│   │       └── wiring.py                           # configure_backends() at API lifespan + worker init
│   │
│   ├── tools/                     # ✅ the typed tool subsystem (see docs/13)
│   │   ├── spec.py                # ToolSpec (17 fields), ComputeClass/LatencyClass/Determinism/
│   │   │                          #   Runtime/Egress/ToolCategory enums, Resources
│   │   ├── registry.py            # name → {version → spec} + latest pointer
│   │   ├── catalog.py             # build_default_registry() — the 22 built-ins at V = "0.1.0";
│   │   │                          #   build_registry() adds container tools only when
│   │   │                          #   GLOWSKY_ENABLE_CONTAINER_TOOLS=true and GLOWSKY_TOOLS_DIR is set
│   │   ├── executor.py            # resolve → cache → dispatch → structure firewall → provenance
│   │   ├── cache.py result.py context.py jobs.py store.py
│   │   ├── manifest.py            # glowsky-tool.yaml → ContainerToolManifest → ToolSpec
│   │   ├── runtimes/container.py  # sandboxed `docker run` ABI (JSON stdin/stdout)
│   │   └── queue/                 # celery_app.py + tasks.py — the slow path
│   │
│   ├── reporting/                 # ✅ markdown.py + notebook.py — run → report / .ipynb export
│   │
│   └── rag/                       # ⏳ (Phase 2) literature & document RAG — not implemented yet
│       ├── ingest/                # parse/chunk/embed (PDF, PubMed, patents)
│       ├── retrieval/             # hybrid vector+keyword, structure-aware
│       └── citation/              # citation assembly
│
├── packages/                      # ⏳ (planned) shared cross-language contracts
│   ├── shared-types/              # ⏳ (planned) OpenAPI-generated TS types + JSON schemas
│   └── sdk/                       # ⏳ (Phase 3) public Python SDK + plugin/custom-tool interfaces
│
├── infra/
│   └── docker/
│       ├── api.Dockerfile         # python:3.13-slim; API *and* Celery worker share this one
│       │                          #   image (different command). COPYs alembic.ini + migrations/
│       │                          #   so the prod-compose `migrate` one-shot can run
│       └── docking.Dockerfile     # opt-in: --platform=linux/amd64 + AutoDock Vina 1.2.5 + OpenBabel
│
└── tests/                         # 🟡 today: 26 flat test_*.py (199 functions, 209 collected)
    ├── chemistry/                 # ⏳ golden-set correctness suite (advisor-reviewed)
    ├── integration/               # ⏳ end-to-end agent-loop tests
    └── e2e/                       # ⏳ Playwright UI flows — the 13 vitest tests in
                                   #   apps/desktop are run only by `pnpm test`
```

---

## High-level system design notes

### Boundaries that matter
- **`chemistry/` is the deterministic firewall.** Nothing trusts an LLM-emitted structure until it passes `services/chemistry/validation.py`; the tool executor re-walks the output of any tool declaring `emits_structures=True` and rejects an invalid `smiles`. The agent reaches chemistry **only** through `services/tools/` — the typed `ToolSpec` registry (`registry.py`, populated by `catalog.py`) → the executor (`executor.py`) → typed `chemistry/` APIs. The only direct `chemistry/` imports outside that path are deterministic server-side reads of caller-supplied input — the `/molecules/*` endpoints and the orchestrator's MPO ranking — never anything the model emitted.
- **`llm_gateway/` is the only place a provider SDK is imported and the only place a stored key is decrypted.** `litellm` is imported lazily inside `LiteLLMProvider.complete` and nowhere else; `decrypt()` has exactly one call site, at the moment of use. Plaintext keys touch code outside the gateway in only two narrow spots: at entry, where `POST /settings/credentials` immediately Fernet-encrypts and masks the submitted key, and in config, where env-supplied fallback keys sit in Settings and are read only through `llm_gateway/keys.py`.
- **`tools/queue/` is where heavy/long/sandboxed work runs.** The `api/` process stays light and responsive; it enqueues and streams.
- **FE/BE contract — planned, not yet in place.** There is no `packages/` directory today and no generation step; the contract is duplicated by hand. Server side: 25 Pydantic `BaseModel` classes in `apps/api/schemas.py`. Client side: hand-written TypeScript interfaces in `apps/desktop/src/lib/api.ts` (739 lines). Nothing catches drift at build time. The planned fix is a `packages/shared-types` generated from the FastAPI OpenAPI schema.

### Why this shape
- **Services as importable libs + thin worker/api wrappers:** the same `chemistry`/`tools`/`agent`/`llm_gateway` code runs in the API (sync paths) and in workers (async paths) without duplication. Lets us split into separate deployables later (each `services/*` can become its own container/microservice) without rewrites — start as a modular monolith, scale out by extraction.
- **A hand-written orchestrator, for now:** the design loop is a fixed 6-stage sequence, so a graph engine would buy nothing today. A framework (LangGraph / Pydantic AI) is a candidate once pause/resume and durable runs are needed — see docs/10.
- **Monorepo:** keeps types, contracts, and the same images aligned across SaaS and self-host; one CI once there is one; easy refactors.
- **Extensibility-ready — and already open.** The typed tool contract (`services/tools/spec.py`) and the container-tool seam ship today. A third party packages an image speaking the tool ABI (JSON args on stdin, `{"ok": true, "result": {...}}` on stdout), drops a `glowsky-tool.yaml` under `GLOWSKY_TOOLS_DIR`, and an operator opts in with `GLOWSKY_ENABLE_CONTAINER_TOOLS=true` — off by default (GS-M3) because `docker run` needs a root-equivalent socket. The tool then runs one-shot and sandboxed via `services/tools/runtimes/container.py`, with the same cache, validation firewall, and provenance as a built-in. Five worked examples live in `examples/tools/`, three of them non-chemistry `logistics` tools. What remains for Phase 3 is `packages/sdk`, the remote-HTTP runtime, custom *agents*, and tool sharing/governance. See docs/13 §6.

### Runtime topology (deployables)
| Process | From | Scales on |
|---|---|---|
| `desktop` | apps/desktop (Tauri 2; Vite bundle embedded via `frontendDist: ../dist`) | shipped as a binary — not a server deployable |
| `api` | apps/api (`uvicorn apps.api.main:app`) | request load |
| `worker` | services/tools/queue (`celery -A services.tools.queue.celery_app worker`) — one generic pool on the `default` queue | queue depth |
| `migrate` | alembic.ini + migrations/ (`alembic upgrade head`, one-shot, prod stack only) | runs once; api + worker gate on it via `service_completed_successfully` |
| ⏳ split `worker` into `worker-cpu` / `worker-gpu` / `worker-io` pools — `task_routes` exists only as a commented example |
| ⏳ (later) split `agent`, `llm_gateway` — and `rag`, once it exists — into own services as load dictates |

`api`, `worker` and `migrate` all run the same image (`infra/docker/api.Dockerfile`), differing only in command; the `docker-compose.docking.yml` overlay swaps that image on api+worker rather than adding a separate docking pool.

Start as **modular monolith** (api + workers sharing the `services/` libs) → extract hot services in Phase 2/3. This avoids premature microservice overhead while keeping clean seams.
