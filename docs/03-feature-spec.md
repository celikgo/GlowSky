# Glowsky — Detailed Feature Specification

This breaks down every major feature area. Prioritization (MVP / V1 / Future) is summarized in `08-feature-prioritization.md`; here we describe *what* each feature is and *how* it should behave.

**Status legend.** ✅ shipped · 🟡 partial · ⏳ planned. The markers describe the code as it stands today; the prose stays the spec. A ⏳ item is still a commitment — it just isn't built yet.

---

## A. AI Agent & Chat (the spine)

### A1. Composer / Sidebar Chat 🟡
- Persistent, context-aware chat panel (Cursor "Composer" style) docked to the workspace. 🟡 — Composer is the desktop app's default screen and the seed/context/prompt dock rides at the bottom of it, but it *is* the screen rather than a panel docked beside one; a split view alongside a library or a structure ⏳ (B3).
- **Context attachment:** `@`-mention molecules, projects, files, assay results, literature docs to inject them as structured context. ("Optimize @lead-7 for solubility.") 🟡 — the `@ Context` picker attaches **molecules** (from a project's libraries, or a pasted SMILES) and the first attachment also seeds the design; files, assay results and literature docs ⏳.
- **Streaming responses** with tool-call visualization: the user sees the agent's plan, each tool invocation (RDKit, predictor, docking), inputs/outputs, and final synthesis. 🟡 — milestones stream over the `/agent/chat/stream` and `/agent/design/stream` WebSockets (`started / plan / trace / candidate / ranked / explanation`, then a terminal `complete`); token-level streaming of the model's prose ⏳.
- **Action proposals with diff/preview:** when the agent generates or edits molecules, results appear as reviewable diffs/cards the user can accept, reject, or refine — never silently mutating the workspace. ✅ — candidates land as cards and enter a library only through an explicit *Save to library*; the run and its molecules are recorded for provenance.
- Conversation history per project; threads; branchable conversations. ⏳ — each turn carries its own `messages` array; nothing chat-side is persisted.

### A2. Agentic Workflows (the differentiator) 🟡
- The agent decomposes a natural-language goal into a **plan of tool calls**, executes them, and synthesizes results. ✅ — through a **hand-written orchestrator** (no LangGraph, no agent framework): a fixed 6-stage loop — validate seed → LLM plan → generate analogs → profile → filter/rank by MPO desirability → LLM synthesis — making exactly two LLM calls, plus a bounded tool-calling loop (`max_steps=6`) for conversational turns.
- Example: *"Generate 50 analogs of @scaffold-A with MW<450, predicted logP 1–3, no PAINS/hERG flags, synthesizable, and dock the top 10 against @target.pdb."* → generate → filter (RDKit/property/alerts) → predict → rank → dock → report. 🟡 — the shipped design loop covers generate → profile → filter → rank, touching four tools and ranking by MPO desirability; it has no predict or dock stage at all. `predict_admet` and `dock` are registry tools the conversational loop can select instead, and both refuse until their adapters are configured (C3/C4).
- **Plan transparency:** show the DAG/steps; allow pause, edit, re-run of a step. 🟡 — the plan and the tool trace stream live and are persisted on the run; a DAG view with pause / edit / re-run of a single step ⏳.
- **Tool registry:** the agent only acts through a curated, validated tool catalog (no free-form code execution by default; sandboxed code tool optional/opt-in). 🟡 — the catalog is real and closed (**22 built-in tools**, all at version `0.1.0`, nothing else unless container tools are switched on — see F1), but arguments are **not** schema-validated: `input_schema` is advertised to the model and the Tools screen, and a malformed call surfaces as a 422 rather than being rejected up front.
- Re-runnable & parameterizable; save a successful run as a reusable **workflow template**. ⏳ — the re-run path today is the notebook export (D4).

### A3. Inline AI Commands (Cmd/Ctrl+K) 🟡
- Invoke AI directly on a selected molecule, R-group, or text without going to chat. 🟡 — the Cmd/Ctrl+K palette ships (navigation + molecule actions, openable globally or scoped to a molecule from a card's ⌘K button); R-group and free-text selection ⏳.
- On a molecule: "lower the logP," "add a fluorine to reduce metabolism here," "suggest bioisosteres for this amide," "make 10 analogs." 🟡 — shipped as a fixed action list (make analogs, lower logP, MW<300, drug-like); arbitrary natural-language edits go through the Composer.
- On code/notebook cells: generate/edit cheminformatics code. ⏳ — there are no notebook cells in the app; notebooks are an export format (D4).
- Returns an inline preview + accept/reject. 🟡 — a palette action composes a Composer turn (sets the seed, prefills the prompt) and hands off to the chat, so there is one design path rather than two; review happens on the Composer's cards.

### A4. Model Routing & BYO-LLM control 🟡
- Pick the model per task class (chat/reasoning, code-gen, embeddings, fast triage). See `Section H`. 🟡 — three classes ship (`reasoning`, `fast_triage`, `codegen`), resolvable per org and surfaced in `/health` and `/settings/routes`; an embeddings class ⏳, and no code path issues a `codegen` completion yet.

---

## B. Molecule Editing & Visualization

### B1. 2D Structure Editor & Renderer 🟡
- High-quality 2D depiction (RDKit/CoordGen or Ketcher/JSME-class editor). ✅ — depiction is **RDKit-JS** (RDKit 2025.3.4 compiled to WASM; `RDKit_minimal.js/.wasm` staged into the desktop app's `public/`), and the embedded sketcher is **Ketcher 3.15** in standalone mode — Indigo runs in a Web Worker, so drawing, cleanup and SMILES export need no backend and no network.
- Sketch a molecule, paste SMILES/InChI/MOL, or import from file. 🟡 — SMILES everywhere, MOL blocks through Ketcher, and SMILES/CSV/SDF through the library importer; direct InChI input ⏳ (the firewall parses SMILES).
- Edit atoms/bonds/stereochemistry directly; agent edits reflected here. ✅ — the Ketcher modal is lazy-loaded (opening it is the only thing that pulls the WASM editor into the page) and hands its SMILES back to the caller, which the backend canonicalizes on use.
- Always **canonicalized & validated** on input (RDKit); invalid structures flagged, never silently accepted. ✅ — `validate_and_canonicalize()` (salt strip → largest fragment → neutralize → canonical SMILES + InChIKey) is the single entry gate for typed, imported and model-emitted structures alike.

### B2. 3D Visualization 🟡
- 3D conformer generation (RDKit ETKDG) and rendering (Mol*, NGL, or 3Dmol.js). ✅ — **ETKDGv3**, MMFF-minimized, served by `POST /molecules/conformer` and drawn with **3Dmol.js**, lazily imported on first 3D view.
- Protein–ligand complex viewing (load PDB, show pocket, docked poses). 🟡 — `DockingPose3D` draws the receptor as a spectrum cartoon under a translucent VDW surface with the docked pose as ball-and-stick (PDB or Vina `.pdbqt`), demoed on the RCSB 1HSG sample; pocket-specific display beyond the whole-receptor surface ⏳.
- Measure distances, show interactions (H-bonds, π-stacking) for docked poses. ⏳

### B3. Multi-molecule / Multi-file Workspace 🟡
- Tabbed / panel workspace like an IDE: multiple molecules, libraries, notebooks, and protein structures open at once. ⏳ — the desktop client is 8 screens behind a single `useState<NavKey>`: one screen at a time, no tabs, no router.
- Grid/table view of a library with inline 2D depictions + property columns (sortable, filterable). 🟡 — the Library screen renders a card grid with inline depictions and each molecule's stored properties; sortable/filterable table columns ⏳.

### B4. Molecule Diff & Comparison 🟡
- Visual diff of two molecules (highlight changed substructure) and their property deltas. 🟡 — `POST /molecules/diff` returns identity plus per-descriptor deltas (MW, logP, TPSA, HBD, HBA, rotatable bonds, QED); substructure highlighting ⏳.
- Side-by-side comparison cards; "what changed and what it cost/gained." ⏳ — no desktop screen consumes the diff endpoint yet.

### B5. Versioning 🟡
- Every molecule and library is versioned; view history, revert, branch. ⏳ — there are no version tables and no `updated_at` column on any table.
- Generations link to the prompt/agent run that produced them (provenance). ✅ — a generated molecule carries `origin_run_id` back to the `agent_runs` row holding the goal, plan, trace and models used.

---

## C. Core Chemistry Capabilities

### C1. Cheminformatics core (RDKit) 🟡
- Canonicalization, standardization, salt stripping, tautomer handling. 🟡 — salt strip → largest fragment → neutralize → canonical SMILES ships; tautomer handling ⏳.
- Descriptors & physchem properties (MW, logP/cLogP, TPSA, HBD/HBA, rotatable bonds, aromatic rings, Fsp3, QED). ✅ — exactly this set, plus heavy-atom count.
- Substructure search, SMARTS matching, similarity (fingerprints: Morgan/ECFP, MACCS), clustering. 🟡 — SMARTS substructure search, Morgan and MACCS fingerprints, and pairwise/bulk Tanimoto ship; clustering ⏳.
- Druglikeness rules (Lipinski, Veber, etc.), PAINS / structural-alert filtering. ✅ — Lipinski Ro5 + Veber, and the RDKit PAINS **and** BRENK catalogs.

### C2. Generative Molecule Design 🟡
- **De novo** generation toward a target profile. ⏳ — every generative path starts from a seed structure; there is no de novo sampler.
- **Scaffold hopping** (preserve pharmacophore, change core). 🟡 — a single aza-walk hop in `bioisosteres.py`, not a general core-replacement search.
- **R-group / analog enumeration** around a scaffold with constraints. ✅ — 10 hard-coded reaction SMARTS in `generative.py`, filtered against the requested profile.
- **Bioisosteric replacement** suggestions. ✅ — 6 bioisostere SMARTS.
- Approach: combine LLM-proposed ideas with cheminformatics enumeration + ML generative models (e.g., REINVENT-class / fragment-based) where available; **all outputs validated & filtered** through RDKit before display. 🟡 — the LLM contributes *intent* only and the enumeration is **deterministic**: every candidate is built by an RDKit reaction SMARTS, never emitted by the model, and the structure firewall re-validates the output of the two tools that declare `emits_structures`, inspecting dict keys named `smiles`. The ML half ⏳ — the repo carries **zero ML dependencies**; `rdkit` is the only chemistry dependency.

### C3. Property & ADMET Prediction 🟡
- Physicochemical (fast, RDKit-computed). ✅
- ADMET (solubility, permeability/Caco-2, hERG, CYP inhibition, metabolic stability, mutagenicity, etc.) via open models (e.g., ADMET-AI/ADMETlab-class) or pluggable custom models. 🟡 — `predict_admet` is **adapter-gated**: `GLOWSKY_ADMET_BACKEND` defaults to `none` and the default backend raises `BackendNotConfigured` → HTTP 501, so the tool is advertised to the model but refuses out of the box. Setting it to `rdkit` enables the in-repo `rdkit-qspr` backend — 7 endpoints (solubility, logD, hERG, CYP3A4, metabolic stability, plasma-protein binding, BBB), of which only Delaney ESOL solubility is a published regression and the other 6 are logistic/rule heuristics. ADMET-AI ships as an *example container tool*, not as a built-in.
- **Honest uncertainty:** show confidence/applicability domain; never present a prediction as ground truth. ✅ — every `rdkit-qspr` endpoint returns `method`, `confidence` and `applicability_domain` alongside the value, and an unconfigured backend 501s rather than inventing one.

### C4. Molecular Docking & Structure-Based Design 🟡
- Wrap an open docking engine (AutoDock Vina / smina / gnina) for pose generation + scoring. 🟡 — the `dock` tool and a Vina adapter ship, but `GLOWSKY_DOCKING_BACKEND` defaults to `none` → `BackendNotConfigured` (HTTP 501). Glowsky never fabricates a score; `docker-compose.docking.yml` is the overlay that wires a real engine in.
- Pocket definition (from ligand, residues, or box), batch docking of a library, pose visualization. 🟡 — the pocket is an explicit box (`center` + `size`); deriving it from a bound ligand or a residue list ⏳. Batch fan-out rides `POST /jobs/batch`, and pose visualization ships (B2).
- Pluggable for enterprise (internal/commercial docking engines via the tool SDK). 🟡 — the seam is the `DockingBackend` protocol plus the opt-in container-tool runtime (F1); there is no Tool SDK yet.

### C5. Retrosynthesis & Synthesizability 🟡
- Synthetic accessibility scoring (SAScore / SCScore). 🟡 — SAScore ships as `sa_score` / `synthesizability`; SCScore ⏳.
- Retrosynthetic route suggestions via open models (e.g., AiZynthFinder-class) or external API. 🟡 — `retrosynthesize` proposes **one-step** disconnections from 7 named reaction templates; multi-step tree search (AiZynthFinder-class) or an external route API ⏳.
- Building-block / reaction feasibility hints. 🟡 — "purchasable building block" is a heuristic stand-in (`heavy_atoms <= 12 and sa_score <= 3.5`), not a supplier-catalog lookup.

### C6. Literature & IP-aware RAG ⏳
- RAG over PubMed/PMC abstracts, optionally patents, and **user-uploaded documents** (PDFs, internal reports). ⏳ — there is no retrieval layer, no vector store and no document ingestion in the repo.
- Chemistry-aware retrieval (structure + text); answer with **citations**. ⏳
- "Has anyone made something like @molecule?" → similar known compounds + references. (Note: not a substitute for formal FTO/patent counsel — labeled as such.) 🟡 — the structure half of that question is already answerable offline via `tanimoto_similarity` / `bulk_similarity` over a user's own libraries; the literature half is the ⏳ part.

---

## D. Projects, Libraries & Knowledge Management

### D1. Projects 🟡
- Top-level container: target(s), goal/profile, members, molecules, libraries, notebooks, conversations, hypotheses, documents. 🟡 — a project holds a `target_profile` JSON, its molecules, its libraries and its agent runs; notebooks, conversations, hypotheses and documents ⏳.
- Project-level settings: default models, tool config, data-residency. ⏳ — model routes and provider credentials are **org**-scoped (`/settings/routes`, `/settings/credentials`).

### D2. Molecule Libraries 🟡
- Collections of molecules with tags, statuses (idea / synthesized / tested / rejected), and arbitrary property columns. 🟡 — a library carries a `kind` and a `columns_config`, and each molecule an open `properties` JSON; first-class tags and the idea/synthesized/tested/rejected lifecycle ⏳.
- Import/export: SMILES, SDF, CSV, MOL; bulk operations. 🟡 — SMILES, CSV and SDF both ways, every row through the firewall, deduped by InChIKey within the project, bad rows reported rather than fatal; a standalone MOL format ⏳.

### D3. Hypothesis & Experiment Tracking ⏳
- First-class **hypothesis** objects: statement, supporting/refuting molecules & data, status, linked rationale. ⏳ — there is no hypothesis table; the closest shipped artifact is the agent run's stored goal, plan, trace and explanation.
- Experiment/design plans: what to make, why, expected outcome; link results back. ⏳
- Decision log ("why we killed this scaffold"). ⏳

### D4. Reporting & Notebook Export 🟡
- Auto-generate a report (Markdown/PDF) of a design campaign: prompts, molecules, predictions, plots, decisions, citations. 🟡 — `GET /runs/{run_id}/export?format=md` builds the Markdown report from the run; PDF, plots and citations ⏳.
- **Export to Jupyter notebook** that reproduces the analysis with real RDKit code (reproducibility for Maya/Chen). ✅ — `?format=ipynb` emits the notebook.

---

## E. Collaboration & Team

### E1. Sharing & permissions 🟡 — roles (owner/editor/viewer) are enforced end to end: they arrive on the platform JWT, are mirrored into `memberships`, and gate every mutating route through `require_write` (12 HTTP routes plus 2 of the 3 WebSockets). Membership is **org**-wide today; sharing an individual project or library with a subset of the org ⏳.
### E2. Comments & annotations ⏳ — on molecules, hypotheses, agent runs.
### E3. Activity feed & audit 🟡 — the mutating paths write `audit_events` (actor, action, entity type/id, metadata) inside the same transaction; there is no read endpoint and no feed UI yet.
### E4. Real-time / async presence ⏳ — see teammates; (real-time co-editing is Future).

---

## F. Extensibility (champion-driven)

### F1. Custom Tools 🟡 — the shipped seam is a **container tool**: a `glowsky-tool.yaml` manifest discovered from `GLOWSKY_TOOLS_DIR` and executed as a one-shot `docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --network none` sandbox. It is opt-in behind **both** `GLOWSKY_ENABLE_CONTAINER_TOOLS=true` **and** `GLOWSKY_TOOLS_DIR` (with only the directory set, the registry stays at the 22 built-ins), and 5 examples ship — `admet_ai`, `molecular_formula`, `cargo_dimensioning`, `apron_energy`, `damage_detect`. Dr. Chen's internal ADMET model becomes "predict_admet_internal" this way. Registering a plain Python function or an HTTP endpoint ⏳ — `Runtime.REMOTE_HTTP` is declared in the contract but unimplemented, and a manifest's declared schemas are not enforced on the arguments.
### F2. Custom Agents / Skills ⏳ — define specialized agents (e.g., "FTO checker," "synthesis planner") with their own prompts/toolsets.
### F3. Prompt & Workflow Templates ⏳ — user/team-defined templates and saved workflows; shareable.
### F4. Plugin SDK & API 🟡 — the integration surface today is the HTTP/WebSocket API itself (41 routes: 38 HTTP + 3 WebSocket, all decorators on one FastAPI app); a Python SDK, a GraphQL layer and webhooks ⏳.
### F5. Notebook integration ⏳ — embedded notebook cells that can call workspace objects and tools; today a run *exports* to a notebook (D4) rather than hosting one.

---

## G. Account, Billing & Admin

### G1. Auth ✅ — identity is **delegated to the nakitte-carbon-auth platform**; Glowsky runs no identity store and mints no credentials of its own. Every request in every environment must carry `Authorization: Bearer <platform JWT>`; the token is verified statelessly as **RS256** against carbon-auth's cached JWKS (`GLOWSKY_NAKITTE_JWKS_URL`), with audience `GLOWSKY_NAKITTE_JWT_AUDIENCE` (default `carbon-platform`) and, when set, issuer `GLOWSKY_NAKITTE_JWT_ISSUER` — there is no auth bypass. `/auth/login` (email + password), `/auth/refresh`, `/auth/tenants` and `/auth/select-tenant` are thin proxies to carbon-auth: Glowsky forwards credentials and relays the token, never storing them. The org, user and membership are **JIT-provisioned** from the token's `sub`, `tenant_id` and `roles` claims, with platform roles collapsed to Glowsky's **owner / editor / viewer** (`owner` → owner; only read-only roles → viewer; any other role → editor; none → viewer). Federated sign-in (Google/GitHub/ORCID OAuth), SSO/SAML and MFA are the identity platform's responsibility — this repo contains no such code.
### G2. Subscription tiers & metering ⏳ — Free/Academic, Pro, Team, Enterprise; usage analytics. (BYO-LLM means we meter *platform* usage, not necessarily tokens.) `organizations.plan` exists as a column; no code reads it, and nothing is metered.
### G3. Admin console 🟡 — the desktop **Settings** screen is the shipped slice of it: connect/remove BYO-LLM provider credentials and set per-org model routes — the key-management line of that list. Seats, role administration, SSO configuration, audit-log views and data-governance settings ⏳.
### G4. Onboarding 🟡 — sample data ships (`GET /examples/docking/sample` serves the RCSB 1HSG complex, and `make demo` runs a sample design loop end to end — on the offline mock when no provider key is configured); a guided first project and starter templates ⏳.

---

## H. BYO-LLM & Model Management

### H1. Provider connections 🟡 — four ship: **Anthropic, OpenAI, Groq, and `local`** (any OpenAI-compatible base URL — Ollama/vLLM), plus a deterministic offline **mock** so the whole agent loop runs with zero keys. Everything else on the wishlist — xAI/Grok, Google, Together.ai, Mistral, AWS Bedrock / Azure / Vertex — is ⏳, and a route naming an unsupported provider quietly degrades to the mock rather than erroring.
### H2. Secure key storage 🟡 — org-scoped **Fernet** ciphertext in `llm_provider_credentials.encrypted_secret` under `GLOWSKY_SECRET_KEY`, with a fail-fast boot guard outside dev and only a masked hint ever returned; never logged; see `07-security-privacy.md`. Per-user scoping, a rotation path (there is no `MultiFernet`) and KMS/secrets-manager custody ⏳.
### H3. Model routing 🟡 — three task classes (`reasoning`, `fast_triage`, `codegen`) with per-**org** overrides via `PUT /settings/routes` falling back to the env-configured default; beyond that the only fallback is graceful degradation to the offline mock when the routed provider has no credential. Per-project overrides and an embeddings class ⏳.
### H4. Cost & usage visibility ⏳ — token/cost estimates per run (where the provider exposes it); budgets/limits. Usage comes back on each completion but is neither stored nor aggregated, and there is no budget enforcement.
### H5. Provider abstraction 🟡 — shipped as `services/llm_gateway/`: a `Provider` protocol with `LiteLLMProvider` (Anthropic/OpenAI/Groq/local, tool schemas normalized across them) and `MockProvider` behind it, so the orchestrator and tool loop are model-agnostic. Capability flags (tool-use, vision, context length) gating features per model ⏳.
