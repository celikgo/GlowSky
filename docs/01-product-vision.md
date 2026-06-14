# Glowsky — Product Vision & Goals

## One-line pitch
**Glowsky is "Cursor for Chemists"** — an AI-native workspace where medicinal chemists and computational researchers design, optimize, analyze, and manage small molecules through natural language, intelligent agents, and rich molecular visualization.

## The problem
Small-molecule drug design today is fragmented across disconnected tools:
- **Cheminformatics** lives in RDKit scripts, Jupyter notebooks, and KNIME pipelines.
- **Visualization** happens in PyMOL, Maestro, MOE, or DataWarrior.
- **Property/ADMET prediction** is scattered across web servers, commercial suites, and home-grown models.
- **Literature & IP** research happens in PubMed, SciFinder, Reaxys, and patent databases — fully siloed from the design loop.
- **Knowledge** (hypotheses, SAR rationale, why a molecule was abandoned) lives in people's heads, slide decks, and ELN free-text.

A chemist with a design idea must context-switch across 5–10 tools, write glue code, and manually carry insight between them. The feedback loop from *idea → molecule → prediction → decision* is slow, manual, and lossy.

LLMs can now reason about chemistry, but generic chat tools (ChatGPT, Claude) hallucinate structures, can't render or validate molecules, have no persistent project memory, and can't call real cheminformatics tools deterministically.

## The vision
A single, fast, modern workspace where the chemist's *intent* — expressed in natural language, sketches, or direct edits — is the primary interface, and a chemistry-aware agent orchestrates validated tools (RDKit, docking, predictors, retrosynthesis, literature RAG) to execute it. The molecule is a first-class, version-controlled, visualizable object — never a hallucinated string.

Think: the ergonomics and "flow state" of Cursor/VS Code, applied to molecular design instead of source code.

## Core principles
1. **AI-first, not AI-bolted-on.** The agent and chat are the spine of the product, not a sidebar afterthought. Every object (molecule, project, assay result) is addressable by the agent.
2. **Deterministic chemistry, probabilistic reasoning.** LLMs *plan and explain*; validated tools (RDKit, predictors, docking) *compute*. We never trust an LLM to emit a final SMILES without canonicalization/validation.
3. **Bring Your Own LLM.** Researchers and enterprises must control which model touches their IP and where API spend goes. Model choice is a first-class setting, routable per-task.
4. **The molecule is a first-class citizen.** Versioned, diffable, visualizable in 2D/3D, annotatable — like a file in an IDE.
5. **Provenance & reproducibility.** Every prediction, generation, and decision is traceable to the tool, model, parameters, and prompt that produced it. Exportable to a notebook or report.
6. **Trust through transparency.** Show the agent's plan, the tools it called, and confidence/uncertainty. Chemists are skeptical experts; the product earns trust by showing its work.
7. **Meet users where they are.** Import/export SMILES, SDF, MOL, FASTA, PDB; export to Jupyter; integrate with existing ELNs over time.

## Goals (what success looks like)

### Product goals
- A chemist can go from *natural-language design idea* to *validated, visualized, property-annotated molecule set* in minutes, without leaving the app or writing code.
- The agent reliably calls real chemistry tools and never silently fabricates structures or properties.
- Users feel the same "flow" and speed they get from Cursor — sub-second UI, instant molecule rendering, streaming agent responses.

### Business goals
- **SaaS** product with tiered subscriptions (Free/academic, Pro, Team, Enterprise).
- **Self-hosted / VPC** deployment for pharma and enterprise with strict IP-control requirements.
- Land in academia (low-friction, BYO-LLM keeps our inference costs near zero) → expand into biotech/pharma teams.

### Non-goals (explicitly out of scope, at least initially)
- We are **not** building our own foundation LLM.
- We are **not** building a wet-lab LIMS/ELN of record (we integrate with them later).
- We are **not** targeting large-molecule/biologics design in V1 (antibodies, peptides beyond basic support) — focus is **small molecules**.
- We are **not** shipping our own docking engine or QM package — we wrap best-in-class open tools (AutoDock Vina, etc.) and allow plug-ins.

## Positioning & differentiation
| Competitor / category | What they do | Where Glowsky wins |
|---|---|---|
| Generic LLM chat (ChatGPT/Claude) | General reasoning | Real validated tools, molecule rendering, persistent projects, no hallucinated structures |
| Schrödinger / MOE / Cresset | Deep physics-based suites | Modern AI-native UX, NL interface, BYO-LLM, far lower cost, fast onboarding |
| Open cheminformatics (RDKit/KNIME) | Powerful but code-heavy | No-code/low-code NL interface, integrated agent, visualization, collaboration |
| ELNs (Benchling, etc.) | Record-keeping | Active *design & reasoning* loop, generative + predictive AI |
| Newer AI-drug-design startups | Often model-as-a-service, closed | Open BYO-LLM, IDE ergonomics, extensibility, self-hostable |

**The wedge:** the *agentic design loop* + *IDE ergonomics* + *BYO-LLM economics* together — no incumbent offers all three.

## Success metrics (early)
- **Activation:** % of new users who design/import a molecule and run ≥1 agent action in week 1.
- **Loop velocity:** median time from a design prompt to a validated, property-annotated candidate.
- **Retention:** weekly active design sessions per user; projects with >1 week of activity.
- **Trust:** % of agent tool-call outputs accepted vs. corrected; hallucination/error reports.
- **Expansion:** academic → team conversion; seats per paying org.
