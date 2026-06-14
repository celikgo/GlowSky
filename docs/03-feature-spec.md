# Glowsky — Detailed Feature Specification

This breaks down every major feature area. Prioritization (MVP / V1 / Future) is summarized in `08-feature-prioritization.md`; here we describe *what* each feature is and *how* it should behave.

---

## A. AI Agent & Chat (the spine)

### A1. Composer / Sidebar Chat
- Persistent, context-aware chat panel (Cursor "Composer" style) docked to the workspace.
- **Context attachment:** `@`-mention molecules, projects, files, assay results, literature docs to inject them as structured context. ("Optimize @lead-7 for solubility.")
- **Streaming responses** with tool-call visualization: the user sees the agent's plan, each tool invocation (RDKit, predictor, docking), inputs/outputs, and final synthesis.
- **Action proposals with diff/preview:** when the agent generates or edits molecules, results appear as reviewable diffs/cards the user can accept, reject, or refine — never silently mutating the workspace.
- Conversation history per project; threads; branchable conversations.

### A2. Agentic Workflows (the differentiator)
- The agent decomposes a natural-language goal into a **plan of tool calls**, executes them, and synthesizes results.
- Example: *"Generate 50 analogs of @scaffold-A with MW<450, predicted logP 1–3, no PAINS/hERG flags, synthesizable, and dock the top 10 against @target.pdb."* → generate → filter (RDKit/property/alerts) → predict → rank → dock → report.
- **Plan transparency:** show the DAG/steps; allow pause, edit, re-run of a step.
- **Tool registry:** the agent only acts through a curated, validated tool catalog (no free-form code execution by default; sandboxed code tool optional/opt-in).
- Re-runnable & parameterizable; save a successful run as a reusable **workflow template**.

### A3. Inline AI Commands (Cmd/Ctrl+K)
- Invoke AI directly on a selected molecule, R-group, or text without going to chat.
- On a molecule: "lower the logP," "add a fluorine to reduce metabolism here," "suggest bioisosteres for this amide," "make 10 analogs."
- On code/notebook cells: generate/edit cheminformatics code.
- Returns an inline preview + accept/reject.

### A4. Model Routing & BYO-LLM control
- Pick the model per task class (chat/reasoning, code-gen, embeddings, fast triage). See `Section H`.

---

## B. Molecule Editing & Visualization

### B1. 2D Structure Editor & Renderer
- High-quality 2D depiction (RDKit/CoordGen or Ketcher/JSME-class editor).
- Sketch a molecule, paste SMILES/InChI/MOL, or import from file.
- Edit atoms/bonds/stereochemistry directly; agent edits reflected here.
- Always **canonicalized & validated** on input (RDKit); invalid structures flagged, never silently accepted.

### B2. 3D Visualization
- 3D conformer generation (RDKit ETKDG) and rendering (Mol*, NGL, or 3Dmol.js).
- Protein–ligand complex viewing (load PDB, show pocket, docked poses).
- Measure distances, show interactions (H-bonds, π-stacking) for docked poses.

### B3. Multi-molecule / Multi-file Workspace
- Tabbed / panel workspace like an IDE: multiple molecules, libraries, notebooks, and protein structures open at once.
- Grid/table view of a library with inline 2D depictions + property columns (sortable, filterable).

### B4. Molecule Diff & Comparison
- Visual diff of two molecules (highlight changed substructure) and their property deltas.
- Side-by-side comparison cards; "what changed and what it cost/gained."

### B5. Versioning
- Every molecule and library is versioned; view history, revert, branch. Generations link to the prompt/agent run that produced them (provenance).

---

## C. Core Chemistry Capabilities

### C1. Cheminformatics core (RDKit)
- Canonicalization, standardization, salt stripping, tautomer handling.
- Descriptors & physchem properties (MW, logP/cLogP, TPSA, HBD/HBA, rotatable bonds, aromatic rings, Fsp3, QED).
- Substructure search, SMARTS matching, similarity (fingerprints: Morgan/ECFP, MACCS), clustering.
- Druglikeness rules (Lipinski, Veber, etc.), PAINS / structural-alert filtering.

### C2. Generative Molecule Design
- **De novo** generation toward a target profile.
- **Scaffold hopping** (preserve pharmacophore, change core).
- **R-group / analog enumeration** around a scaffold with constraints.
- **Bioisosteric replacement** suggestions.
- Approach: combine LLM-proposed ideas with cheminformatics enumeration + ML generative models (e.g., REINVENT-class / fragment-based) where available; **all outputs validated & filtered** through RDKit before display.

### C3. Property & ADMET Prediction
- Physicochemical (fast, RDKit-computed).
- ADMET (solubility, permeability/Caco-2, hERG, CYP inhibition, metabolic stability, mutagenicity, etc.) via open models (e.g., ADMET-AI/ADMETlab-class) or pluggable custom models.
- **Honest uncertainty:** show confidence/applicability domain; never present a prediction as ground truth.

### C4. Molecular Docking & Structure-Based Design
- Wrap an open docking engine (AutoDock Vina / smina / gnina) for pose generation + scoring.
- Pocket definition (from ligand, residues, or box), batch docking of a library, pose visualization.
- Pluggable for enterprise (internal/commercial docking engines via the tool SDK).

### C5. Retrosynthesis & Synthesizability
- Synthetic accessibility scoring (SAScore / SCScore).
- Retrosynthetic route suggestions via open models (e.g., AiZynthFinder-class) or external API.
- Building-block / reaction feasibility hints.

### C6. Literature & IP-aware RAG
- RAG over PubMed/PMC abstracts, optionally patents, and **user-uploaded documents** (PDFs, internal reports).
- Chemistry-aware retrieval (structure + text); answer with **citations**.
- "Has anyone made something like @molecule?" → similar known compounds + references. (Note: not a substitute for formal FTO/patent counsel — labeled as such.)

---

## D. Projects, Libraries & Knowledge Management

### D1. Projects
- Top-level container: target(s), goal/profile, members, molecules, libraries, notebooks, conversations, hypotheses, documents.
- Project-level settings: default models, tool config, data-residency.

### D2. Molecule Libraries
- Collections of molecules with tags, statuses (idea / synthesized / tested / rejected), and arbitrary property columns.
- Import/export: SMILES, SDF, CSV, MOL; bulk operations.

### D3. Hypothesis & Experiment Tracking
- First-class **hypothesis** objects: statement, supporting/refuting molecules & data, status, linked rationale.
- Experiment/design plans: what to make, why, expected outcome; link results back.
- Decision log ("why we killed this scaffold").

### D4. Reporting & Notebook Export
- Auto-generate a report (Markdown/PDF) of a design campaign: prompts, molecules, predictions, plots, decisions, citations.
- **Export to Jupyter notebook** that reproduces the analysis with real RDKit code (reproducibility for Maya/Chen).

---

## E. Collaboration & Team

### E1. Sharing & permissions — share projects/libraries; roles (owner/editor/viewer).
### E2. Comments & annotations — on molecules, hypotheses, agent runs.
### E3. Activity feed & audit — who did/changed what, which model/tool ran.
### E4. Real-time / async presence — see teammates; (real-time co-editing is Future).

---

## F. Extensibility (champion-driven)

### F1. Custom Tools — register a function/HTTP endpoint as an agent-callable tool (schema + auth). Dr. Chen's internal ADMET model becomes "predict_admet_internal."
### F2. Custom Agents / Skills — define specialized agents (e.g., "FTO checker," "synthesis planner") with their own prompts/toolsets.
### F3. Prompt & Workflow Templates — user/team-defined templates and saved workflows; shareable.
### F4. Plugin SDK & API — Python SDK + REST/GraphQL API for scripting and integration; webhooks.
### F5. Notebook integration — embedded notebook cells that can call workspace objects and tools.

---

## G. Account, Billing & Admin

### G1. Auth — email/OAuth (Google/GitHub/ORCID for academics), SSO/SAML (enterprise).
### G2. Subscription tiers & metering — Free/Academic, Pro, Team, Enterprise; usage analytics. (BYO-LLM means we meter *platform* usage, not necessarily tokens.)
### G3. Admin console — seats, roles, SSO, audit logs, data-governance settings, key management.
### G4. Onboarding — guided first project, sample data, templates.

---

## H. BYO-LLM & Model Management

### H1. Provider connections — Anthropic, OpenAI, xAI/Grok, Google, Groq, Together.ai, Mistral, local via Ollama/vLLM (OpenAI-compatible endpoints), AWS Bedrock / Azure / Vertex.
### H2. Secure key storage — user/org-scoped, encrypted; never logged; see `07-security-privacy.md`.
### H3. Model routing — assign models to task classes (deep reasoning vs. fast triage vs. code vs. embeddings); per-project overrides; fallbacks.
### H4. Cost & usage visibility — token/cost estimates per run (where the provider exposes it); budgets/limits.
### H5. Provider abstraction — a unified internal LLM interface (likely LiteLLM-class) so tools/agents are model-agnostic; capability flags (tool-use, vision, context length) gate features per model.
