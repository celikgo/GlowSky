# Glowsky — Feature Set & Prioritization

Prioritized into **MVP**, **V1 (nice-to-have)**, and **Future/Advanced**. Guiding rule: MVP must deliver the **agentic design loop** end-to-end for **one persona deeply (Maya)** while being usable by David — narrow but complete, not broad and shallow.

The MVP litmus test: *Can a user, with their own LLM key, take a molecule from a natural-language prompt to a validated, visualized, property-annotated, docked, exportable result — without writing code?* If yes, MVP is real.

---

## 🟢 MVP — Must-have (Phase 1)
**Goal: the core loop works, with BYO-LLM, for small-molecule design.**

### Foundation
- Auth (email + Google/GitHub/ORCID OAuth), single-tenant-style org model, projects.
- **BYO-LLM:** connect ≥3 providers (Anthropic, OpenAI, one OpenAI-compatible/local), secure key storage, basic per-task model routing.
- Core data model + versioning + provenance plumbing.

### Molecule experience
- Import/paste SMILES; **RDKit canonicalization & validation**; 2D rendering.
- Basic 2D editor (sketch/edit) — or a solid embedded editor (Ketcher/JSME).
- 3D conformer view (single molecule).
- Library/grid view with property columns; import/export SMILES/CSV/SDF.
- Molecule diff (2 molecules + property deltas).

### Chemistry core
- Physicochemical descriptors (RDKit): MW, logP, TPSA, HBD/HBA, rotatable bonds, QED, Lipinski/Veber, PAINS/alerts.
- **Generative:** analog / R-group enumeration around a scaffold with constraints (RDKit-based + LLM-proposed, all validated/filtered).
- Property-based filtering & ranking.
- **One ADMET predictor integration** (open model) for a handful of key endpoints (e.g., solubility, hERG, logD) with confidence display.
- **Docking (basic):** wrap AutoDock Vina/smina; load PDB, define pocket from ligand, dock a small set, view poses + scores.

### Agent
- **Composer chat** with streaming + tool-call visualization.
- **`@`-context** attachment (molecules/projects).
- **Agentic workflow** that chains generate → validate → filter → predict → (dock) → rank → explain, with a visible plan.
- **Cmd/Ctrl+K inline** action on a molecule (≥ "make analogs," "modify property").
- Accept/reject proposals (diff cards).

### Output
- **Jupyter notebook export** of a run (reproducible RDKit code).
- Basic Markdown report export.

### Platform/security (non-negotiable subset from §10 of security doc)
- Encrypted KMS key storage, tenant isolation, TLS+at-rest, server-side authz, sandboxed workers, audit logging.

### Async infra
- Task queue + worker pool for generation/docking/prediction; WS streaming of progress.

---

## 🟡 V1 — Nice-to-have (Phase 2)
**Goal: deepen chemistry, broaden personas (David fully + teams), and harden.**

- **More generative modes:** scaffold hopping, bioisostere suggestions, de novo toward a profile; integrate an ML generative model (REINVENT-class).
- **Fuller ADMET suite** (CYPs, metabolic stability, permeability, mutagenicity) + applicability domain.
- **Retrosynthesis & synthesizability** (SA/SC score + AiZynth-class route suggestions).
- **Literature RAG with citations** (PubMed/PMC + user document upload).
- **Batch docking** across a library; pose interaction analysis in 3D.
- **Hypothesis & experiment tracking;** decision log.
- **Collaboration:** project sharing, roles, comments/annotations, activity feed.
- **Model routing UI** + cost/usage visibility; more providers (xAI, Groq, Together, Mistral, Bedrock/Azure/Vertex).
- **Workflow templates** (save/re-run/parameterize a successful run).
- **Better reporting** (PDF, figures, provenance tables).
- Substructure/similarity search across libraries (RDKit cartridge or service).
- Onboarding flow, sample projects, templates.

---

## 🔵 Future / Advanced (Phase 3+)
**Goal: extensibility, enterprise, scale, and moat.**

- **Extensibility SDK:** register custom tools, custom agents/skills, custom models; plugin marketplace.
- **Public API (REST/GraphQL) + Python SDK;** webhooks; embedded notebook compute.
- **Enterprise:** SSO/SAML/SCIM, admin console, audit export, CMK/BYOK, SOC 2, self-hosted Helm + air-gapped mode.
- **Patent/IP-aware search** (with explicit non-legal-advice framing); FTO support.
- **Advanced structure-based design:** pharmacophore modeling, MD-adjacent triage, free-energy-perturbation hooks, ensemble docking, gnina/ML scoring.
- **Real-time collaborative editing** (multiplayer workspace).
- **Multi-parameter optimization (MPO) scoring** & Pareto views; active-learning design loops.
- **Reaction/synthesis planning** integration with building-block catalogs (Enamine, etc.).
- **ELN/LIMS integrations** (Benchling, etc.).
- **Beyond small molecules:** basic peptide/PROTAC/covalent support.
- **Managed inference option** (for users without keys) + fine-tuned chemistry models.
- **Org knowledge graph / SAR mining** across projects.

---

## Prioritization rationale
- **BYO-LLM is MVP, not optional** — it's the economic + trust wedge (near-zero inference cost for us; IP control for users).
- **Docking in MVP (basic)** — it's a key "wow" for both personas and validates the heavy-worker architecture early. Kept minimal (one engine, small batches).
- **RAG/literature deferred to V1** — valuable but not core to the design-loop "aha," and ingestion/citation quality is a rabbit hole.
- **Extensibility deferred to Phase 3** — it's the champion/enterprise moat but needs a stable tool registry first; building it too early risks premature abstraction.
- **Collaboration in V1** — MVP can be single-user-deep; teams matter once the loop is proven.

See `09-roadmap.md` for sequencing and `10-tech-stack.md` for the implementing stack.
