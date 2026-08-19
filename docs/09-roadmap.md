# Glowsky — Development Roadmap

Phased plan. Durations are indicative for a small team (≈3–6 engineers + 1 chemistry/CADD advisor); compress with more people. Each phase ends with a clear, demoable milestone and a "definition of done."

> **Status (August 2026).** This roadmap is the plan of record: the plan prose stays in the future tense, and the status markers and italic notes record what the repo actually contains today. Much of Phases 0–1 has since shipped: a FastAPI backend plus a Tauri desktop client with 8 screens — Composer, Design, Library, Docking, Retrosynthesis, Matched Pairs & SAR, Tools, Settings.
>
> **Shipped.** Phase 0's definition of done works end to end: `services/agent/orchestrator.py` runs the 6-stage design loop, with runs and generated molecules persisted as `AgentRun`/`Molecule`. Also shipped: 22 built-in tool specs; Composer chat over WebSocket; library SMILES/CSV/SDF import & export plus `/molecules/diff`; Jupyter-notebook + Markdown run export; the Celery slow path with WebSocket job progress; multi-tenant auth with org/project scoping and Fernet-encrypted BYO-LLM credentials at rest.
>
> **Not yet delivered from Phase 0/1.** CI/CD pipelines and an IaC baseline (`infra/` holds only two Dockerfiles). An external secrets manager / KMS. Object storage. A vector store. Molecule versioning. LLM **token-level** streaming — the gateway exposes only `complete()`; the WebSockets stream milestones, not tokens. Telemetry. Tool-call trace visualisation in Composer. Property-delta diff cards with an explicit reject — accepting a candidate today is an explicit *Save to library*. `predict_admet` and `dock` are registered but **adapter-gated and off by default**.
>
> **Landed early from Phases 2–3.** MPO scoring, retrosynthesis + SA score, bioisosteres / scaffold hopping, MMP-based SAR mining, the model-routing UI (cost/usage visibility still pending), and the opt-in container-tool extensibility seam.

**Status legend:** ✅ shipped · 🟡 partial · ⏳ planned. Markers below describe what exists in the repo today; everything unmarked is still the plan.

---

## 🟡 Phase 0 — Foundation & Architecture *(~4–6 weeks)*
*Definition of done met; the infra, data-layer and security-baseline workstreams are partially outstanding.*

**Objective:** de-risk the hard parts, set up the skeleton, prove the two scariest integrations (BYO-LLM gateway + deterministic chemistry-as-tools).

**Workstreams**
- 🟡 **Repo & infra scaffold:** monorepo, CI/CD, containerized dev env, IaC baseline, secrets manager wired. *(Monorepo ✅ and the containerized dev env ✅ — four root Compose files over two Dockerfiles in `infra/docker/`. ⏳ Still open: CI/CD — there is no CI configuration of any kind in the repo — an IaC baseline, and an external secrets manager; BYO-LLM keys are Fernet ciphertext under `GLOWSKY_SECRET_KEY`, not KMS-backed.)*
- 🟡 **LLM Gateway spike:** unified provider interface (LiteLLM-class) + streaming + one secure key flow across 2 providers + 1 local (Ollama). Capability flags + basic routing. *(Shipped ✅ over LiteLLM for exactly four providers — `anthropic`, `openai`, `groq` and `local` (an OpenAI-compatible base URL for Ollama/vLLM) — plus an offline mock, with per-org encrypted keys and per-org routing across the three task classes `reasoning`, `fast_triage` and `codegen` (`codegen` is routable but no code path issues a completion with it yet). ⏳ Still open: streaming — the gateway exposes only `complete()`.)*
- ✅ **Chemistry Service spike:** RDKit worker behind a typed tool API (canonicalize, descriptors, enumerate analogs). Job queue + worker isolation proven. *(22 built-in tools behind the frozen `ToolSpec` contract, with Celery + Redis carrying the slow path. One caveat: `POST /tools/{name}` runs the handler on the request thread whatever the tool's compute class — work leaves that thread only through `POST /jobs` / `POST /jobs/batch`.)*
- ✅ **Agent orchestrator spike:** LLM plans a 2–3 step tool sequence, executes via the registry, streams results. Trace persisted. *(A hand-written orchestrator — no LangGraph, no agent framework: a fixed 6-stage loop making exactly two LLM calls, plus a bounded tool-calling loop (`max_steps=6`) for chat turns, with the tool trace persisted on `AgentRun`. The WebSockets stream milestones, not tokens.)*
- 🟡 **Data layer:** Postgres schema v0 (orgs/users/projects/molecules/versions/runs), object storage, vector store provisioned. *(12 SQLAlchemy tables over a linear 3-revision Alembic chain, head `f68490608234` — but SQLite is the default (`sqlite:///glowsky.db`) and Postgres 16 appears only in `docker-compose.prod.yml`. ⏳ Still open: molecule versioning, object storage and a vector store.)*
- 🟡 **Security baseline:** KMS key storage, tenant scoping, TLS, authz middleware, audit skeleton. *(Tenant scoping ✅ — `org_id` filters, 404 never 403 across orgs — authz middleware ✅ on 30 of the 38 HTTP routes (12 `require_write`, 18 `current_principal`), and an audit skeleton ✅ — `audit_events` rows on eight mutating actions, with no export or viewer. ⏳ Still open: KMS key storage — keys are Fernet ciphertext under `GLOWSKY_SECRET_KEY` with no rotation path — TLS, which nothing in the repo terminates, and stronger-than-app-layer isolation: there is no Postgres row-level security.)*

**Definition of done:** a thin vertical slice — "paste SMILES → ask the agent (using *your* key) to make 5 analogs → validated structures returned & stored" — works end-to-end in dev.

**Key decisions locked:** stack (see `10`), tool-registry contract, provenance schema, deployment shape.

---

## 🟡 Phase 1 — MVP (Core Experience) *(~10–14 weeks)*
*The design loop, library and export paths are live end to end; the agent's trace/diff UI, telemetry and beta hardening are outstanding, and the ADMET and docking backends still refuse until an operator wires them.*

**Objective:** ship the complete agentic design loop with BYO-LLM, polished enough for Maya (and usable by David). Closed beta with design partners.

**Build (per `08` MVP list):**
- ✅ Auth + org/project model; onboarding to connect an LLM key. *(Identity is delegated to nakitte-carbon-auth — RS256 JWTs, with Organization/User/Membership rows JIT-provisioned from the token. Sign-in and BYO-LLM key connection both live in the Settings screen rather than a guided first-run flow.)*
- ✅ Molecule import/paste/edit (2D editor), RDKit validation, 2D render, 3D single-molecule view. *(Ketcher 3.15 standalone for editing, RDKit-JS for depiction, 3Dmol.js for conformers; `validate_and_canonicalize()` is the single entry gate.)*
- 🟡 Library/grid with property columns; SMILES/CSV/SDF I/O; molecule diff. *(`POST /libraries/{id}/import` and `GET /libraries/{id}/export` cover SMILES/CSV/SDF, firewalled and InChIKey-deduped, and `POST /molecules/diff` ✅. 🟡 The grid is a card layout that promotes `mw`/`logp`/`tpsa`/`qed` plus up to three imported CSV columns; the `libraries.columns_config` column that would back a user-chosen column set is read by no code yet.)*
- 🟡 Chemistry core: physchem descriptors, druglikeness, alerts; analog/R-group enumeration; filtering/ranking; **one ADMET predictor**; **basic Vina docking** + pose view. *(Descriptors, druglikeness, alerts, R-group enumeration and MPO-based filtering/ranking ✅, and the docking pose view ✅. 🟡 The ADMET and docking predictors themselves are **adapter-gated**: `GLOWSKY_ADMET_BACKEND` and `GLOWSKY_DOCKING_BACKEND` both default to `none`, so `predict_admet` and `dock` are registered and advertised to the LLM but raise `BackendNotConfigured` → HTTP 501 until an operator wires `rdkit` / `vina`.)*
- 🟡 Agent: Composer chat (stream + tool-call viz), `@`-context, the chained design workflow, Cmd+K inline, accept/reject diffs. *(Milestone streaming over `/agent/chat/stream`, `@`-context, the chained workflow and Cmd+K ✅ — token-level streaming ⏳. ⏳ Tool-call trace visualisation in Composer: the Design screen renders an execution trace, but the Composer collects the same trace events without displaying them. 🟡 Review: candidates land as cards and enter a library only through an explicit "Save to library"; a property-delta diff card and an explicit reject action ⏳.)*
- ✅ Output: Jupyter notebook export + Markdown report.
- 🟡 Async workers + WS progress; the MVP security non-negotiables. *(Celery workers, `POST /jobs` / `POST /jobs/batch` and the `/jobs/{id}/stream` WebSocket ✅. ⏳ Of the non-negotiables in `08`: keys are Fernet, not KMS-managed; `GET /tools` and `POST /molecules/diff` are still unauthenticated (`07` §10).)*
- ✅ **Client shape (pivot):** the shipped UI is a **Tauri 2 + React 18 + Vite desktop app** (`apps/desktop/`, productName `Glowsky`, identifier `com.glowsky.desktop`), not the Next.js web app originally recommended in `10-tech-stack.md`. `10` now records that recommendation as **superseded**: it is the web/marketing surface that is deferred, not the desktop shell.

**Milestones**
- M1: Workspace + molecule editing/visualization + library (no agent yet).
- M2: Agent chat + tool calls + analog generation + filtering (the loop without docking).
- M3: Docking + ADMET + notebook/report export → **feature-complete MVP**.
- M4: Closed beta hardening, telemetry, bug-bash, perf (sub-second UI, fast render, streaming).

**Definition of done:** design partners run the Maya journey unaided and produce a reproducible notebook. Activation metric instrumented.

---

## 🟡 Phase 2 — Advanced Chemistry + Teams *(~12–16 weeks)*
*Not worked through in order: MPO scoring, template retrosynthesis, bioisosteres and the model-routing UI landed early; RAG, team collaboration, cost/usage visibility and launch are untouched.*

**Objective:** deepen science so David adopts fully and teams collaborate; broaden provider support; public launch.

**Build (per `08` V1 list):**
- Generative: ✅ **bioisosteres and scaffold hopping already shipped** (`services/chemistry/bioisosteres.py` — 6 functional-group bioisostere reaction SMARTS + an aza-walk ring hop, exposed as the `bioisosteric_replacement` tool and run by the design loop alongside R-group enumeration). ⏳ Still open: de novo profile-targeting and an ML generative model — today's generation is entirely deterministic RDKit reaction SMARTS (10 in `generative.py`; 6 + the one ring hop in `bioisosteres.py`), and the backend declares no ML dependency at all (`rdkit>=2024.3` is the only chemistry dep; the sole ML in the repo is the containerized ADMET-AI *predictor* example, not a generator).
- 🟡 Fuller ADMET suite + applicability domain. *(With `GLOWSKY_ADMET_BACKEND=rdkit` the in-process `rdkit-qspr` adapter answers seven endpoints — solubility, logd, herg, cyp3a4, metabolic_stability, ppb, bbb — each carrying `method`, `confidence` and an `applicability_domain` flag; but the backend defaults to `none`, and only Delaney ESOL solubility is a published regression — the other six are logistic/rule heuristics, not trained models. MPO scoring ✅ **already shipped ahead of plan** — `services/chemistry/medchem.py` computes piecewise-linear (Derringer / Pfizer-CNS-MPO style) desirability as a weighted arithmetic mean against one named profile (`oral`, `lead` or `fragment`) and reports the limiting property. Exposed as the `mpo_score` tool, ranks candidates in the design loop, is a selectable Δ property for MMP/SAR, is served by `POST /molecules/assess`, and renders as desirability bars in the desktop Molecule Inspector. Pareto views remain open.)*
- ✅ **Already shipped (ahead of plan):** template retrosynthesis + synthesizability scoring — `services/chemistry/retrosynthesis.py` (7 named one-step retro SMARTS disconnections: amide coupling, esterification, sulfonamide formation, urea formation, Suzuki coupling, reductive amination, Williamson ether) and `services/chemistry/synthesizability.py` (Ertl & Schuffenhauer SA score, `synthesizable` at SA ≤ 6.0), registered as the `sa_score`, `retrosynthesize` and `synthesizability` tools, covered by 11 tests in `tests/test_retrosynthesis.py`, and surfaced by a dedicated Retrosynthesis screen in the desktop app. ⏳ Still open for Phase 2: the AiZynth-class part — multi-step route search, an SC score, and a real building-block catalog. Today "purchasable" is a two-number heuristic (heavy atoms ≤ 12 **and** SA ≤ 3.5), so `route_found` does not imply a supplier exists.
- Literature RAG with citations (PubMed/PMC + user docs).
- Batch docking + interaction analysis.
- Hypothesis/experiment tracking + decision log.
- 🟡 Collaboration: sharing, roles, comments, activity feed. *(Roles ✅ — owner/admin/editor/viewer carried on `memberships` from the carbon-auth token and enforced by `require_write`. ⏳ Still open: sharing beyond the org boundary, comments and an activity feed.)*
- ✅ **Model-routing UI shipped early** — `GET/PUT/DELETE /settings/routes` back per-org `model_route_overrides` rows for the three task classes, and the Settings screen's "Model routing" section edits provider/model per task class with an override/default badge and a Revert button. ✅ **Groq** is already one of the four connectable providers (`anthropic`, `openai`, `groq`, `local`). ⏳ Still open: **cost/usage visibility** — LiteLLM token usage is read into `CompletionResponse.usage` but is never persisted, displayed, or budgeted (`models_used` records only route strings), and the gateway has no spend budget or rate limit — plus the remaining providers (xAI/Together/Mistral/Bedrock/Azure/Vertex).
- 🟡 Workflow templates; richer PDF reporting; substructure/similarity search at scale. *(`substructure_search`, `tanimoto_similarity` and `bulk_similarity` ship as tools ✅, but they loop in-process over the molecules handed to them — there is no index. ⏳ Workflow templates and PDF reporting; today's report formats are the notebook and Markdown exports.)*

**Milestones**
- M5: Advanced generative + multi-step retrosynthesis route search + RAG.
- M6: Collaboration + teams + cost/usage UI.
- M7: **Public launch** (Pro + Team tiers), pricing, billing, marketing site.

**Definition of done:** David journey works end-to-end with team sharing; paid conversion live; RAG citations trustworthy.

---

## ⏳ Phase 3 — Polish, Extensibility & Enterprise *(~12–20 weeks, ongoing)*
*Only two pieces exist today — the opt-in container-tool runtime and MMP/SAR mining; everything else here is unstarted.*

**Objective:** build the moat (extensibility) and unlock enterprise revenue.

**Build (per `08` Future list):**
- **Extensibility SDK:** 🟡 partly shipped — the tool contract (`ToolSpec`) and the **sandboxed container-tool runtime** already exist: `services/tools/manifest.py` parses a `glowsky-tool.yaml` manifest into a first-class `ToolSpec`, and `services/tools/runtimes/container.py` runs the image one-shot under `docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges --network none` (plus pids/memory/cpu caps, non-root, timeout) over a JSON stdin/stdout ABI, with the same cache/firewall/provenance as built-ins; 5 example tools live in `examples/tools/`. `13` §6 marks container tools ✅ **Phase 0**. It is **opt-in and trusted-single-tenant/local only** — `GLOWSKY_ENABLE_CONTAINER_TOOLS` + `GLOWSKY_TOOLS_DIR` — and OFF in `docker-compose.prod.yml`, because the runtime shells out to a root-equivalent `/var/run/docker.sock`. ⏳ Still open: a multi-tenant-safe tool runner; SDK ergonomics (decorator + Pydantic I/O models, generated schemas, image build/pin); remote-HTTP tools (`Runtime.REMOTE_HTTP` is declared with no implementation); custom agents/skills and custom models; per-org tool governance/approval + namespacing; the stable **public** tool-registry contract; and (later) a plugin marketplace.
- **Public API + Python SDK**, webhooks, embedded notebook compute.
- **Desktop distribution:** bundle the FastAPI backend as a Tauri sidecar — today `pnpm desktop:build` (from `apps/desktop/`, or `make desktop-build`) produces installers for an app that still requires a separately-run backend on `localhost:8000`, so `tauri.conf.json` declares no `externalBin`; add installer signing/notarization and auto-update (no updater or signing config today); set a Content-Security-Policy (`tauri.conf.json` currently sets `"csp": null`); and move credentials to OS-keychain storage — the access and refresh tokens live in plain `localStorage` with no keyring/stronghold plugin.
- **Enterprise:** SSO/SAML/SCIM, admin console, audit export, CMK/BYOK, **self-hosted Helm chart + air-gapped mode**, **SOC 2 Type II**.
- Advanced SBDD (pharmacophore, ensemble/ML docking, FEP hooks), patent/IP-aware search (non-legal framing).
- Real-time collaboration; active-learning design loops. *(✅ MMP-based **SAR mining shipped ahead of plan** — `services/chemistry/mmp.py` (`matched_pairs`, `sar_transforms`) behind the `matched_pairs` and `sar_transforms` tools, with a dedicated Matched Pairs & SAR screen in the desktop app.)*
- ELN/LIMS integrations.

**Milestones**
- M8: Tool SDK ergonomics + multi-tenant-safe runner + governance + public API (Dr. Chen registers a custom tool **without hand-writing a manifest and a Dockerfile, on a host that isn't trusted single-tenant**).
- M9: Enterprise pack (SSO, self-host, CMK) + SOC 2 readiness.
- M10: Advanced SBDD + IP search + ecosystem integrations.

**Definition of done:** a pharma champion self-hosts in VPC, registers internal tools, rolls out to a team; SOC 2 achieved.

---

## Sequencing principles
1. **De-risk early:** the BYO-LLM gateway and chemistry-as-tools are the two hardest unknowns — proven in Phase 0, not Phase 2.
2. **One persona deep before broad:** nail Maya's loop in MVP; expand to David/teams in Phase 2; champion/enterprise in Phase 3.
3. **Heavy-worker architecture validated in MVP** via basic docking, so scaling it later is incremental, not architectural.
4. **Extensibility last, deliberately:** stabilize the internal tool registry through real use before exposing it publicly.
5. **Security baseline from Phase 0;** enterprise-grade controls layer on in Phase 3 without rework.

## Cross-phase tracks (continuous)
- Reliability/observability, cost controls, design-partner feedback loop, chemistry-correctness validation (advisor-reviewed), docs.
