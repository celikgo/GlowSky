# Glowsky — Feature Set & Prioritization

Prioritized into **MVP**, **V1 (nice-to-have)**, and **Future/Advanced**. Guiding rule: MVP must deliver the **agentic design loop** end-to-end for **one persona deeply (Maya)** while being usable by David — narrow but complete, not broad and shallow.

The MVP litmus test: *Can a user, with their own LLM key, take a molecule from a natural-language prompt to a validated, visualized, property-annotated, docked, exportable result — without writing code?* If yes, MVP is real.

**Priority key.** 🟢 MVP · 🟡 V1 · 🔵 future — these mark *priority tier*, not build status, so 🟡 here means "V1," never "partial" (the same split `13-chemistry-tools-architecture.md` §10 uses for its catalog). For what the repo actually contains today see `09-roadmap.md` and `03-feature-spec.md`, which use ✅ shipped · 🟡 partial · ⏳ planned. Items that landed ahead of this plan are annotated inline rather than silently re-listed as upcoming.

---

## 🟢 MVP — Must-have (Phase 1)
**Goal: the core loop works, with BYO-LLM, for small-molecule design.**

### Foundation
- **Auth: delegated to nakitte-carbon-auth** — Glowsky owns no identity. Every data-bearing endpoint requires `Authorization: Bearer <jwt>`: a carbon-auth **RS256** access token verified against the platform JWKS (`GLOWSKY_NAKITTE_JWKS_URL`), audience `carbon-platform` — 30 of the 38 HTTP routes are gated today (12 `require_write`, 18 `current_principal`), with `GET /tools` and `POST /molecules/diff` the two known gaps still to close (`07-security-privacy.md` §10). There is no auth bypass and no local *user*-credential store (the `ApiKey` model is on the books but dead code). Glowsky's only login surface is a thin proxy to carbon-auth — `POST /auth/login` (email+password), `/auth/refresh`, `/auth/tenants`, `/auth/select-tenant`. **Multi-tenant** org model: the token's `sub`/`tenant_id`/`roles` JIT-provision Organization/User/Membership on first sight, every tenant-owned row carries `org_id`, and cross-tenant reads return 404 (never 403). Platform roles collapse to owner/editor/viewer. Social/academic sign-in (Google/GitHub/ORCID), SSO/SAML and MFA are the identity platform's concern, not Glowsky's. Tenant-scoped projects.
- **BYO-LLM:** connect ≥3 providers (Anthropic, OpenAI, Groq, one OpenAI-compatible/local), secure key storage, and **per-task model routing with a Settings UI** — per-org provider/model overrides for the `reasoning` / `fast_triage` / `codegen` task classes, each shown as `override` or `default` and revertable to the server default.
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
- **MPO desirability scoring:** piecewise-linear plateau desirability per property, aggregated as a weighted arithmetic mean against a named profile (oral/lead/fragment), reporting the limiting property — drives candidate ranking in the agentic design loop.
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
- Encrypted key storage (**Fernet** ciphertext under an operator-supplied `GLOWSKY_SECRET_KEY`, with a fail-fast boot guard outside dev — a managed KMS / secrets manager layers on later), tenant isolation, TLS+at-rest, server-side authz, sandboxed workers, audit logging.

### Async infra
- Task queue + worker pool for generation/docking/prediction; WS streaming of progress.

---

## 🟡 V1 — Nice-to-have (Phase 2)
**Goal: deepen chemistry, broaden personas (David fully + teams), and harden.**

- **More generative modes:** de novo toward a profile; integrate an ML generative model (REINVENT-class). *(Scaffold hopping and bioisostere suggestions shipped ahead of plan — `services/chemistry/bioisosteres.py` is 6 functional-group bioisostere reaction SMARTS plus an aza-walk ring hop, exposed as the `bioisosteric_replacement` tool and run by the design loop alongside R-group enumeration. Everything generative today is deterministic RDKit SMARTS; the backend declares no ML dependency at all.)*
- **Fuller ADMET suite** (CYPs, metabolic stability, permeability, mutagenicity) + applicability domain.
- **Retrosynthesis & synthesizability:** AiZynth-class multi-step route search, an SC score, and a real building-block catalog. *(Template retrosynthesis shipped ahead of plan — `services/chemistry/retrosynthesis.py` (7 named one-step disconnections) and `services/chemistry/synthesizability.py` (Ertl & Schuffenhauer SA score), behind the `retrosynthesize`, `synthesizability` and `sa_score` tools and a dedicated Retrosynthesis screen. "Purchasable" is still a two-number heuristic, so `route_found` does not imply a supplier exists.)*
- **Literature RAG with citations** (PubMed/PMC + user document upload).
- **Batch docking** across a library; pose interaction analysis in 3D.
- **Hypothesis & experiment tracking;** decision log.
- **Collaboration:** project sharing, roles, comments/annotations, activity feed.
- **Cost/usage visibility** (token + spend accounting per org/run, budget caps) — the gateway already returns LiteLLM's `usage` on every completion, but nothing reads, aggregates or persists it today; and **more providers** (xAI, Together, Mistral, Bedrock/Azure/Vertex — Anthropic, OpenAI, Groq and local/OpenAI-compatible already ship).
- **Workflow templates** (save/re-run/parameterize a successful run).
- **Better reporting** (PDF, figures, provenance tables).
- Substructure/similarity search across libraries *at scale* (RDKit cartridge or service) — the `substructure_search`, `tanimoto_similarity` and `bulk_similarity` tools already ship; what is missing is a library-wide index and a search endpoint behind them.
- Onboarding flow, sample projects, templates.

---

## 🔵 Future / Advanced (Phase 3+)
**Goal: extensibility, enterprise, scale, and moat.**

- **Extensibility SDK:** a decorator + Pydantic-I/O authoring path that generates the schema, registers the tool, and builds/digest-pins the image; custom agents/skills and custom models; remote-HTTP tools; per-org/user tool scoping with admin approval and name-spacing; plugin marketplace. *(The sandboxed container-tool runtime and the `glowsky-tool.yaml` registration seam already shipped in Phase 0 — `services/tools/runtimes/container.py`, `services/tools/manifest.py`, five examples under `examples/tools/` — opt-in behind `GLOWSKY_ENABLE_CONTAINER_TOOLS=true` **and** `GLOWSKY_TOOLS_DIR`, both off by default; see `13-chemistry-tools-architecture.md` §6. `Runtime.REMOTE_HTTP` is still only an enum member.)*
- **Public API (REST/GraphQL) + Python SDK;** webhooks; embedded notebook compute.
- **Enterprise:** SSO/SAML/SCIM, admin console, audit export, CMK/BYOK, SOC 2, self-hosted Helm + air-gapped mode.
- **Patent/IP-aware search** (with explicit non-legal-advice framing); FTO support.
- **Advanced structure-based design:** pharmacophore modeling, MD-adjacent triage, free-energy-perturbation hooks, ensemble docking, gnina/ML scoring.
- **Real-time collaborative editing** (multiplayer workspace).
- **Pareto / trade-off views** over MPO axes; active-learning design loops. *(MMP-based SAR mining shipped ahead of plan — `services/chemistry/mmp.py` behind the `matched_pairs` and `sar_transforms` tools, with its own Matched Pairs & SAR screen in the desktop app.)*
- **Reaction/synthesis planning** integration with building-block catalogs (Enamine, etc.).
- **ELN/LIMS integrations** (Benchling, etc.).
- **Beyond small molecules:** basic peptide/PROTAC/covalent support.
- **Managed inference option** (for users without keys) + fine-tuned chemistry models.
- **Org knowledge graph / SAR mining across projects** — today's MMP tools mine a caller-supplied set of molecules, not an org-wide corpus.

---

## Prioritization rationale
- **BYO-LLM is MVP, not optional** — it's the economic + trust wedge (near-zero inference cost for us; IP control for users).
- **Docking in MVP (basic)** — it's a key "wow" for both personas and validates the heavy-worker architecture early. Kept minimal (one engine, small batches).
- **RAG/literature deferred to V1** — valuable but not core to the design-loop "aha," and ingestion/citation quality is a rabbit hole.
- **Extensibility *SDK* deferred to Phase 3** — the typed tool registry and a sandboxed container-tool seam landed in Phase 0 (`13-chemistry-tools-architecture.md` §6), so what remains is the authoring SDK, governance (org scoping, admin approval, name-spacing) and distribution, not the abstraction itself; the public registry contract is deliberately stabilized through real internal use before it is exposed.
- **Collaboration in V1** — MVP can be single-user-deep; teams matter once the loop is proven.

See `09-roadmap.md` for sequencing and `10-tech-stack.md` for the implementing stack.
