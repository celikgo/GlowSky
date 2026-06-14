# Glowsky

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-54%20passing-brightgreen.svg)](tests/)
[![Status: Phase 0](https://img.shields.io/badge/status-Phase%200%20scaffold-orange.svg)](docs/09-roadmap.md)
[![Code style: RDKit](https://img.shields.io/badge/chemistry-RDKit-26a69a.svg)](https://www.rdkit.org/)

**The AI-native workspace for small-molecule drug design — "Cursor for Chemists."**

Glowsky is an AI-first environment where medicinal chemists and computational drug-discovery researchers design, optimize, analyze, and manage small molecules through natural language and intelligent agents — combining IDE-grade ergonomics, deep chemistry tooling (RDKit, docking, ADMET, retrosynthesis, literature RAG), and **Bring-Your-Own-LLM** support, available as SaaS and self-hosted.

> **Status:** Phase 0 scaffold. The product & architecture docs live in `docs/`; a runnable backend vertical slice (LLM gateway + chemistry + agent design loop) lives in `services/`, `apps/`, and `tests/`. See **Getting Started** below.

---

## The core idea
Express your design *intent* in natural language; a chemistry-aware agent **plans** and orchestrates **validated tools** to execute it. LLMs reason and explain; deterministic chemistry (RDKit, predictors, docking) computes. The molecule is a first-class, versioned, visualizable object — never a hallucinated string. Use your own LLM keys (Claude, GPT, Grok, Groq, local models…), routed per task.

---

## Documentation index

| # | Document | What's inside |
|---|---|---|
| 01 | [Product Vision & Goals](docs/01-product-vision.md) | Problem, vision, principles, positioning, success metrics |
| 02 | [Target User Personas](docs/02-personas.md) | Maya (PhD), David (med chemist), Dr. Chen (CADD), admin & founder |
| 03 | [Feature Specification](docs/03-feature-spec.md) | All major features broken down (agent, molecules, chemistry, projects, BYO-LLM, extensibility) |
| 04 | [User Journey Maps](docs/04-user-journeys.md) | End-to-end journeys for the PhD student and the professional chemist |
| 05 | [Technical Architecture](docs/05-technical-architecture.md) | System layers, components, key flows, deployment shapes |
| 06 | [Data Models](docs/06-data-models.md) | High-level entities, relationships, provenance, indexing |
| 07 | [Security & Privacy](docs/07-security-privacy.md) | Threat model, BYO-LLM credential security, IP protection, sandboxing |
| 08 | [Feature Prioritization](docs/08-feature-prioritization.md) | MVP / V1 / Future with rationale |
| 09 | [Development Roadmap](docs/09-roadmap.md) | Phases 0–3 with milestones & definitions of done |
| 10 | [Technical Stack](docs/10-tech-stack.md) | Recommended stack with reasoning & alternatives |
| 11 | [Folder Structure & System Design](docs/11-folder-structure.md) | Monorepo layout, boundaries, runtime topology |
| 12 | [Risks & Mitigations](docs/12-risks.md) | Key technical risks and how we address them |
| 13 | [Chemistry Tools Subsystem Architecture](docs/13-chemistry-tools-architecture.md) | Scalable, reproducible, extensible tool layer — contract, execution, scaling, SDK, tool catalog |

---

## Getting Started (Phase 0 scaffold)

Phase 0 proves the two hardest integrations end-to-end: the **BYO-LLM gateway** and
**deterministic chemistry-as-tools**, wired through an **agentic design loop**. It runs
**fully offline** (a built-in mock LLM) so no API key is needed to try it.

> Requires Python 3.11–3.13 (RDKit has no 3.14 wheels yet). Homebrew `python3.13` works.

```bash
make venv && make install     # create .venv313 + install (editable)
make test                     # 54 tests: firewall, tools subsystem, slow-path + streaming, container runtime, gateway, agent loop, API, auth/tenancy
make demo                     # run a sample design loop, print results + provenance
make run                      # start the API at http://localhost:8000  (/docs for Swagger)
```

**Try the design loop** (offline mock by default):

```bash
curl -s localhost:8000/agent/design -H 'content-type: application/json' -d '{
  "goal": "Make 12 analogs with MW<300, logP 1-3, no PAINS, drug-like",
  "seed_smiles": "c1ccccc1C(=O)O"
}' | python -m json.tool
```

**Use your own LLM:** copy `.env.example` → `.env`, set a key (e.g.
`GLOWSKY_ANTHROPIC_API_KEY`) and route (e.g. `GLOWSKY_ROUTE_REASONING=anthropic/claude-opus-4-8`).
With no keys set, every task class gracefully falls back to the offline mock.

**Slow path & streaming.** Heavy tools (conformers, docking, batch library jobs) run
off the request thread and stream progress. Submit a job, then stream its events:

```bash
# Batch-profile a library; per-item results stream as they complete
JOB=$(curl -s localhost:8000/jobs/batch -H 'content-type: application/json' -d '{
  "tool": "profile_molecule",
  "items": [{"canonical_smiles":"CCO"},{"canonical_smiles":"c1ccccc1C(=O)O"}]
}' | python -c 'import sys,json;print(json.load(sys.stdin)["job_id"])')
# Stream events over WebSocket:  ws://localhost:8000/jobs/$JOB/stream
curl -s localhost:8000/jobs/$JOB | python -m json.tool   # or poll
```

With **no `GLOWSKY_REDIS_URL`**, Celery runs *eager* (in-process) — the slow path works
with zero infra. To run the **real distributed path**: set `GLOWSKY_REDIS_URL`, start
Redis (`make redis`) and a worker (`make worker`), or `docker compose up`. Same code,
same events; jobs now execute on workers and stream over Redis.

**Container tools (bring-your-own model).** A researcher packages their tool as a Docker
image that speaks the tool ABI (read JSON args on stdin, write `{"ok",result}` on stdout)
and drops a `glowsky-tool.yaml` under `GLOWSKY_TOOLS_DIR`. Glowsky registers it as a
first-class, agent-callable tool — with the **same cache, firewall, and provenance** as
built-ins — and runs it **fully sandboxed**: `--network none --read-only --cap-drop ALL
--security-opt no-new-privileges`, non-root, memory/cpu/pids caps, and a hard timeout.

```bash
make tool-example        # build examples/tools/molecular_formula -> a container tool
GLOWSKY_TOOLS_DIR=examples/tools make run     # API now lists `molecular_formula`
curl -s localhost:8000/tools/molecular_formula -d '{"args":{"canonical_smiles":"CCO"}}' \
  -H 'content-type: application/json'         # runs the sandboxed container, returns formula
```

**Real ADMET backend (`examples/tools/admet_ai/`).** A production-grade example: the open
**ADMET-AI** predictor (pretrained Chemprop-RDKit GNN over ~40 Therapeutics Data Commons
endpoints — solubility, hERG, CYP, Caco-2, BBB, clearance, …) packaged as a container tool.
Model weights are baked into the image at build time, so it predicts **fully offline**
under `--network none`.

```bash
make tool-admet          # build glowsky-tool-admet-ai (large: torch; takes a few min)
GLOWSKY_TOOLS_DIR=examples/tools make run
curl -s localhost:8000/tools/admet_ai -H 'content-type: application/json' \
  -d '{"args":{"canonical_smiles":"CC(=O)Oc1ccccc1C(=O)O","endpoints":["Solubility","hERG","BBB"]}}'
# -> real ADMET predictions, sandboxed, with image-pinned provenance
```

This is how the ADMET seam (`predict_admet`, docs/13 §10) is satisfied by a real model
with **zero Glowsky code changes** — just an image + a `glowsky-tool.yaml`.

### Run the whole stack on Docker

```bash
make tool-example         # build the example container tool image (on the host daemon)
docker compose up --build # redis + api + worker (same image), API at :8000
```

`docker compose` runs Redis + the API + a Celery worker. The worker mounts the host
Docker socket so it can launch sandboxed **container tools** (docker-out-of-docker).
Verified end-to-end: API → Redis → worker → `docker run` (sandboxed tool) → streamed
result with image-pinned provenance.
> The socket mount is root-equivalent on the host — fine for local dev; production
> should use a rootless/sysbox/gVisor builder or a dedicated tool-runner service.

### What's implemented in Phase 0
| Area | Module | Notes |
|---|---|---|
| **Deterministic firewall** | `services/chemistry/validation.py` | Every structure (incl. LLM-emitted) is validated/canonicalized before it's trusted or stored |
| **Chemistry tools (15)** | `services/chemistry/*` | Validation, descriptors, druglikeness, PAINS/BRENK, fingerprints, Tanimoto (single+bulk), substructure search, Murcko scaffolds, SA score, analog enumeration, ETKDG conformers; ADMET + docking as adapter-gated seams |
| **Tool execution subsystem** | `services/tools/` | The scalable seam (docs/13): versioned `ToolSpec` contract, registry, `ToolExecutionService` (cache + firewall + provenance + compute-class routing) |
| **Slow path + streaming** | `services/tools/queue/`, `store.py` | Celery tasks for heavy/batch tools; append-only `JobStore` (in-memory eager **or** Redis); `POST /jobs`, `/jobs/batch`, `GET /jobs/{id}`, and **`WS /jobs/{id}/stream`** relaying queued→running→item→completed live |
| **Container-tool runtime** | `services/tools/runtimes/container.py`, `manifest.py`, `examples/tools/` | Bring-your-own model as a sandboxed Docker tool: JSON-stdin/stdout ABI, `glowsky-tool.yaml` manifests, strict isolation. Registered like any built-in (cache/firewall/provenance) |
| **Docker deployment** | `docker-compose.yml`, `infra/docker/` | Redis + API + worker on one image; worker mounts the Docker socket to launch sandboxed tool containers |
| **BYO-LLM gateway** | `services/llm_gateway/` | LiteLLM-backed multi-provider access + offline mock; task-class routing; keys resolved only at call time, never logged |
| **Agent orchestrator** | `services/agent/orchestrator.py` | Plan (LLM) → generate → profile → filter → rank → synthesize (LLM); every chemistry call routes through the execution service, with a full provenance trace |
| **API + persistence** | `apps/api/` + `services/core/` | FastAPI endpoints incl. generic `POST /tools/{name}`; runs + molecules stored with provenance (`origin_run_id`) in SQLite |
| **Auth & tenancy** *(Phase 1)* | `services/core/auth.py`, `apps/api/deps.py` | Org/user/membership/project model, bearer **API-key** auth (hash-at-rest), tenant-scoped projects/runs/molecules, and an audit trail — all gated behind `GLOWSKY_AUTH_ENABLED` so dev mode stays zero-setup |

Layout follows `docs/11-folder-structure.md` + `docs/13-chemistry-tools-architecture.md`.
Phase 1 (in progress) adds the auth/tenancy spine (done — see below), and next wires the
slow-path Celery/Redis queue, real ADMET/docking backends, WebSocket streaming polish,
2D/3D viewers, and notebook export.

**Auth & multi-tenancy (Phase 1).** Off by default — every request resolves to a built-in
local owner, so the Phase 0 commands above need no token. Flip `GLOWSKY_AUTH_ENABLED=true`
to require a per-org **bearer API key**; data is then isolated per tenant.

```bash
# Mint an org + API key (the key is shown exactly once):
KEY=$(curl -s localhost:8000/auth/signup -H 'content-type: application/json' \
  -d '{"email":"maya@lab.edu","org_name":"Maya Lab"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["api_key"])')

# Create a project and run a design scoped to it (only this org can see it):
PID=$(curl -s localhost:8000/projects -H "authorization: Bearer $KEY" \
  -H 'content-type: application/json' -d '{"name":"Kinase series"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s localhost:8000/agent/design -H "authorization: Bearer $KEY" \
  -H 'content-type: application/json' \
  -d "{\"goal\":\"make 8 analogs, MW<300, no PAINS\",\"seed_smiles\":\"c1ccccc1C(=O)O\",\"project_id\":\"$PID\"}"
curl -s localhost:8000/projects/$PID/runs -H "authorization: Bearer $KEY"   # provenance, scoped
```

> Bearer API keys are the Phase 1 auth primitive (fully testable headlessly). Email/OAuth
> (Google/GitHub/ORCID) sign-in arrives with the frontend; the org/membership model is
> already in place for it. Schema evolution currently uses `create_all`; Alembic migrations
> are the next follow-up.

---

## TL;DR of the plan

- **Who:** PhD/academic researchers (lead persona), professional med chemists, CADD scientists (champions), → teams & enterprise.
- **Wedge:** the agentic design loop + IDE ergonomics + BYO-LLM economics — no incumbent has all three.
- **MVP litmus test:** with your own LLM key, take a molecule from a natural-language prompt to a validated, visualized, property-annotated, docked, exportable result — **without writing code.**
- **Stack:** Next.js/TS frontend (RDKit-JS, Mol*, Ketcher, Monaco); Python/FastAPI backend; LangGraph agent; LiteLLM-based BYO-LLM gateway; RDKit + Vina + ADMET/REINVENT/AiZynth chemistry; Postgres + pgvector + Redis + S3/MinIO; Docker/K8s + Helm for SaaS & self-host.
- **Two existential risks handled in Phase 0:** chemistry hallucination (deterministic firewall + validation) and credential/IP security (KMS-backed gateway, tenant isolation).
- **Roadmap:** Phase 0 foundation → Phase 1 MVP (core loop) → Phase 2 advanced chemistry + teams → Phase 3 extensibility + enterprise.
