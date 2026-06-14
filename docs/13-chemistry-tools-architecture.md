# Glowsky — Chemistry Tools Subsystem Architecture

> **Scope.** How Glowsky models, registers, executes, scales, and extends its chemistry
> tools — from a sub-millisecond `canonicalize` to a 10-minute GPU docking job to a
> researcher's own model dropped in as a plugin. This is the **high-level architecture**;
> it precedes adding the tools themselves so we add them *into a frame*, not ad hoc.
>
> **Design center:** a **highly scalable, academic- & R&D-centric** product. That shapes
> every decision below (see §1).

---

## 1. What "academic & R&D-centric, highly scalable" forces

These four properties are the constraints the architecture must satisfy:

| Driver | Consequence for the tools layer |
|---|---|
| **Reproducibility is non-negotiable** (theses, papers, DRC defensibility) | Tools are **versioned, pinned, content-addressed**; every result carries full provenance; identical inputs → identical outputs → exportable to a notebook that reruns. |
| **Heterogeneous compute** (RDKit µs-calls, GPU ML inference, long docking, external APIs) | One uniform **tool contract**, but **multiple execution backends** routed by a declared *compute class*. Never run a 10-min docking job on the request path. |
| **Bursty, shared, cost-sensitive load** (many students/labs, big virtual libraries, BYO-compute) | **Horizontal autoscaling per compute class**, aggressive **content-addressed caching**, **batch fan-out** with streaming partial results, **per-tenant quotas & fair scheduling**. |
| **R&D extensibility** (researchers bring their own models/tools) | A first-class **Tool SDK + plugin model** with **sandboxing**, manifests, and versioned sharing — the moat. The same contract serves built-in and custom tools. |

**Architectural thesis:** decouple *what a tool is* (a versioned, typed contract) from *how it runs* (an executor chosen by compute class). The agent and orchestrator only ever see the contract. Everything scalable, reproducible, and extensible follows from that seam.

---

## 2. The Tool Contract (the heart)

Every tool — built-in or custom — declares a typed, versioned contract. This is the single abstraction the registry, executor, cache, provenance, and SDK all key off.

```
ToolSpec
  name:            str                  # "generate_analogs"
  version:         semver               # "0.2.0" — bump on behaviour change
  category:        ToolCategory         # cheminformatics | filtering | property |
                                        #   generative | structure_based | retrosynthesis | search | io
  summary:         str
  input_schema:    JSON Schema          # validated before execution
  output_schema:   JSON Schema          # validated after execution
  # --- execution metadata: how to run & scale it ---
  compute_class:   CPU_LIGHT | CPU_HEAVY | GPU | IO_BOUND | EXTERNAL_API
  latency_class:   INSTANT(<100ms) | SHORT(<10s) | LONG(s–min) | BATCH
  determinism:     DETERMINISTIC | SEEDED | NONDETERMINISTIC
  batchable:       bool                 # accepts N inputs in one call (vectorized)
  cacheable:       bool                 # + cache-key strategy (default: content hash)
  # --- resources & environment (for scheduling + reproducibility) ---
  resources:       {cpu, mem, gpu?, timeout_s}
  runtime:         BuiltinPython | ContainerImage(digest) | RemoteHTTP
  env_digest:      str                  # container/image digest pinned for repro
  # --- safety ---
  egress:          NONE | ALLOWLIST     # network policy (custom/remote tools)
  emits_structures: bool                # if true, outputs pass the validation firewall
```

Why each field earns its place:
- **`compute_class` + `latency_class`** → the executor routes (inline vs queue vs GPU pool vs batch). This is what keeps a docking job off the request thread.
- **`determinism` + `version` + `env_digest`** → reproducibility & cache correctness. A `SEEDED` tool caches on `(input, seed, version)`; `NONDETERMINISTIC` is never cached.
- **`batchable`** → the batch executor can vectorize (RDKit descriptors over 1M molecules) instead of N calls.
- **`emits_structures`** → reasserts the **deterministic firewall**: any tool (including a custom ML generator) that outputs molecules has them validated/canonicalized before they're trusted.
- **`runtime` + `egress`** → built-in vs containerized vs remote, and the sandbox policy for each.

> **Evolution from Phase 0:** today's `services/agent/registry.Tool` is this contract in embryo (name, description, params, version, fn). We extend it with the execution/repro/safety metadata above. Backward-compatible — existing tools gain sensible defaults (`CPU_LIGHT`, `INSTANT`, `DETERMINISTIC`).

---

## 3. Registry & Discovery

```
┌─────────────────────────────────────────────────────────────┐
│ Tool Registry                                                 │
│  • Built-in tools     → registered at boot (in-process)       │
│  • Custom/org tools   → loaded from DB + manifests (Phase 3)  │
│  • Capability-gated   → a route's model must support tool-use │
│  • Versioned          → multiple versions can coexist; pin    │
│    per project for reproducibility                            │
│                                                               │
│  exposes: specs() for agent/LLM tool-calling discovery        │
│           resolve(name, version?) → ToolSpec + handle         │
└─────────────────────────────────────────────────────────────┘
```

- **Namespacing:** `glowsky.*` (built-in), `org:<id>.*` (private), `community.*` (published, future).
- **Version pinning:** a Project records the tool versions it used → reruns are exact. Default = latest; pin on demand.
- **Discovery:** `specs()` already feeds the agent; it also drives native LLM tool-calling in Phase 1 and the UI tool catalog.

---

## 4. Execution Architecture — the scalable core

A single **Tool Execution Service (dispatcher)** sits between the orchestrator and the compute backends. The orchestrator calls `execute(tool, args, ctx)` and never knows *where* it ran.

```
                         orchestrator / agent
                                  │  execute(tool, args, ctx)
                                  ▼
                    ┌──────────────────────────────┐
                    │   Tool Execution Service      │
                    │   (dispatcher + policy)       │
                    │  1. validate input schema     │
                    │  2. cache lookup (if cacheable)│
                    │  3. quota / fairness check     │
                    │  4. route by compute_class     │
                    │  5. validate output (firewall) │
                    │  6. record provenance + cache  │
                    └───┬─────────┬─────────┬────────┘
          FAST PATH     │         │ SLOW PATH (queued, async, streamed)
        (inline, <100ms)│         │
                        ▼         ▼                 ▼                  ▼
                ┌────────────┐ ┌──────────┐  ┌────────────┐  ┌──────────────┐
                │ in-proc /  │ │ CPU-heavy│  │ GPU worker │  │ External-API │
                │ fast pool  │ │ workers  │  │ pool       │  │ connector    │
                │ canonical, │ │ docking  │  │ ML ADMET,  │  │ retrosynth   │
                │ descriptors│ │ prep,    │  │ gnina,     │  │ APIs, name→  │
                │ fingerprints│ │ enumerate│  │ generative │  │ structure    │
                └────────────┘ └──────────┘  └────────────┘  └──────────────┘
                        │            │  (Task Queue: Redis/Celery → Temporal in P2)
                        └──── results stream back via Redis pub/sub → WS → client
```

### 4.1 Two paths, one contract
- **Fast path** (`INSTANT` + `CPU_LIGHT`): executed inline in a fast worker — canonicalize, descriptors, similarity, substructure. Sub-second, synchronous, feels instant in the UI.
- **Slow path** (`SHORT`/`LONG`/`BATCH` or `GPU`/`CPU_HEAVY`/`EXTERNAL_API`): enqueued; the call returns a job handle; progress + results **stream** back over WebSocket. Docking, ML inference, generation, retrosynthesis, big enumerations.

The dispatcher picks the path purely from `ToolSpec` metadata — adding a new tool is declarative.

### 4.2 Scaling primitives
- **Heterogeneous worker pools**, independently autoscaled on queue depth (KEDA on K8s): `worker-cpu` (RDKit-heavy), `worker-gpu` (ML/docking), `worker-io` (external APIs). Cheap to scale the CPU pool wide for academic burst; reserve scarce GPUs for the GPU queue.
- **Batch fan-out (map/reduce):** a `BATCH` tool over a library is split into chunks by a coordinator, fanned across workers, with **streaming partial results**, early-exit, and cancellation. Wall-clock ≈ slowest chunk, not the sum. Essential for virtual screening / library profiling.
- **Content-addressed cache:** key = `hash(tool_name, version, env_digest, canonical_input)`. Hot in Redis, cold in object storage. Deterministic chemistry is recomputed once, ever. **Tenant-scoped by default** (an input SMILES *is* IP — a global cache would leak that a structure exists; see §7).
- **Idempotency keys** so retries don't double-run; **backpressure** so a flood of jobs degrades latency, not correctness.

### 4.3 Execution backbone choice
- **Phase 0 (done):** fast-path inline via `execute()`; **slow path implemented** with Celery — `submit()`/`submit_batch()` enqueue `glowsky.run_tool_job`/`run_batch_job`, which emit an event stream to a shared `JobStore` (in-memory in *eager* mode, Redis across processes). `WS /jobs/{id}/stream` relays events live. With no `GLOWSKY_REDIS_URL`, Celery runs eager so the slow path works with zero infra; setting it flips on real workers + Redis with no code change.
- **Phase 2 (scale):** evaluate **Temporal** (durable, observable, retry-native workflows) for multi-step/long jobs, and/or **Ray** for distributed batch chemistry/ML fan-out. The batch task processes items sequentially today (per-item streaming already matches what a parallel group/chord emits) → swapping in a Celery `group`/`chord` or Ray is a task-internal change. Both slot behind the same dispatcher — no orchestrator changes.

---

## 5. Reproducibility & Provenance (academic non-negotiable)

Every execution writes a provenance record (extends Phase 0's `ToolCallRecord` / `AgentRun.trace`):

```
{ run_id, step, tool, version, env_digest, compute_class,
  input_hash, params, seed?, cache_hit, duration_ms, worker, timestamp }
```

- **Tool Environment Registry:** `tool_version → container image digest + dependency lockfile`. Reproducing a 2-year-old thesis result pulls the exact image.
- **Notebook export** reads the trace and emits code pinned to those versions — the result regenerates bit-for-bit (deterministic tools) or seed-for-seed (`SEEDED`).
- **Determinism honored in cache:** `NONDETERMINISTIC` tools are never cached; `SEEDED` cache on the seed.

---

## 6. Extensibility — the Tool SDK & plugin model (R&D moat)

Three runtime types, one contract, escalating isolation:

| Runtime | Who/when | Isolation | Use case | Status |
|---|---|---|---|---|
| **Builtin Python** | Glowsky core; trusted self-host plugins | in-process | RDKit ops, our predictors | ✅ Phase 0 |
| **Container tool** | Researcher brings an image + `glowsky-tool.yaml` manifest | one-shot container: `--network none --read-only --cap-drop ALL --security-opt no-new-privileges`, non-root, mem/cpu/pids caps, timeout | a lab's custom ADMET model, internal docking | ✅ **Phase 0** (`services/tools/runtimes/container.py`, `manifest.py`; example in `examples/tools/`) |
| **Remote HTTP tool** | Org registers an endpoint + schema + auth | egress allowlist, consented data, scoped creds | enterprise internal services | ⏳ Phase 3 |

**Implemented container ABI:** the image reads a JSON args object on **stdin** and writes
`{"ok": true, "result": {...}}` (or `{"ok": false, "error": ...}`) on **stdout**. The
`ContainerRuntime` builds the sandboxed `docker run` argv, pipes args in, parses the
result, and (because the tool is a normal `ToolSpec`) the executor applies the same
cache, validation firewall, and provenance as for built-ins. Verified end-to-end through
the Dockerized stack (API → Redis → worker → `docker run` → streamed result).

```
glowsky-tool.yaml (manifest)
  name: org:acme.predict_herg
  version: 1.2.0
  category: property
  compute_class: GPU
  image: registry/acme/herg@sha256:...      # pinned for repro
  input_schema: {...}   output_schema: {...}
  resources: {gpu: 1, mem: 8Gi, timeout_s: 120}
  egress: NONE
  emits_structures: false
```

- **SDK ergonomics:** define a tool by decorator + Pydantic I/O models; the SDK generates the schema, registers it, and (for container tools) builds/pins the image.
- **Sharing & governance:** tools are versioned artifacts — private to a user, shared org-wide, or (future) published to a community registry. Admins approve/allowlist custom tools.
- **Firewall still applies:** any custom tool with `emits_structures: true` has outputs validated/canonicalized — a researcher's generative model can't inject garbage structures.

This is how Dr. Chen (persona §3) turns "I have an internal model" into "it's an agent-callable tool the whole team uses" — **without us writing code**.

---

## 7. Security & multi-tenancy (in the tools layer)

- **Deterministic firewall, everywhere:** §2 `emits_structures` → validation gate. Non-negotiable across built-in and custom tools.
- **Sandboxing by runtime type** (§6): container tools get no ambient egress, CPU/mem/time caps, dropped capabilities — the same posture as docs/07 §6.
- **Tenant-scoped cache:** caching is per-org by default because the input structure is the IP. A *shared* cache is opt-in and limited to non-sensitive, purely-public deterministic computations.
- **Quotas & fair scheduling:** per-org/user concurrency + compute budgets; **priority classes** (interactive fast-path > batch) so one lab's million-molecule screen doesn't starve another's interactive session. Backpressure over failure.
- **Egress control** for remote/external-API tools; consent + audit on data sent out.

---

## 8. Failure handling
- **Timeouts per `latency_class`**; **retries with backoff** for transient/`IO_BOUND`; **circuit breakers** for flaky external APIs.
- **Batch partial results:** a failed chunk drops to `null` and is reported; the run continues and surfaces what was dropped (no silent truncation).
- **Dead-letter queue** for poison jobs; every failure is traced with the tool/version/input-hash for debugging.

---

## 9. Observability
Per-tool metrics: p50/p95 latency, error rate, **cache-hit rate**, queue depth, GPU utilization, cost. Distributed tracing across dispatcher → worker → tool. Every agent run's trace ID is surfaced in the UI (docs/05 cross-cutting).

---

## 10. The Tool Catalog to add (organized, prioritized)

Tools to build *into this frame*, by category. Priority: 🟢 MVP-ish (now/next) · 🟡 V1 · 🔵 Future. Compute class in brackets.

### Cheminformatics (RDKit) — mostly `CPU_LIGHT`/`CPU_HEAVY`
- 🟢 `standardize` / `canonicalize` *(have)*, `tautomer_canonicalize`
- 🟢 `compute_descriptors` *(have)*, extended descriptor set
- 🟢 `fingerprint` (Morgan/ECFP, MACCS, RDKit) `[CPU_LIGHT, batchable]`
- 🟢 `similarity` (Tanimoto, single + bulk) `[CPU_LIGHT, batchable]`
- 🟢 `substructure_search` / `smarts_match` `[CPU_LIGHT, batchable]`
- 🟢 `murcko_scaffold` / scaffold extraction
- 🟡 `cluster` (Butina / sphere-exclusion) `[CPU_HEAVY]`
- 🟡 `diversity_select` (MaxMin) `[CPU_HEAVY]`
- 🟡 `mcs` (maximum common substructure)
- 🟡 `enumerate_library` (scaffold × R-groups), `enumerate_stereoisomers`, `enumerate_tautomers`
- 🟡 `generate_conformers` (ETKDG) `[CPU_HEAVY]`
- 🟢 `convert_format` (SMILES/InChI/MOL/SDF parse+write) `[CPU_LIGHT]`

### Filtering & alerts — `CPU_LIGHT`
- 🟢 `structural_alerts` (PAINS *(have)*, + BRENK, NIH, custom SMARTS sets)
- 🟢 `druglikeness` *(have)* — expose as a tool (Ro5/Veber/Egan/Ghose)
- 🟢 `property_filter` — pull the orchestrator's inline filter into a first-class tool

### Property / ADMET — `CPU_HEAVY` or `GPU`
- 🟢 `sa_score` (synthetic accessibility) `[CPU_LIGHT]`, 🟡 `scscore`
- 🟡 `predict_admet` (ADMET-AI / open models: solubility, logD, hERG, CYPs, metab stability) `[GPU/CPU_HEAVY]` — with applicability domain & confidence. ✅ **Implemented as a real container tool** (`examples/tools/admet_ai/`): ADMET-AI pretrained Chemprop-RDKit GNN over ~40 TDC endpoints, weights baked in, runs sandboxed under `--network none`. Demonstrates satisfying the ADMET seam with zero Glowsky code change.
- 🟡 `predict_pka` / `logd`

### Generative — `GPU`/`CPU_HEAVY`, all `emits_structures: true`
- 🟢 `generate_analogs` *(have)* — R-group enumeration
- 🟡 `scaffold_hop`, `bioisostere_replace` (BRICS/fragmentation-based)
- 🔵 `de_novo_generate` (REINVENT-class) `[GPU, SEEDED]`
- 🔵 `fragment_grow` / `link` (BRICS, fragment merging)

### Structure-based — `GPU`/`LONG`
- 🟡 `dock` (Vina/smina; 🔵 gnina CNN scoring) `[GPU/CPU_HEAVY, LONG]`
- 🟡 `detect_pocket`, `prepare_protein`, `prepare_ligand`
- 🔵 `interaction_fingerprint`, `minimize_pose`

### Retrosynthesis — `LONG`/`EXTERNAL_API`
- 🟡 `synthesizability` (SA/SC) ; 🟡 `retrosynthesis` (AiZynthFinder-class) `[LONG]`
- 🔵 `building_block_availability` (catalog lookup) `[EXTERNAL_API]`

### Search — `EXTERNAL_API`/`CPU_HEAVY`
- 🟡 `similarity_search_corpus` (ChEMBL/known compounds) ; 🔵 patent/IP-aware search

> Each entry is small *because the frame does the heavy lifting* — a new tool is a `ToolSpec` + a function/image, and it inherits routing, scaling, caching, provenance, and sandboxing for free.

---

## 11. How this maps onto the current code (delta)

| Today (Phase 0) | Becomes |
|---|---|
| `services/agent/registry.Tool` (name, desc, params, fn, version) | `ToolSpec` with compute/latency/determinism/runtime/egress metadata (backward-compatible defaults) |
| Orchestrator calls `tool.fn(...)` directly | Orchestrator calls `ToolExecutionService.execute(tool, args, ctx)`; inline now, queue/GPU/batch later — **no orchestrator change** |
| `ToolCallRecord` in the run trace | + `env_digest`, `cache_hit`, `compute_class`, `seed` |
| Single `services/chemistry/*` module set | + `services/chemistry/{fingerprints,similarity,search,clustering,enumeration}.py` and predictor/docking adapters, each registered as a `ToolSpec` |
| n/a | `services/tools/executor.py` (dispatcher), `cache.py`, `runtimes/` (builtin/container/remote), `manifest.py` (SDK) |

**The one seam to introduce first:** the `ToolExecutionService.execute()` indirection. Adding it now (even as a pass-through) means every subsequent tool — and the move to queues, GPU pools, and batch — lands without touching the agent. That is the lever that makes "add more chemistry tools" cheap and scaling non-disruptive.

---

## 12. Open decisions (yours to confirm)
1. **Execution backbone for the slow path** — start Celery/Redis (simple) vs jump to Temporal/Ray earlier (durability/distributed batch sooner). *Recommendation: Celery/Redis now, Temporal in Phase 2.*
2. **Custom-tool runtime priority** — which of {builtin-plugin, container, remote-HTTP} matters first for your users. *Recommendation: builtin-plugin + container (covers academic self-host + R&D internal models).*
3. **Tool-catalog focus for the next build** — which category to deepen first (cheminformatics breadth vs ADMET vs docking). *Recommendation: cheminformatics breadth + SA score (fast, high-leverage, all CPU-light) before GPU tools.*
4. **GPU strategy** — do we target a GPU worker pool in early self-host, or keep V1 CPU-only (Vina, CPU ADMET) and add GPU in Phase 2? *Recommendation: CPU-only V1; GPU pool Phase 2.*
