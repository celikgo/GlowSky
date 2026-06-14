# Glowsky — Target User Personas

We design for three primary personas and two secondary ones. The product must feel native to **both** a code-comfortable computational researcher and a structure-thinking bench medicinal chemist.

---

## Primary Persona 1 — "Maya," the PhD Student / Academic Researcher
**Role:** 3rd-year PhD in medicinal / computational chemistry. Works in an academic lab on a hit-to-lead project.

**Technical level:** Comfortable with Python, RDKit, Jupyter; not a software engineer. Hacks scripts together; hates maintaining infrastructure.

**Goals**
- Generate and prioritize molecule ideas around a scaffold for her target.
- Predict properties (logP, solubility, basic ADMET) and filter candidates fast.
- Run docking against a known PDB structure and rationalize binding.
- Stay current with literature and patents; cite sources in her thesis/papers.
- Produce reproducible figures and notebooks for publications.

**Pains**
- Limited budget — can't afford Schrödinger licenses. Uses free/open tools stitched together.
- Spends days writing glue code instead of doing science.
- Loses track of *why* she designed/rejected molecules months ago.
- Reproducibility pressure from advisors and reviewers.

**What wins her over**
- **Free/academic tier + BYO-LLM** (she has free API credits or a cheap key, or uses a local model).
- Open-tool integration (RDKit, Vina) she already trusts.
- One-click **Jupyter / report export** for her thesis.
- Literature RAG with real citations.

**Quote:** *"I don't want another expensive black box. I want my RDKit scripts, my docking, and a smart assistant — in one place, reproducible, that I can put in my paper."*

---

## Primary Persona 2 — "David," the Professional Medicinal Chemist
**Role:** Senior medicinal chemist at a mid-size biotech. Leads a lead-optimization program.

**Technical level:** Deep chemistry intuition; minimal coding. Thinks in structures, SAR, and synthetic feasibility. Lives in ChemDraw, ELN, and meetings.

**Goals**
- Rapidly explore R-group and scaffold ideas to improve potency while fixing ADMET liabilities (hERG, metabolic stability, solubility).
- Triage large virtual libraries down to a synthesizable, IP-clean shortlist.
- Assess synthetic feasibility / retrosynthesis before committing chemists' time.
- Track hypotheses and design rationale across the team; defend decisions in DRC meetings.

**Pains**
- Doesn't code — locked out of powerful cheminformatics without a comp-chem colleague.
- Slow back-and-forth with the modeling team for simple predictions.
- Design rationale and SAR knowledge scattered across decks and ELN.
- IP/freedom-to-operate anxiety.

**What wins him over**
- **No-code natural-language interface** — "make 20 analogs of this with lower logP and no hERG flag, that are synthesizable."
- Beautiful 2D/3D visualization and molecule diffing.
- Synthetic-feasibility + retrosynthesis gut-check.
- Team sharing of hypotheses and annotated molecule libraries.

**Quote:** *"I have the chemistry intuition. I just want to ask for what I want in plain English and see real, synthesizable structures with honest predictions — without filing a ticket with the modeling group."*

---

## Primary Persona 3 — "Dr. Chen," the Computational Chemist / CADD Scientist
**Role:** Computational chemistry / CADD lead at a biotech or pharma. Bridges biology, chemistry, and software.

**Technical level:** Strong Python, ML, cheminformatics, and modeling. Power user. Will push the tool to its limits.

**Goals**
- Run and orchestrate complex workflows (virtual screening, generative design + filtering cascades, free-energy-adjacent triage).
- Plug in **custom models, tools, and agents** (their own ADMET model, internal docking, proprietary scoring).
- Automate repetitive pipelines and standardize them for the team.
- Govern model usage, data residency, and reproducibility for the org.

**Pains**
- Becomes the bottleneck — everyone asks them for predictions and scripts.
- Reproducibility and standardization across the team is hard.
- Wants extensibility, not a walled garden.

**What wins them over**
- **Extensibility:** custom tools/agents via SDK, custom prompt templates, model routing.
- **Self-hosted / VPC** deployment with full data control.
- API access and scripting; export pipelines as code/notebooks.
- Acts as the internal champion who deploys Glowsky to the whole team.

**Quote:** *"If I can register my own scoring model and docking tool as agent actions, and self-host it in our VPC, I'll roll this out to every chemist and stop being a human API."*

---

## Secondary Persona 4 — "Sara," the Lab/Program Manager (Buyer/Admin)
**Role:** Manages a research team or platform; controls budget and procurement.

**Cares about:** seat management, SSO, billing, data-governance/compliance, ROI, audit logs. Not a daily user but a key **buyer** and **admin**. Needs admin console, usage analytics, and security documentation.

## Secondary Persona 5 — "Alex," the Biotech Founder / Small-team Generalist
**Role:** Early-stage startup; wears every hat. Wants to move fast with a small team.

**Cares about:** speed, low cost, all-in-one, minimal setup, collaboration. Will adopt the Team tier and grow into Enterprise.

---

## Persona → priority mapping
| Persona | MVP priority | Why |
|---|---|---|
| Maya (PhD) | **Highest** | Low-friction adopter, BYO-LLM keeps our costs ~0, drives bottom-up growth & word-of-mouth |
| David (Med chemist) | **High** | Core revenue persona; defines the no-code NL experience |
| Dr. Chen (CADD) | **High (champion)** | Extensibility + self-host; converts orgs; deferred features OK for MVP |
| Sara (Admin) | Phase 3 | Enterprise/Team monetization |
| Alex (Founder) | Phase 2 | Team-tier expansion |

**Design tension to hold:** Maya/Chen want power and code escape-hatches; David wants zero code. The interface must let the agent + NL serve David while exposing notebooks, SDK, and raw tool params for Maya/Chen. Progressive disclosure is the answer.
