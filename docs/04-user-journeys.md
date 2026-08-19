# Glowsky — User Journey Maps

Two end-to-end journeys illustrating how the product feels in practice.

**These are target-state journeys** — the experience the product is being built toward, not a walkthrough of what runs today. Per-feature build status lives in `03-feature-spec.md` (✅ shipped · 🟡 partial · ⏳ planned) and `09-roadmap.md`; the gap between these stories and the current code is summarized in the cross-cutting notes at the end.

---

## Journey 1 — Maya (PhD student): hit-to-lead optimization for a thesis project

**Context:** Maya has a confirmed hit against a kinase target and a PDB co-crystal structure. She has a free Groq key and her own cheap Anthropic key.

### 1. Onboarding (Day 1, ~5 min)
- Signs up with ORCID. Picks **Academic (free)** tier.
- Prompted to **connect an LLM**: pastes her Anthropic + Groq keys. Glowsky validates them, suggests routing (Claude for reasoning, Groq/Llama for fast triage).
- Creates project **"KIN-X hit-to-lead,"** sets goal profile: *improve potency, keep MW<450, logP 1–3, avoid hERG, must be synthesizable.*

### 2. Seeding the project (~10 min)
- Pastes her hit's SMILES → instantly canonicalized, rendered in 2D, physchem props auto-computed.
- Uploads the target PDB; Glowsky shows the 3D structure and detects the binding pocket from the co-crystallized ligand.
- Uploads two key papers → indexed into project literature RAG.

### 3. The design loop (the magic moment, ~20 min)
- In Composer: *"Generate 40 analogs of @hit-1 that keep the hinge-binding motif, improve predicted potency, MW<450, logP 1–3, no PAINS/hERG flags, and are synthesizable."*
- Agent shows a **plan**: generate → validate/canonicalize → property filter → alert filter → ADMET predict → SA-score → rank. Streams progress.
- Returns **18 candidates** as a sortable grid with 2D depictions + property columns (MPO desirability, physchem, ADMET endpoints where a backend is configured, SA-score) + confidence badges. Maya sorts by **MPO desirability** and filters on SA-score — potency itself is never scored here; it is only ever *proxied*, one step later, by the docking score.
- Selects top 6 → *"Dock these against @KIN-X.pdb in the ATP pocket."* Agent runs Vina, returns poses + scores.
- Opens the best pose in 3D, sees the H-bond to the hinge highlighted. Uses **Cmd+K** on one analog: *"add a fluorine to block this metabolic soft spot"* → inline preview → accept.

### 4. Reasoning & record (~10 min)
- Asks: *"Why might analog 12 be more potent than the hit?"* → agent explains using interactions + literature, **with citations**.
- Logs a **hypothesis**: "Hinge H-bond + ortho-F improves potency & metabolic stability." Links the 3 supporting analogs.

### 5. Output (~5 min)
- *"Export this campaign as a Jupyter notebook."* → gets a runnable notebook (RDKit code, the molecules, docking setup, plots) for her thesis appendix.
- *"Generate a report."* → a Markdown report with structures, predictions, rationale, and citations for her advisor.

**Outcome:** In ~1 hour, no glue code, fully reproducible, costing her only her own (small) API spend. **This is the activation moment.**

---

## Journey 2 — David (professional med chemist): lead optimization in a biotech program

**Context:** David leads a lead-op program. Doesn't code. His org uses Glowsky **Team** tier; Dr. Chen has registered an internal ADMET model and internal docking as custom tools. Sign-in is the org's SSO, federated by the nakitte-carbon-auth platform Glowsky delegates identity to — Glowsky itself stores no user credentials. Models are pinned to org-scoped credentials for IP control: Claude on the org's own Anthropic account, with a self-hosted OpenAI-compatible endpoint (the `local` provider) for anything that must stay in-VPC.

### 1. Morning triage
- Opens shared project **"Program LOptX."** Sees the team library, recent agent runs, and a teammate's comment on a scaffold.
- The lead series has a **hERG liability** and **poor metabolic stability**.

### 2. No-code design (the core experience for David)
- Composer: *"Make 25 analogs of @Lead-12 that reduce predicted hERG and improve metabolic stability, keep potency, and stay synthesizable. Use our internal ADMET model."*
- Agent uses Chen's **custom internal ADMET tool**, generates + filters, returns ranked candidates with the org's predictions and uncertainty.
- David thinks in structures: opens the **molecule diff** between Lead-12 and a top analog — sees the basic amine replaced by a bioisostere, predicted hERG risk down on the org's model, MPO/physchem profile held.

### 3. Synthesis gut-check
- *"Which of these are realistically synthesizable in <4 steps from commercial building blocks?"* → retrosynthesis/ SA tool ranks them; flags 3 as easy.
- Selects 8 promising, synthesizable, IP-aware candidates.

### 4. IP & literature
- *"Has anything close to these been published or patented?"* → similarity + RAG over patents/literature, returns nearest known compounds with citations and a **clear disclaimer** that this isn't formal FTO.

### 5. Decision & handoff
- Tags 8 molecules **"propose for synthesis,"** writes rationale, @mentions a teammate.
- Updates the **hypothesis**: "Amine→bioisostere reduces hERG without potency loss." Links data.
- Generates a **DRC-ready report** with structures, predictions, rationale, and provenance (which model/tool produced each number) for the design-review committee.

**Outcome:** David ran a full optimization cycle in an afternoon, in plain English, using the org's controlled models and internal tools, without waiting on the modeling team. Provenance makes it defensible in the DRC.

---

## Cross-cutting journey notes
- **Trust touchpoints:** plan transparency, tool-call visibility, confidence/uncertainty, provenance, citations, accept/reject diffs. These appear in *both* journeys and are central to adoption by skeptical experts.
- **Progressive disclosure:** Maya/Chen drill into raw params, code, and notebooks; David stays in NL + visuals. Same engine, different surface depth.
- **BYO-LLM in practice:** Maya = personal keys; David's org = org-scoped credentials plus a self-hosted OpenAI-compatible endpoint for in-VPC routing. The product abstracts both behind the same model-routing layer. Four providers ship — **Anthropic, OpenAI, Groq and `local`** (any OpenAI-compatible base URL) — plus a deterministic offline mock; Bedrock, Azure and Vertex are ⏳ (`03-feature-spec.md` H1), and a route naming an unsupported provider quietly degrades to the mock rather than erroring.
- **Potency is not a Glowsky prediction.** Ranking is multi-parameter desirability (MPO over physchem descriptors), alongside ADMET endpoints and SA-score; the only structure-based potency proxy is the docking score (Vina affinity, kcal/mol) — a proxy, not a predicted IC50/Ki. Both of those inputs are adapter-gated: `predict_admet` and `dock` are advertised to the model but refuse with a 501 until a backend or container tool is registered (`03-feature-spec.md` C3/C4). A genuine potency/QSAR model arrives as the user's or org's own registered tool (`03-feature-spec.md` F1), not as a built-in.
- **Where these journeys run ahead of the build.** Shipped today: the Composer design loop with MPO ranking, the molecule diff, retrosynthesis + SA scoring, the adapter-gated `dock` and `predict_admet` seams, and Markdown/Jupyter export of a run. Still ⏳: literature and patent RAG with citations (`03-feature-spec.md` C6), pocket detection from a co-crystallized ligand (C4), hypothesis and decision tracking (D3), comments and @mentions (E2), PDF reports and plots (D4), and subscription tiers (G2). Free-text **Cmd/Ctrl+K** edits hand off to the Composer instead of previewing inline (A3), and Chen's internal tools need the container-tool seam switched on with **both** `GLOWSKY_ENABLE_CONTAINER_TOOLS=true` **and** `GLOWSKY_TOOLS_DIR` (F1).
