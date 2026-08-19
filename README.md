# Glowsky

[![ci](https://github.com/celikgo/GlowSky/actions/workflows/ci.yml/badge.svg)](https://github.com/celikgo/GlowSky/actions/workflows/ci.yml)
[![validation](https://github.com/celikgo/GlowSky/actions/workflows/validation.yml/badge.svg)](https://github.com/celikgo/GlowSky/actions/workflows/validation.yml)
[![docker](https://github.com/celikgo/GlowSky/actions/workflows/docker.yml/badge.svg)](https://github.com/celikgo/GlowSky/actions/workflows/docker.yml)
[![migrations](https://github.com/celikgo/GlowSky/actions/workflows/migrations.yml/badge.svg)](https://github.com/celikgo/GlowSky/actions/workflows/migrations.yml)
[![security](https://github.com/celikgo/GlowSky/actions/workflows/security.yml/badge.svg)](https://github.com/celikgo/GlowSky/actions/workflows/security.yml)
[![docs-links](https://github.com/celikgo/GlowSky/actions/workflows/docs-links.yml/badge.svg)](https://github.com/celikgo/GlowSky/actions/workflows/docs-links.yml)

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)
[![Status: Early access](https://img.shields.io/badge/status-early%20access-blue.svg)](docs/09-roadmap.md)
[![Chemistry: RDKit](https://img.shields.io/badge/chemistry-RDKit-26a69a.svg)](https://www.rdkit.org/)

> The `validation` badge is the one worth clicking. It runs the benchmarks in
> [`docs/VALIDATION.md`](docs/VALIDATION.md) against published reference values —
> 1128 measured aqueous solubilities, and a ligand pose determined by X-ray
> crystallography — and it reports what fails as well as what passes.

**The AI-native workspace for small-molecule drug design — "Cursor for Chemists."**

Glowsky is an AI-first environment where medicinal chemists and computational drug-discovery researchers design, optimize, analyze, and manage small molecules through natural language and intelligent agents — combining IDE-grade ergonomics, deep chemistry tooling (RDKit descriptors and structural alerts, MPO scoring, matched molecular pairs/SAR, template retrosynthesis, plus opt-in ADMET and AutoDock Vina docking), and **Bring-Your-Own-LLM** support. Self-hostable today; literature RAG and a managed SaaS are planned (`docs/09-roadmap.md`).

> **Status:** Early access — self-hostable today; a managed/hosted SaaS is not GA yet. A working vertical slice runs end to end: the FastAPI backend (BYO-LLM gateway + validated chemistry tools + the agentic design loop) under `services/` and `apps/api/`, plus a Tauri desktop app (`apps/desktop/`) whose default screen is the **Composer** — a multi-turn chat front door over the design loop — alongside design, retrosynthesis, SAR/matched-pairs, docking, library, tools and settings screens, a ⌘K command palette and a molecule inspector. Product & architecture docs live in `docs/`. See **Getting Started** below.

---

## The core idea
Express your design *intent* in natural language; a chemistry-aware agent **plans** and orchestrates **validated tools** to execute it. LLMs reason and explain; deterministic chemistry (RDKit, predictors, docking) computes. The molecule is a first-class, visualizable, provenance-carrying object — never a hallucinated string (molecule *versioning* is still planned, `docs/03-feature-spec.md` B5). Use your own LLM keys (Anthropic Claude, OpenAI, Groq, or any OpenAI-compatible local endpoint such as Ollama/vLLM), routed per task class (reasoning / fast triage / codegen).

---

## What Glowsky is not

The core idea above has a second half that matters just as much, and it is the half a
tool in this domain usually gets wrong. **A predicted number is not a measurement.**
A predicted ADMET property or a docking score presented as a bare point estimate reads
like data and is not. So every predictor here returns its value together with:

- its **uncertainty** — an interval or a probability, never a lone number;
- its **applicability domain** — whether this molecule is even the kind of molecule the
  model was built for, with the individual checks visible;
- its **provenance** — which model, which version, fitted on what, and a citation that
  resolves. Every DOI in this repository is verified against Crossref on every push.

Concretely, and regardless of how anything is displayed:

- **A docking score is not a binding affinity.** It is a scoring-function value in
  kcal/mol.
- **A predicted hERG risk is not a cardiac safety assessment.** It is a structural flag
  for follow-up.
- **Passing a druglikeness rule battery predicts nothing.** Those rules describe where
  past drugs sat; they are not causes of why those drugs worked, and every one of them
  was published with exceptions.
- **An SA score is not a route** and does not mean a compound can be made.
- **None of this is a regulatory or safety assessment**, and nothing here is a substitute
  for an assay.
- **Most of it is not validated.** [`docs/VALIDATION.md`](docs/VALIDATION.md) is
  generated from a benchmark run and lists every capability with no benchmark behind it,
  plus what validating each would take. Seven of the eight ADMET endpoints are on that
  list, and the docking benchmark is published as **currently failing** its success
  criterion rather than having the criterion relaxed to fit.

These are triage and prioritisation aids: things to help a chemist decide which compound
to make next. That is a genuinely useful job, and it is the job they are built for.

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
| — | [**Validation**](docs/VALIDATION.md) | **Generated** from a benchmark run: how the predictors compare against published reference values, and every capability that has no benchmark at all |

---

## Getting Started

The runnable slice proves the two hardest integrations end-to-end: the **BYO-LLM gateway** and
**deterministic chemistry-as-tools**, wired through an **agentic design loop**. It runs
**fully offline** (a built-in mock LLM) so no API key is needed to try it.

> Requires Python 3.11–3.13 (RDKit has no 3.14 wheels yet). `make venv` hardcodes the
> Apple-Silicon Homebrew interpreter (`/opt/homebrew/bin/python3.13`, Makefile:9) and —
> unlike `PY`/`PIP`/`ALEMBIC` — is not overridable; on Intel macOS, Linux, or Windows create
> the env yourself: `python3 -m venv .venv313 && make install` (the Makefile's `PY`/`PIP`
> default to `.venv313/bin/`, so the directory name matters, the interpreter name does not).
> Day-to-day development and both app images (`infra/docker/api.Dockerfile`,
> `infra/docker/docking.Dockerfile`) run 3.13. All three versions are exercised on every
> pull request by the `ci` matrix, so `requires-python = ">=3.11,<3.14"` is a tested
> claim rather than a declared one.

```bash
make venv && make install     # create .venv313 + install (editable)
make test                     # 223 tests: firewall, chemistry core (MMP/SAR, retrosynthesis, bioisosteres, med-chem rules + MPO), tools, slow-path + streaming, container runtime + THY logistics tools, gateway, agent + Composer chat loop, API, auth/tenancy + RBAC, migrations, ADMET/docking backends, library I/O, run export, BYO-LLM key management
make demo                     # run a sample design loop, print results + provenance
make run                      # start the API at http://localhost:8000  (/docs for Swagger)
```

> The desktop app has its own suite: `cd apps/desktop && pnpm test` (13 vitest tests across
> 5 files). It is not run by `make test` — pytest's `testpaths` is `["tests"]`, and no
> Makefile target invokes it.

**Try the design loop** (offline mock LLM by default). This call — like every endpoint that
touches data or spends compute — needs a nakitte-carbon-auth JWT (see **Auth &
multi-tenancy** below); export one as `$TOKEN` first:

```bash
curl -s localhost:8000/agent/design \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{
  "goal": "Make 12 analogs with MW<300, logP 1-3, no PAINS, drug-like",
  "seed_smiles": "c1ccccc1C(=O)O"
}' | python -m json.tool
```

> `make demo` runs the same loop **in-process** (no HTTP, no token) for a zero-setup taste.

**Use your own LLM:** copy `.env.example` → `.env`, set a key (e.g.
`GLOWSKY_ANTHROPIC_API_KEY`) and route (e.g. `GLOWSKY_ROUTE_REASONING=anthropic/claude-opus-4-8`).
With no keys set, every task class gracefully falls back to the offline mock.

**Slow path & streaming.** Heavy tools (conformers, docking, batch library jobs) are taken
off the request by **submitting them as jobs** — `POST /jobs` / `POST /jobs/batch` — which
stream progress. (`POST /tools/{name}` always runs the handler inline and holds the HTTP
response until it finishes, whatever the spec's compute/latency class; automatic
compute-class routing is not wired yet. With `GLOWSKY_REDIS_URL` unset, Celery is eager, so
jobs also run in-process — see below.)

> `$TOKEN` is the JWT exported above. `POST /tools/{name}`, `POST /jobs` and
> `POST /jobs/batch` require a **writer** principal (`require_write`); `GET /jobs/{id}`
> requires any authenticated principal (`current_principal`). `GET /health` is the only
> endpoint below that needs no token.

Submit a job, then stream its events:

```bash
# Batch-profile a library; per-item results stream as they complete
JOB=$(curl -s localhost:8000/jobs/batch -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{
  "tool": "profile_molecule",
  "items": [{"canonical_smiles":"CCO"},{"canonical_smiles":"c1ccccc1C(=O)O"}]
}' | python -c 'import sys,json;print(json.load(sys.stdin)["job_id"])')
# Stream events over WebSocket:  ws://localhost:8000/jobs/$JOB/stream?token=$TOKEN
curl -s localhost:8000/jobs/$JOB -H "authorization: Bearer $TOKEN" | python -m json.tool   # or poll
```

With **no `GLOWSKY_REDIS_URL`**, Celery runs *eager* (in-process) — the slow path works
with zero infra. To run the **real distributed path**: set `GLOWSKY_REDIS_URL`, start
Redis (`make redis`) and a worker (`make worker`), or `docker compose up`. Same code,
same events; jobs now execute on workers and stream over Redis.

**Container tools (bring-your-own model).** A researcher packages their tool as a Docker
image that speaks the tool ABI (read JSON args on stdin, write `{"ok": true, "result": {…}}`
on stdout) and drops a `glowsky-tool.yaml` under `GLOWSKY_TOOLS_DIR`. Glowsky registers it as a
first-class, agent-callable tool — with the **same cache, firewall, and provenance** as
built-ins — and runs it **fully sandboxed**: `--network none --read-only --cap-drop ALL
--security-opt no-new-privileges`, non-root, memory/cpu/pids caps, and a hard timeout.

```bash
make tool-example        # build examples/tools/molecular_formula -> a container tool
GLOWSKY_TOOLS_DIR=examples/tools GLOWSKY_ENABLE_CONTAINER_TOOLS=true make run   # API now lists `molecular_formula`
curl -s localhost:8000/tools/molecular_formula -d '{"args":{"canonical_smiles":"CCO"}}' \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json'         # runs the sandboxed container, returns formula
```

Container tools are opt-in: registration needs **both** `GLOWSKY_TOOLS_DIR` and
`GLOWSKY_ENABLE_CONTAINER_TOOLS=true` (GS-M3, `services/tools/catalog.py`). With only
`GLOWSKY_TOOLS_DIR` set the registry stays at the 22 built-ins and
`POST /tools/molecular_formula` returns 404.

**Real ADMET backend (`examples/tools/admet_ai/`).** A production-grade example: the open
**ADMET-AI** predictor (pretrained Chemprop-RDKit GNN over ~40 Therapeutics Data Commons
endpoints — solubility, hERG, CYP, Caco-2, BBB, clearance, …) packaged as a container tool.
Model weights are baked into the image at build time, so it predicts **fully offline**
under `--network none`.

```bash
make tool-admet          # build glowsky-tool-admet-ai (large: torch; takes a few min)
GLOWSKY_TOOLS_DIR=examples/tools GLOWSKY_ENABLE_CONTAINER_TOOLS=true make run
curl -s localhost:8000/tools/admet_ai -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"args":{"canonical_smiles":"CC(=O)Oc1ccccc1C(=O)O","endpoints":["Solubility","hERG","BBB"]}}'
# -> real ADMET predictions, sandboxed, with image-pinned provenance
```

This is how the ADMET seam (`predict_admet`, docs/13 §10) is satisfied by a real model
with **zero Glowsky code changes** — just an image + a `glowsky-tool.yaml`.

**The tool seam is domain-agnostic — it isn't only chemistry.** `examples/tools/` also
ships the nakitte-carbon **ULD-line accelerator products** as sandboxed `logistics` tools,
proving any team's model plugs in the same way: `cargo_dimensioning` (IATA volumetric +
chargeable weight — the deterministic billing core; AI measures upstream, ADR-140),
`damage_detect` (the deterministic triage gate over a vision model's detections —
classify → pending_review → human-confirm), and `apron_energy` (apron GSE energy + grid
CO₂ projected from ULD movements, ADR-139). All pure-stdlib, deterministic, `--network none`.
Build with `make tools-thy`; they register exactly like a built-in tool.

### Run the whole stack on Docker

Five compose files, selected with `-f` — a base dev stack, a standalone prod stack, a
released-image stack, and two opt-in overlays. (These are plain files, not Compose
`profiles:`; `docker compose --profile …` does not apply here.) Each has a different
security posture:

| Stack | Command | Database | Docker socket | Container tools |
|---|---|---|---|---|
| **dev (default)** | `docker compose up --build` | SQLite | none (socket-free) | off |
| **prod** | `docker compose -f docker-compose.prod.yml up --build` | **Postgres** (Alembic-migrated) | none (socket-free) | off |
| **release (pinned image)** | `docker compose -f docker-compose.release.yml up -d` | **Postgres** (Alembic-migrated) | none (socket-free) | off |
| **tools (opt-in overlay)** | `docker compose -f docker-compose.yml -f docker-compose.tools.yml up --build` | SQLite | **mounted** (root-equivalent) | **on** |
| **docking (opt-in overlay)** | `make up-docking` (= `docker compose -f docker-compose.yml -f docker-compose.docking.yml up --build`) | SQLite | none (socket-free) | off |

```bash
docker compose up --build   # redis + api + worker (same image), SQLite, API at :8000
```

#### Running a release rather than the working tree

Every stack above with `--build` runs **whatever is checked out**, which is a moving target
and not something a bug report can identify. `docker-compose.release.yml` runs a published
image instead:

```bash
export GLOWSKY_SECRET_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export GLOWSKY_DB_PASSWORD="$(openssl rand -hex 24)"
docker compose -f docker-compose.release.yml up -d     # pulls ghcr.io/celikgo/glowsky
curl localhost:8000/health
```

It has no `build:` section anywhere, so there is no path by which it quietly builds local
source and presents the result as a release — `.github/workflows/docker.yml` fails the
build if one appears, and if the three application services ever pin different tags. The
default tag is the version this checkout declares, kept in step with `pyproject.toml` and
the desktop manifests by `tests/test_version_consistency.py`. Run a different release with
`GLOWSKY_VERSION=0.2.0 docker compose -f docker-compose.release.yml up -d`.

The default and prod stacks are **socket-free** and register only the in-process built-in
RDKit tools. `docker-compose.prod.yml` is a complete standalone stack (not an overlay): it
swaps SQLite for **Postgres** and runs a one-shot `alembic upgrade head` (the `migrate`
service) that api/worker hard-depend on, so the schema is versioned rather than bootstrapped
by `create_all`. The docking overlay changes only the chemistry backend — it rebuilds api +
worker from `infra/docker/docking.Dockerfile` (AutoDock Vina 1.2.5 + OpenBabel, pinned
`linux/amd64`) and sets `GLOWSKY_DOCKING_BACKEND=vina`.

**Container (docker-run) tools are OPT-IN** (`docker-compose.tools.yml`, GS-M3). That overlay
mounts the host Docker socket so the worker can launch sandboxed tool containers
(docker-out-of-docker) — verified end-to-end: API → Redis → worker → `docker run` → streamed
result with image-pinned provenance:

```bash
make tool-example         # build the example container tool image (on the host daemon)
docker compose -f docker-compose.yml -f docker-compose.tools.yml up --build
```

> The socket mount is **root-equivalent** on the host — acceptable only on a **trusted
> single-tenant / local** host, which is why it is not in the default or prod stacks. A
> hosted/multi-tenant deployment must use a rootless/sysbox/gVisor builder or a dedicated
> tool-runner service before re-enabling container tools (deferred, ADR-005).

### Run with real docking (AutoDock Vina + OpenBabel)

Docking is adapter-gated and off by default. An opt-in overlay rebuilds the api + worker
on a Vina/OpenBabel image and flips `GLOWSKY_DOCKING_BACKEND=vina`:

```bash
make up-docking            # docker compose -f docker-compose.yml -f docker-compose.docking.yml up --build
curl localhost:8000/health # -> backends.docking: "autodock-vina (vina)"
```

The image is pinned to `linux/amd64` (Vina ships x86_64 binaries only, so it runs under
emulation on Apple Silicon). `./examples/docking` mounts at `/receptors`. Prepare the
bundled 1HSG receptor once, then dock the co-crystallised ligand back into its pocket
(centre = the crystal ligand's centroid, `13.1, 22.5, 5.6`):

```bash
docker compose -f docker-compose.yml -f docker-compose.docking.yml run --rm api \
  obabel /receptors/1hsg_receptor.pdb -O /receptors/1hsg_receptor.pdbqt -xr -p 7.4
curl -s localhost:8000/tools/dock -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"args":{
  "ligand_smiles":"CC(C)(C)NC(=O)[C@@H]1CN(Cc2cccnc2)CCN1C[C@@H](O)C[C@@H](Cc1ccccc1)C(=O)N[C@H]1c2ccccc2C[C@H]1O",
  "receptor_ref":"/receptors/1hsg_receptor.pdbqt",
  "center":[13.1,22.5,5.6],"size":[22,22,22]}}'   # -> Vina scores + per-pose .pdbqt geometry
```

Three things about that command are worth stating, because each was wrong in an earlier
version of this README:

- **`-p 7.4` is required, not a refinement.** It adds hydrogens at physiological pH.
  `1hsg_receptor.pdb` has none (1514 atoms, all C/N/O/S), and Vina assigns its
  hydrogen-bond atom types from the protonation state. Without it, re-docking this
  ligand puts the top pose 4.22 Å from the crystallographic answer — measured, in
  [`tests/validation/test_redocking_rmsd.py`](tests/validation/test_redocking_rmsd.py).
- **That SMILES is indinavir**, the ligand actually co-crystallised in 1HSG, with the
  stereochemistry read off the deposited coordinates. The 24-heavy-atom string this
  README used to show is a fragment of it, not the ligand.
- **A Vina score is not a binding affinity.** It is a scoring-function value in
  kcal/mol. Recovering a pose is evidence about *geometry*; nothing here measures how
  strongly anything binds. See [`docs/VALIDATION.md`](docs/VALIDATION.md).

### What's implemented today

Untagged rows are the Phase 0 foundation; rows tagged *(Phase 1)* landed since.

| Area | Module | Notes |
|---|---|---|
| **Deterministic firewall** | `services/chemistry/validation.py` | Every structure (incl. LLM-emitted) is validated/canonicalized before it's trusted or stored |
| **Chemistry tools (22)** | `services/chemistry/*` | Validation, descriptors + one-call profiling, druglikeness, PAINS/BRENK alerts, fingerprints, Tanimoto (single+bulk), substructure search, Murcko scaffolds, SA score, template retrosynthesis + synthesizability, MPO scoring + a 7-rule med-chem battery (Lipinski/Veber/Ghose/Egan/Muegge/lead-like/Ro3), matched molecular pairs + SAR transforms, analog enumeration, bioisosteric replacement, ETKDG conformers; ADMET + docking as adapter-gated seams |
| **Tool execution subsystem** | `services/tools/` | The scalable seam (docs/13): versioned `ToolSpec` contract, registry, `ToolExecutionService` (cache + firewall + provenance; compute/latency class declared on every spec and recorded in provenance, with the slow path entered by explicit job submission — automatic compute-class routing is not wired yet) |
| **Slow path + streaming** | `services/tools/queue/`, `store.py` | Celery tasks for heavy/batch tools; append-only `JobStore` (in-memory eager **or** Redis); `POST /jobs`, `/jobs/batch`, `GET /jobs/{id}`, and **`WS /jobs/{id}/stream`** relaying queued→running→item→completed live |
| **Container-tool runtime** | `services/tools/runtimes/container.py`, `manifest.py`, `examples/tools/` | Bring-your-own model as a sandboxed Docker tool: JSON-stdin/stdout ABI, `glowsky-tool.yaml` manifests, strict isolation. Registered like any built-in (cache/firewall/provenance) |
| **Docker deployment** | `docker-compose.yml` (dev), `docker-compose.prod.yml` (Postgres, migrated, socket-free), `docker-compose.tools.yml` (opt-in container tools), `docker-compose.docking.yml`, `infra/docker/` | Redis + API + worker on one image. Default + prod stacks are socket-free with container tools off; the opt-in tools overlay mounts the Docker socket (root-equivalent, trusted hosts only) to launch sandboxed tool containers. An opt-in `docking.Dockerfile` overlay adds a real AutoDock Vina + OpenBabel toolchain (`make up-docking`) |
| **BYO-LLM gateway** | `services/llm_gateway/` | LiteLLM-backed multi-provider access + offline mock; task-class routing; keys resolved only at call time, never logged |
| **Agent orchestrator** | `services/agent/orchestrator.py` | Plan (LLM) → generate → profile → filter → rank → synthesize (LLM); every chemistry call routes through the execution service, with a full provenance trace |
| **API + persistence** | `apps/api/` + `services/core/` | FastAPI endpoints incl. generic `POST /tools/{name}` and **`POST /agent/chat`** + **`WS /agent/chat/stream`** (one Composer turn, non-streaming/streaming; `services/agent/chat.py`, write-scoped like `/agent/design`); runs + molecules stored with provenance (`origin_run_id`) in SQLite (dev/test default) or **Postgres** (prod, Alembic-migrated — see `docker-compose.prod.yml`) |
| **Auth & tenancy** *(Phase 1)* | `services/core/nakitte_auth.py`, `apps/api/deps.py` | **nakitte-carbon-auth JWT** is the sole credential (RS256, JWKS-verified) — no local key store, no bypass; org/user/membership tenant is JIT-provisioned from the token; tenant-scoped projects/runs/molecules + audit trail; every design, job and tool-execution endpoint gated (`require_write` for writes, `current_principal` for reads, a `token` query/init frame for the three WebSockets). Ungated by design: `GET /health`, the pre-tenant `/auth/*` proxies, `GET /settings/providers`, and `GET /tools` (static catalog, no execution). Known gap: `POST /molecules/diff` is stateless compute but is currently ungated, unlike its `/molecules/*` siblings |
| **Real ADMET/docking backends** *(Phase 1)* | `services/chemistry/adapters/admet_rdkit.py`, `adapters/vina.py` | Offline **RDKit-QSPR** ADMET (ESOL solubility + BBB rule + lipophilicity heuristics, every value carries method/confidence/applicability-domain) and an **AutoDock Vina** docking wrapper that surfaces real per-pose 3D geometry (parsed from Vina's output `.pdbqt`, not just scores) — both adapter-gated (`GLOWSKY_ADMET_BACKEND`, `GLOWSKY_DOCKING_BACKEND`); the default stays "not configured" so nothing is ever fabricated |
| **Library + SMILES/CSV/SDF I/O** *(Phase 1)* | `services/chemistry/io.py`, `apps/api/main.py` | Tenant-scoped libraries; import/export in SMILES/CSV/SDF (every structure firewalled, InChIKey-deduped, with a re-import filling empty property fields but never overwriting one, and bad rows reported rather than fatal); molecule diff with per-descriptor deltas |
| **Migrations** *(Phase 1)* | `migrations/`, `tests/test_migrations.py` | Alembic as schema source of truth; a drift-guard test fails if models and migrations diverge |
| **Run export** *(Phase 1)* | `services/reporting/`, `GET /runs/{id}/export` | Export a design run as a **reproducible Jupyter notebook** (self-contained RDKit code that recomputes descriptors + re-applies the filters — verified to execute) or a **Markdown report**; both built from stored provenance, tenant-scoped |
| **BYO-LLM key management** *(Phase 1)* | `services/core/crypto.py`, `services/llm_gateway/credentials.py`, `apps/api/main.py` | Per-org provider credentials **encrypted at rest** (Fernet; only a masked hint is ever returned) and per-org model-route overrides; the gateway resolves an org's stored keys/routes ahead of env defaults (then the offline mock). Endpoints under `/settings/*`, tenant-scoped |
| **Desktop app** *(Phase 1)* | `apps/desktop/` | **Tauri 2 + React + Vite + TS** desktop client themed in the Twitter **Dim** palette. **Composer** (the default screen: multi-turn chat over `WS /agent/chat/stream`, a working seed that carries across turns, `@`-attached context molecules, **Ketcher** 2D structure drawing (`ketcher-react` 3.15.0, lazy-loaded), multi-select candidates → save-to-library, and per-run notebook/report export), Design (agentic loop with **RDKit-JS 2D rendering** + an interactive **3Dmol.js conformer viewer** behind a per-card 2D/3D toggle, notebook/report export), Library (projects + SMILES/CSV/SDF I/O), Docking (adapter-gated dock form + a **3Dmol.js receptor/ligand pose viewer**, demoable on a real RCSB 1HSG sample complex), **Retrosynthesis**, **Matched Pairs & SAR**, Tools (schema-driven registry playground), and Settings (BYO-LLM keys + model routing) — plus a **⌘K command palette** and a molecule inspector openable from any card. See `apps/desktop/README.md` |

Layout follows `docs/11-folder-structure.md` + `docs/13-chemistry-tools-architecture.md`.
Phase 1 is largely delivered — see the rows tagged *(Phase 1)* above: the auth/tenancy spine,
the slow-path Celery/Redis queue with WebSocket streaming (`WS /jobs/{id}/stream`,
`/agent/design/stream`, `/agent/chat/stream`), real ADMET/docking backends, 2D/3D viewers
(RDKit-JS 2D + an interactive 3Dmol.js conformer viewer), and notebook/report export are all
in. Still open in the tools layer: input-schema validation and quota/fairness enforcement in
the execution service (docs/13 §4 steps 1 and 3, §7 — step 1 has no code at all, so
`ToolSpec.input_schema` is advertised to the model and the Tools screen but never gates a
call, and step 3 is a lone placeholder comment at `services/tools/executor.py:74`), a
shared Redis/object-storage result cache (`services/tools/cache.py` is in-memory only), and a
CI workflow (there is no `.github/workflows`).

**Auth & multi-tenancy.** Identity is owned by **nakitte-carbon-auth** — Glowsky has no
local credential store and no auth bypass. **Every** request that touches tenant data or
spends compute, in every environment, presents a platform **JWT**
(`Authorization: Bearer <jwt>`; RS256, verified against the carbon-auth JWKS) — the handful
of deliberately ungated endpoints is listed in the **Auth & tenancy** row above. The token's
`sub`/`tenant_id`/`roles` become the principal, the tenant is **JIT-provisioned** into
Glowsky's tables on first sight, and all data is isolated per tenant.
Point `GLOWSKY_NAKITTE_JWKS_URL` at a running carbon-auth — for local dev too (see
`.env.example`). Roles map to write/read: `owner` → owner, read-only platform roles
(`viewer`/`auditor`) → viewer, any other role → editor.

```bash
# Get an access token from nakitte-carbon-auth (see that service's README), then:
TOKEN=...   # a carbon-auth access JWT for your tenant

# Create a project and run a design scoped to it (only this tenant can see it):
PID=$(curl -s localhost:8000/projects -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"name":"Kinase series"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s localhost:8000/agent/design -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d "{\"goal\":\"make 8 analogs, MW<300, no PAINS\",\"seed_smiles\":\"c1ccccc1C(=O)O\",\"project_id\":\"$PID\"}"
curl -s localhost:8000/projects/$PID/runs -H "authorization: Bearer $TOKEN"   # provenance, scoped
```

> A WS handshake can't carry an `Authorization` header, so each WebSocket endpoint takes the
> token another way: `WS /jobs/{id}/stream` reads it from a query param (`?token=…`), while
> `WS /agent/design/stream` and `WS /agent/chat/stream` read it from a `token` field in the
> client's first (init) frame.

**Database migrations (Alembic).** SQLite dev/test bootstraps tables via `create_all`,
but **Alembic is the source of truth** for schema evolution — required for Postgres /
production. `docker-compose.prod.yml` runs `alembic upgrade head` as a one-shot `migrate`
service (against Postgres, driver bundled via `psycopg[binary]`) that api/worker hard-depend
on, so a prod boot is always schema-versioned. The baseline migration is kept honest by a
test that applies all migrations to a throwaway DB and diffs the result against the models,
plus a driver-free test that renders every migration as Postgres DDL.

```bash
make migrate                      # alembic upgrade head (apply pending migrations)
make migration m="add libraries"  # autogenerate a migration from model changes
make migrate-history              # history + current revision
```

> After changing any model in `services/core/models.py`, run `make migration m="..."`,
> review the generated file under `migrations/versions/`, and commit it. The
> `tests/test_migrations.py` drift guard fails if models and migrations diverge — run
> `make test` before committing a model change. CI goes further than that guard can: the
> `migrations` workflow runs `alembic upgrade head`, then `downgrade -1`, then back up,
> and finally all the way down to `base` and up again — against **Postgres 16**, the
> engine production runs. The local guard uses SQLite in batch mode, where an `ALTER` is
> a table rewrite rather than a real `ALTER`, so a migration can pass locally and fail
> in production. CI is also the only place `downgrade()` is ever executed.

---

## TL;DR of the plan

- **Who:** PhD/academic researchers (lead persona), professional med chemists, CADD scientists (champions), → teams & enterprise.
- **Wedge:** the agentic design loop + IDE ergonomics + BYO-LLM economics — no incumbent has all three.
- **MVP litmus test:** with your own LLM key, take a molecule from a natural-language prompt to a validated, visualized, property-annotated, docked, exportable result — **without writing code.**
- **Stack — shipped today:** Tauri 2 + React 18 + Vite desktop client (RDKit-JS, 3Dmol.js, Ketcher); Python/FastAPI backend; a hand-written agent orchestrator (no agent framework); LiteLLM-based BYO-LLM gateway; RDKit + AutoDock Vina chemistry; SQLite (dev) / Postgres + Redis (prod) on Docker Compose. **Planned:** pgvector + object storage for literature RAG, generative/retrosynthesis models (REINVENT/AiZynth-class), and K8s + Helm packaging for managed SaaS.
- **Two existential risks addressed by architecture, from Phase 0 on:** chemistry hallucination (deterministic firewall + validation) and credential/IP security (the gateway resolves provider keys only at call time and never logs or returns them, under strict tenant isolation; stored per-org BYO-LLM keys are Fernet-encrypted at rest under `GLOWSKY_SECRET_KEY` — Phase 1, `services/core/crypto.py`. A managed KMS/secrets-manager path with envelope encryption, per-tenant data keys, and key rotation is still planned — see `docs/07-security-privacy.md` §2).
- **Roadmap:** Phase 0 foundation → Phase 1 MVP (core loop) → Phase 2 advanced chemistry + teams → Phase 3 extensibility + enterprise.
