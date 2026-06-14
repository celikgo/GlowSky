# Glowsky — Development Roadmap

Phased plan. Durations are indicative for a small team (≈3–6 engineers + 1 chemistry/CADD advisor); compress with more people. Each phase ends with a clear, demoable milestone and a "definition of done."

---

## Phase 0 — Foundation & Architecture *(~4–6 weeks)*
**Objective:** de-risk the hard parts, set up the skeleton, prove the two scariest integrations (BYO-LLM gateway + deterministic chemistry-as-tools).

**Workstreams**
- **Repo & infra scaffold:** monorepo, CI/CD, containerized dev env, IaC baseline, secrets manager wired.
- **LLM Gateway spike:** unified provider interface (LiteLLM-class) + streaming + one secure key flow across 2 providers + 1 local (Ollama). Capability flags + basic routing.
- **Chemistry Service spike:** RDKit worker behind a typed tool API (canonicalize, descriptors, enumerate analogs). Job queue + worker isolation proven.
- **Agent orchestrator spike:** LLM plans a 2–3 step tool sequence, executes via the registry, streams results. Trace persisted.
- **Data layer:** Postgres schema v0 (orgs/users/projects/molecules/versions/runs), object storage, vector store provisioned.
- **Security baseline:** KMS key storage, tenant scoping, TLS, authz middleware, audit skeleton.

**Definition of done:** a thin vertical slice — "paste SMILES → ask the agent (using *your* key) to make 5 analogs → validated structures returned & stored" — works end-to-end in dev.

**Key decisions locked:** stack (see `10`), tool-registry contract, provenance schema, deployment shape.

---

## Phase 1 — MVP (Core Experience) *(~10–14 weeks)*
**Objective:** ship the complete agentic design loop with BYO-LLM, polished enough for Maya (and usable by David). Closed beta with design partners.

**Build (per `08` MVP list):**
- Auth + org/project model; onboarding to connect an LLM key.
- Molecule import/paste/edit (2D editor), RDKit validation, 2D render, 3D single-molecule view.
- Library/grid with property columns; SMILES/CSV/SDF I/O; molecule diff.
- Chemistry core: physchem descriptors, druglikeness, alerts; analog/R-group enumeration; filtering/ranking; **one ADMET predictor**; **basic Vina docking** + pose view.
- Agent: Composer chat (stream + tool-call viz), `@`-context, the chained design workflow, Cmd+K inline, accept/reject diffs.
- Output: Jupyter notebook export + Markdown report.
- Async workers + WS progress; the MVP security non-negotiables.

**Milestones**
- M1: Workspace + molecule editing/visualization + library (no agent yet).
- M2: Agent chat + tool calls + analog generation + filtering (the loop without docking).
- M3: Docking + ADMET + notebook/report export → **feature-complete MVP**.
- M4: Closed beta hardening, telemetry, bug-bash, perf (sub-second UI, fast render, streaming).

**Definition of done:** design partners run the Maya journey unaided and produce a reproducible notebook. Activation metric instrumented.

---

## Phase 2 — Advanced Chemistry + Teams *(~12–16 weeks)*
**Objective:** deepen science so David adopts fully and teams collaborate; broaden provider support; public launch.

**Build (per `08` V1 list):**
- Generative: scaffold hopping, bioisosteres, de novo profile-targeting; integrate an ML generative model.
- Fuller ADMET suite + applicability domain; MPO-style scoring early version.
- Retrosynthesis + synthesizability scoring.
- Literature RAG with citations (PubMed/PMC + user docs).
- Batch docking + interaction analysis.
- Hypothesis/experiment tracking + decision log.
- Collaboration: sharing, roles, comments, activity feed.
- Model-routing UI, cost/usage visibility, more providers (xAI/Groq/Together/Mistral/Bedrock/Azure/Vertex).
- Workflow templates; richer PDF reporting; substructure/similarity search at scale.

**Milestones**
- M5: Advanced generative + retrosynthesis + RAG.
- M6: Collaboration + teams + routing/cost UI.
- M7: **Public launch** (Pro + Team tiers), pricing, billing, marketing site.

**Definition of done:** David journey works end-to-end with team sharing; paid conversion live; RAG citations trustworthy.

---

## Phase 3 — Polish, Extensibility & Enterprise *(~12–20 weeks, ongoing)*
**Objective:** build the moat (extensibility) and unlock enterprise revenue.

**Build (per `08` Future list):**
- **Extensibility SDK:** custom tools, custom agents/skills, custom models; stable tool-registry public contract; (later) plugin marketplace.
- **Public API + Python SDK**, webhooks, embedded notebook compute.
- **Enterprise:** SSO/SAML/SCIM, admin console, audit export, CMK/BYOK, **self-hosted Helm chart + air-gapped mode**, **SOC 2 Type II**.
- Advanced SBDD (pharmacophore, ensemble/ML docking, FEP hooks), patent/IP-aware search (non-legal framing).
- Real-time collaboration; active-learning design loops; SAR mining.
- ELN/LIMS integrations.

**Milestones**
- M8: Extensibility SDK + API (Dr. Chen registers a custom tool/agent).
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
