# Glowsky — User Journey Maps

Two end-to-end journeys illustrating how the product feels in practice.

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
- Returns **18 candidates** as a sortable grid with 2D depictions + property columns + confidence badges. Maya sorts by predicted potency, filters SA-score.
- Selects top 6 → *"Dock these against @KIN-X.pdb in the ATP pocket."* Agent runs Vina, returns poses + scores.
- Opens the best pose in 3D, sees the H-bond to the hinge highlighted. Uses **Cmd+K** on one analog: *"add a fluorine to block this metabolic soft spot"* → inline preview → accept.

### 4. Reasoning & record (~10 min)
- Asks: *"Why might analog 12 be more potent than the hit?"* → agent explains using interactions + literature, **with citations**.
- Logs a **hypothesis**: "Hinge H-bond + ortho-F improves potency & metabolic stability." Links the 3 supporting analogs.

### 5. Output (~5 min)
- *"Export this campaign as a Jupyter notebook."* → gets a runnable notebook (RDKit code, the molecules, docking setup, plots) for her thesis appendix.
- *"Generate a report."* → Markdown/PDF with structures, predictions, rationale, citations for her advisor.

**Outcome:** In ~1 hour, no glue code, fully reproducible, costing her only her own (small) API spend. **This is the activation moment.**

---

## Journey 2 — David (professional med chemist): lead optimization in a biotech program

**Context:** David leads a lead-op program. Doesn't code. His org uses Glowsky **Team** tier; Dr. Chen has registered an internal ADMET model and internal docking as custom tools. SSO via Okta. Models routed to the org's Bedrock (Claude) for IP control.

### 1. Morning triage
- Opens shared project **"Program LOptX."** Sees the team library, recent agent runs, and a teammate's comment on a scaffold.
- The lead series has a **hERG liability** and **poor metabolic stability**.

### 2. No-code design (the core experience for David)
- Composer: *"Make 25 analogs of @Lead-12 that reduce predicted hERG and improve metabolic stability, keep potency, and stay synthesizable. Use our internal ADMET model."*
- Agent uses Chen's **custom internal ADMET tool**, generates + filters, returns ranked candidates with the org's predictions and uncertainty.
- David thinks in structures: opens the **molecule diff** between Lead-12 and a top analog — sees the basic amine replaced by a bioisostere, hERG risk down, potency predicted maintained.

### 3. Synthesis gut-check
- *"Which of these are realistically synthesizable in <4 steps from commercial building blocks?"* → retrosynthesis/ SA tool ranks them; flags 3 as easy.
- Selects 8 promising, synthesizable, IP-aware candidates.

### 4. IP & literature
- *"Has anything close to these been published or patented?"* → similarity + RAG over patents/literature, returns nearest known compounds with citations and a **clear disclaimer** that this isn't formal FTO.

### 5. Decision & handoff
- Tags 8 molecules **"propose for synthesis,"** writes rationale, @mentions a teammate.
- Updates the **hypothesis**: "Amine→bioisostere reduces hERG without potency loss." Links data.
- Generates a **DRC-ready report** (PDF) with structures, predictions, rationale, and provenance (which model/tool produced each number) for the design-review committee.

**Outcome:** David ran a full optimization cycle in an afternoon, in plain English, using the org's controlled models and internal tools, without waiting on the modeling team. Provenance makes it defensible in the DRC.

---

## Cross-cutting journey notes
- **Trust touchpoints:** plan transparency, tool-call visibility, confidence/uncertainty, provenance, citations, accept/reject diffs. These appear in *both* journeys and are central to adoption by skeptical experts.
- **Progressive disclosure:** Maya/Chen drill into raw params, code, and notebooks; David stays in NL + visuals. Same engine, different surface depth.
- **BYO-LLM in practice:** Maya = personal keys; David's org = Bedrock/VPC routing. The product abstracts both behind the same model-routing layer.
