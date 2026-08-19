# Glowsky — Chemistry Tools Subsystem Architecture

> **Scope.** How Glowsky models, registers, executes, scales, and extends its chemistry
> tools — from a sub-millisecond `canonicalize` to a 10-minute GPU docking job to a
> researcher's own model dropped in as a plugin. This is the **high-level architecture**;
> it precedes adding the tools themselves so we add them *into a frame*, not ad hoc.
>
> **Design center:** a **highly scalable, academic- & R&D-centric** product. That shapes
> every decision below (see §1).
>
> **Status legend.** ✅ shipped · 🟡 partial · ⏳ planned. (§10's catalog uses a separate
> *priority* key — 🟢 now/next · 🟡 V1 · 🔵 future — stated inline there.)

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
  category:        ToolCategory         # cheminformatics | filtering | property | generative |
                                        #   structure_based | retrosynthesis | search | io | logistics
  summary:         str
  input_schema:    JSON Schema          # surfaced to the LLM/UI as `parameters`; not enforced yet
  output_schema:   JSON Schema          # declared for docs/SDK; not read or enforced yet
  # --- execution metadata: how to run & scale it ---
  compute_class:   CPU_LIGHT | CPU_HEAVY | GPU | IO_BOUND | EXTERNAL_API
  latency_class:   INSTANT(<100ms) | SHORT(<10s) | LONG(s–min) | BATCH
  determinism:     DETERMINISTIC | SEEDED | NONDETERMINISTIC
  batchable:       bool                 # accepts N inputs in one call (vectorized)
  cacheable:       bool                 # + cache-key strategy (default: content hash)
  # --- resources & environment (for scheduling + reproducibility) ---
  resources:       {cpu, mem_mb, gpu, timeout_s}
  runtime:         BuiltinPython | ContainerImage(digest) | RemoteHTTP
  env_digest:      str                  # container/image digest pinned for repro
  # --- safety ---
  egress:          NONE | ALLOWLIST     # network policy (custom/remote tools)
  emits_structures: bool                # if true, outputs pass the validation firewall
```

Why each field earns its place:
- **`category`** → groups the UI tool catalog (`GET /tools` → `ToolSpec.discovery_dict()` → `ToolsScreen` renders one group header per category), and nothing else: it does *not* reach the agent, because `registry_to_tool_schemas()` forwards only name/description/parameters. `logistics` is deliberately non-chemistry: the tool contract is domain-agnostic, and the partner ULD-line tools in `examples/tools/` (`cargo_dimensioning`, `apron_energy`, `damage_detect`) register through exactly the same container seam (§6) as a lab's ADMET model. Note `retrosynthesis` is declared but used by zero tools — `retrosynthesize` is registered under `cheminformatics` and `synthesizability` under `property`.
- **`compute_class` + `latency_class`** → the routing key the executor reads (inline vs queue vs GPU pool vs batch). This is the field that will keep a docking job off the request thread — today the mode defaults to inline, see §4.1.
- **`determinism` + `version` + `env_digest`** → reproducibility & cache correctness. A `SEEDED` tool caches on `(input, seed, version)`; `NONDETERMINISTIC` is never cached.
- **`batchable`** → the batch executor can vectorize (RDKit descriptors over 1M molecules) instead of N calls.
- **`emits_structures`** → reasserts the **deterministic firewall**: a tool that *declares* it outputs molecules has every `smiles` it emits validated/canonicalized before it's trusted. The gate is opt-in and key-literal — 2 of the 22 built-ins declare it, and the walk matches the dict key `smiles` exactly (§7).
- **`runtime` + `egress`** → built-in vs containerized vs remote, and the sandbox policy for each.

> **Status:** this contract is implemented as the frozen dataclass `ToolSpec` in `services/tools/spec.py` (plus a `handler` field the sketch above omits). Field defaults are `CPU_LIGHT` / `INSTANT` / `DETERMINISTIC` / `batchable=False` / `cacheable=True` / `runtime=BUILTIN` / `egress=NONE`; 17 of the 22 built-ins run on the default compute/latency pair, while five override — `predict_admet` is `GPU`/`LONG`, `dock` is `CPU_HEAVY`/`LONG`, `generate_analogs` / `bioisosteric_replacement` / `generate_conformers` are `CPU_HEAVY`/`SHORT`, `generate_conformers` is `SEEDED`, and manifest-loaded container tools set `runtime=CONTAINER` with `env_digest` = the image string.

---

## 3. Registry & Discovery

```
┌───────────────────────────────────────────────────────────────┐
│ Tool Registry                                                 │
│  • Built-in tools     → registered at boot (in-process)    ✅ │
│  • Custom/org tools   → glowsky-tool.yaml manifests        ✅ │
│                         loaded from the DB                 ⏳ │
│  • Capability-gated   → a route's model must support       ⏳ │
│                         tool-use                              │
│  • Versioned          → multiple versions can coexist      ✅ │
│                         pinned per project                 ⏳ │
│                                                               │
│  exposes: specs() for agent/LLM tool-calling discovery        │
│           resolve(name, version?) → ToolSpec + handle         │
└───────────────────────────────────────────────────────────────┘
```

- **Namespacing (⏳):** `glowsky.*` (built-in), `org:<id>.*` (private), `community.*` (published, future). Not implemented — `ToolRegistry` keys on the bare `name`, so both the built-in catalog and every manifest register unprefixed.
- **Version pinning (🟡):** the registry genuinely holds `{name: {version: spec}}` and `resolve(name, version)` honours `ctx.version_pins`, so coexisting versions work today. What is missing is the *recording* half — `Project` has no pins column and no caller ever populates `version_pins`, so every resolve falls through to latest. Reruns are exact only while a tool's version is unbumped.
- **Discovery (✅):** `specs()` feeds all three consumers — `GET /tools` for the desktop catalog, `registry_to_tool_schemas()` for native LLM function-calling in the `ToolCallingAgent` loop (`max_steps=6`), and the design orchestrator's own calls.

---

## 4. Execution Architecture — the scalable core

A single **Tool Execution Service (dispatcher)** sits between the orchestrator and the compute backends. The orchestrator calls `execute(tool, args, ctx)` and never knows *where* it ran.

```
                         orchestrator / agent
                                  │  execute(tool, args, ctx)
                                  ▼
                    ┌────────────────────────────────┐
                    │   Tool Execution Service       │
                    │   (dispatcher + policy)        │
                    │  1. validate input schema   ⏳ │
                    │  2. cache lookup (if cacheable)│
                    │  3. quota / fairness check  ⏳ │
                    │  4. route by compute_class  🟡 │
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
                │fingerprints│ │ enumerate│  │ generative │  │ structure    │
                └────────────┘ └──────────┘  └────────────┘  └──────────────┘
                        │            │  (Task Queue: Redis/Celery ✅ → Temporal ⏳)
                        └──── results stream back via the append-only job event
                              log (Redis or in-memory) → WS → client; pub/sub ⏳
```

> **Status (`services/tools/executor.py`).** Steps 2, 5 and 6 run today: cache lookup, the `emits_structures` firewall, and the provenance record + cache write. **Step 1 does not exist** — `execute()` resolves the spec and drops straight into the cache lookup; a malformed `args` dict reaches `spec.handler(**kwargs)` (or the container's stdin) unchecked, surfacing as a `TypeError` wrapped in `ToolExecutionError` → HTTP 422. **Step 3** is a placeholder comment at `executor.py:74`. **Step 4** reads `ToolSpec` metadata, but the API constructs the service in `ExecutionMode.INLINE` and `_dispatch_slow()` still calls `_run_handler` inline — the queued slow path is reached only through `submit()`/`submit_batch()` (§4.3).

### 4.1 Two paths, one contract
- **Fast path** (`INSTANT` + `CPU_LIGHT`): executed inline in a fast worker — canonicalize, descriptors, similarity, substructure. Sub-second, synchronous, feels instant in the UI.
- **Slow path** (`SHORT`/`LONG`/`BATCH` or `GPU`/`CPU_HEAVY`/`EXTERNAL_API`): submitted via `submit()` / `submit_batch()` (`POST /jobs`, `POST /jobs/batch`), which return a `job_id`; progress + results **stream** back over `WS /jobs/{job_id}/stream`.

> **Status:** the path is chosen by the *caller* today, not the dispatcher. Every `ToolExecutionService` is constructed with the default `ExecutionMode.INLINE`, so `execute()` runs every tool inline whatever its compute class — `POST /tools/dock` (`CPU_HEAVY`/`LONG`, `timeout_s=600`) and `POST /tools/predict_admet` (`GPU`/`LONG`) still occupy the API request thread. `ExecutionMode.QUEUE`, `ToolSpec.is_fast_path`, and `_dispatch_slow()` are the reserved seam.

### 4.2 Scaling primitives
- **Heterogeneous worker pools (⏳)**, independently autoscaled on queue depth (KEDA on K8s): `worker-cpu` (RDKit-heavy), `worker-gpu` (ML/docking), `worker-io` (external APIs). Cheap to scale the CPU pool wide for academic burst; reserve scarce GPUs for the GPU queue.
- **Batch fan-out (map/reduce) (🟡):** a `BATCH` tool over a library is split into chunks by a coordinator, fanned across workers, with **streaming partial results**, early-exit, and cancellation. Wall-clock ≈ slowest chunk, not the sum. Essential for virtual screening / library profiling.
- **Content-addressed cache (🟡):** key = `sha256(tool, version, env_digest, org_id, args, seed)`. Deterministic chemistry is recomputed once, ever. **Tenant-scoped by default** (an input SMILES *is* IP — a global cache would leak that a structure exists; see §7). Hot in Redis, cold in object storage.
- **Idempotency keys (⏳)** so retries don't double-run; **backpressure (⏳)** so a flood of jobs degrades latency, not correctness.

> **Status:** only the cache exists as code, and only its key discipline is finished — `services/tools/cache.py` is an `InMemoryCache` dict private to each API/worker process, with no eviction, no TTL, no Redis and no cold tier (`result_cache_max` is a declared setting no code reads). Celery runs a single `default` queue with `task_routes` commented out, so there are no per-class pools to autoscale; `run_batch_job` walks its items sequentially in one worker — the per-item event stream is already the shape a `group`/`chord` emits (§4.3), but there is no chunk coordinator, early-exit or cancellation. Idempotency and backpressure are unwritten: `submit()` mints a fresh UUID per call, so a client retry runs the tool twice.

### 4.3 Execution backbone choice
- **Phase 0 (done):** fast-path inline via `execute()`; **slow path implemented** with Celery — `submit()`/`submit_batch()` enqueue `glowsky.run_tool_job`/`run_batch_job`, which emit an event stream to a shared `JobStore` (in-memory in *eager* mode, Redis across processes). `WS /jobs/{id}/stream` relays events live. With no `GLOWSKY_REDIS_URL`, Celery runs eager so the slow path works with zero infra; setting it flips on real workers + Redis with no code change.
- **Phase 2 (scale):** evaluate **Temporal** (durable, observable, retry-native workflows) for multi-step/long jobs, and/or **Ray** for distributed batch chemistry/ML fan-out. The batch task processes items sequentially today (per-item streaming already matches what a parallel group/chord emits) → swapping in a Celery `group`/`chord` or Ray is a task-internal change. Both slot behind the same dispatcher — no orchestrator changes.

---

## 5. Reproducibility & Provenance (academic non-negotiable)

Every execution returns an `ExecutionRecord`, carried on the `ToolResult`; the design loop additionally folds a per-step `ToolCallRecord` into `AgentRun.trace`.

```
ExecutionRecord (shipped)
{ tool, version, compute_class, determinism, env_digest,
  input_hash, cache_hit, duration_ms, seed?, error? }

AgentRun.trace entry — ToolCallRecord (shipped)
{ step, tool, tool_version, compute_class, input, summary,
  duration_ms, cache_hit, calls }

Still to add: run_id (the field exists on ExecutionContext and is forwarded to
              workers, but no caller sets it), worker, timestamp
```

`input_hash` is the first 16 hex chars of a content hash computed with a sentinel org id (`"_provenance"`), so it is stable across tenants and is deliberately *not* the cache key — the cache key is the full digest keyed on `ctx.org_id`.

- **Tool Environment Registry (⏳):** `tool_version → container image digest + dependency lockfile`, so reproducing a 2-year-old thesis result pulls the exact image. The hook is there — `ToolSpec.env_digest` rides in every `ExecutionRecord` and cache key — but it is the literal string `"builtin"` for all 22 built-ins and the raw `image:` ref for container tools; nothing resolves a digest or a lockfile.
- **Notebook export (✅)** *(`services/reporting/notebook.py`, `GET /runs/{id}/export?format=ipynb`)* emits a self-contained `.ipynb` that embeds the run's parent and candidate SMILES and *recomputes* their descriptors and MW/logP constraint filter with plain local RDKit — verifiable without Glowsky or an LLM in the loop — carrying the plan, explanation, and the `tool@version` trace as Markdown provenance. *Open:* emitting calls pinned to those tool versions and `env_digest`s (and seeds for `SEEDED` tools) so a run regenerates through the same code path rather than an equivalent one.
- **Determinism honored in cache (✅):** `NONDETERMINISTIC` tools are never cached; `SEEDED` cache on the seed.

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

Registration is **opt-in behind both** `GLOWSKY_ENABLE_CONTAINER_TOOLS=true` (default
`false`) **and** `GLOWSKY_TOOLS_DIR` (default unset) — shelling `docker run` needs a mounted
`/var/run/docker.sock`, which is root-equivalent on the host, so `docker-compose.tools.yml`
is the only stack that turns it on. With `GLOWSKY_TOOLS_DIR` alone the registry stays at the
22 built-ins. Five example tools ship under `examples/tools/`: `admet_ai`,
`molecular_formula`, and the three `logistics` partner tools.

```yaml
# glowsky-tool.yaml — as ContainerToolManifest actually parses it
name: acme_predict_herg          # bare name; `org:<id>.*` namespacing (§3) is not implemented yet
version: "1.2.0"
category: property               # lowercase — values are the ToolCategory enum strings
summary: hERG liability prediction
compute_class: gpu               # cpu_light | cpu_heavy | gpu | io_bound | external_api
latency_class: long              # instant | short | long | batch
determinism: deterministic       # deterministic | seeded | nondeterministic
image: registry/acme/herg@sha256:...      # pinned for repro (mutable tags break the cache key)
input_schema: {...}   output_schema: {...}
resources: {cpu: 2.0, mem_mb: 8192, gpu: 1, timeout_s: 120}
egress: none                     # none | allowlist
emits_structures: false
user: "65534:65534"              # optional; this is the default
```

Only `name` and `image` are required. Everything else defaults: `version` `0.1.0`, `category` `property`, `summary` `""`, `compute_class` `cpu_heavy`, `latency_class` `short`, `determinism` `deterministic`, `emits_structures` `false`, `egress` `none`, `resources` `{cpu: 1.0, mem_mb: 1024, gpu: 0, timeout_s: 120}`, `user` `65534:65534`.

- **SDK ergonomics (⏳ Phase 3):** the target is defining a tool by decorator + Pydantic I/O models, with the SDK generating the schema and (for container tools) building and pinning the image. Not built — there is no `packages/sdk/` yet. Today built-in tools are hand-registered as `ToolSpec` objects with hand-written JSON-Schema dicts in `services/tools/catalog.py`, and container tools are described by a hand-written `glowsky-tool.yaml`; `services/tools/manifest.py` parses that YAML into a `ToolSpec` and `load_container_tools()` auto-discovers and registers it — so registration is automatic, but schema generation and image build/pin are not.
- **Sharing & governance (⏳ Phase 3):** the target is tools as versioned artifacts — private to a user, shared org-wide, or published to a community registry, with admins approving/allowlisting custom tools. None of it exists: registration is filesystem-scoped (`GLOWSKY_TOOLS_DIR` on the host), so a manifest is visible to every org on the deployment and to none outside it. There is no tool table, no owner, no approval step.
- **Firewall still applies (✅):** any custom tool with `emits_structures: true` has outputs validated/canonicalized — a researcher's generative model can't inject garbage structures.

This is how Dr. Chen (`02-personas.md`, Primary Persona 3) turns "I have an internal model" into "it's an agent-callable tool the whole team uses" — **without us writing code**.

### 6.1 In-process backend adapters (the second seam)

The container manifest is the seam for *other people's* code. There is a second, narrower seam for heavy engines that live in-process: `services/chemistry/adapters/` defines a `Protocol` per capability (`ADMETBackend.predict()`, `DockingBackend.dock()`) and ships a refusing default — `NotConfiguredADMET` / `NotConfiguredDocking` raise `BackendNotConfigured`, which the API maps to **HTTP 501**. Glowsky never fabricates an ADMET value or a docking score; the tool is registered and discoverable, and it says so honestly when nothing is wired.

`configure_backends()` (`adapters/wiring.py`) applies the settings once per process — at the FastAPI lifespan and again on Celery's `worker_process_init`, so the API and the workers resolve the same backends.

| Setting (`GLOWSKY_` prefix) | Default | Enabled value | What it wires |
|---|---|---|---|
| `GLOWSKY_ADMET_BACKEND` | `none` → refuses (501) | `rdkit` → `RDKitQSPRADMET` | 7 offline endpoints — solubility, logd, herg, cyp3a4, metabolic_stability, ppb, bbb — of which only Delaney ESOL solubility is a published regression; the rest are logistic/rule heuristics carrying `method` + `confidence` + `applicability_domain` |
| `GLOWSKY_DOCKING_BACKEND` | `none` → refuses (501) | `vina` → `VinaDockingBackend` | AutoDock Vina as a subprocess; receptor refs must resolve under `GLOWSKY_DOCKING_RECEPTORS_DIR` (default `examples/docking`) so a caller-supplied path can never traverse the worker filesystem |
| `GLOWSKY_VINA_BIN` / `GLOWSKY_OBABEL_BIN` | `vina` / `obabel` | — | the binaries the Vina backend shells out to |

Matching is **exact string equality** — a typo or unrecognized value silently leaves the not-configured default, with no warning.

---

## 7. Security & multi-tenancy (in the tools layer)

- **Deterministic firewall (🟡):** a tool that declares `emits_structures` has its output walked recursively and every `smiles` value re-validated by RDKit before the caller sees it (`services/tools/executor.py::_firewall_validate`). *Current limits:* the walk matches the dict key `smiles` exactly and only when its value is a plain string, and only 2 of the 22 built-ins (`generate_analogs`, `bioisosteric_replacement`) declare `emits_structures` — every shipped example manifest declares `false`. Other structure-producing code is safe by its own construction rather than by this gate: `retrosynthesize` runs `validate_and_canonicalize` on each precursor before emitting them as a bare `precursors` list, and `io.parse_*` validates every imported record. Widening the walk to any SMILES-bearing key, and requiring `emits_structures` on custom tools that return structures, are the open items.
- **Sandboxing by runtime type (✅)** (§6): container tools get no ambient egress, CPU/mem/time caps, dropped capabilities — the same posture as `07-security-privacy.md` §6. Egress is fail-closed: an `egress: allowlist` manifest still gets `--network none`, because the Phase-3 proxy that would police an allowlist does not exist.
- **Tenant-scoped cache (✅):** `make_key()` folds `ctx.org_id` into every digest, so caching is per-org because the input structure is the IP. A *shared* cache for non-sensitive, purely-public deterministic computations is ⏳ — there is no opt-out switch today.
- **Quotas & fair scheduling (⏳ unbuilt):** per-org/user concurrency + compute budgets; **priority classes** (interactive fast-path > batch) so one lab's million-molecule screen doesn't starve another's interactive session. Backpressure over failure. Today this is a single comment line at `executor.py:74` — no quota module, no rate limiting (§12.5).
- **Egress control (⏳)** for remote/external-API tools; consent + audit on data sent out. Moot until `Runtime.REMOTE_HTTP` has an implementation (§6, §12.2).

---

## 8. Failure handling
- **Timeouts (🟡):** enforced where the work leaves Python — `resources.timeout_s` is a hard wall-clock kill on `docker run`, and the Vina subprocess caps at 600 s. A built-in handler still runs uncapped: `latency_class` declares an intent no code enforces.
- **Retries with backoff (⏳)** for transient/`IO_BOUND`; **circuit breakers (⏳)** for flaky external APIs. Celery's retry machinery is available but no task uses it.
- **Batch partial results (✅):** a failed item is recorded as `{index, args, error}`, streamed as its own `item` event, and counted into the job's `succeeded`/`failed` summary; the run continues (`run_batch_job`, no silent truncation).
- **Dead-letter queue (⏳)** for poison jobs. Failures are traceable in principle — `ToolExecutionError` carries the `ExecutionRecord` with tool/version/`input_hash` — but the Celery tasks stringify the exception into a `failed` event, so the record does not reach the job store.

---

## 9. Observability *(⏳ — none of this is built)*
The target: per-tool metrics — p50/p95 latency, error rate, **cache-hit rate**, queue depth, GPU utilization, cost — plus distributed tracing across dispatcher → worker → tool. The repo carries no logging, OpenTelemetry or metrics dependency, and no trace ID exists to surface. What ships instead is the **execution trace**: every design run returns the per-step `ToolCallRecord` list that the Composer and Design screens render, and every tool call returns an `ExecutionRecord` carrying `duration_ms` and `cache_hit` (`05-technical-architecture.md`, cross-cutting concerns).

---

## 10. The Tool Catalog to add (organized, prioritized)

Tools to build *into this frame*, by category. Priority: 🟢 MVP-ish (now/next) · 🟡 V1 · 🔵 Future. Compute class in brackets.

**Shipped today:** `build_default_registry()` registers **22 built-in tools**, all at version `0.1.0` — 17 on the fast path (`CPU_LIGHT`/`INSTANT`) and 5 on the slow path: `generate_analogs`, `bioisosteric_replacement`, `generate_conformers` (all `CPU_HEAVY`/`SHORT`), `predict_admet` (`GPU`/`LONG`) and `dock` (`CPU_HEAVY`/`LONG`). The molecule I/O layer (`services/chemistry/io.py`) ships but is REST-only — imported by the API, never registered as an agent-callable `ToolSpec`.

### Cheminformatics (RDKit) — mostly `CPU_LIGHT`/`CPU_HEAVY`
- 🟢 `validate_molecule` *(have)* — standardize + canonicalize + InChIKey; 🟡 `tautomer_canonicalize`
- 🟢 `compute_descriptors` *(have)*, 🟢 `profile_molecule` *(have)* — descriptors + druglikeness + alerts in one call; 🟡 extended descriptor set
- 🟢 `fingerprint` *(have)* — 2048-bit Morgan/ECFP4 or MACCS bit summary `[CPU_LIGHT]`; 🟡 the RDKit path fingerprint
- 🟢 `tanimoto_similarity` *(have)* (pairwise, Morgan) `[CPU_LIGHT]`, `bulk_similarity` *(have)* (rank a set against a query) `[CPU_LIGHT, batchable]`
- 🟢 `substructure_search` *(have)* — SMARTS match over a set `[CPU_LIGHT, batchable]`
- 🟢 `murcko_scaffold` *(have)* — Bemis–Murcko scaffold + generic scaffold
- 🟡 `cluster` (Butina / sphere-exclusion) `[CPU_HEAVY]`
- 🟡 `diversity_select` (MaxMin) `[CPU_HEAVY]`
- 🟡 `mcs` (maximum common substructure)
- 🟡 `enumerate_library` (scaffold × R-groups), `enumerate_stereoisomers`, `enumerate_tautomers`
- 🟢 `generate_conformers` *(have)* — ETKDG v3 embedding + MMFF minimization, reporting per-conformer energies `[CPU_HEAVY, SHORT, SEEDED]`
- 🟢 `convert_format` (SMILES/InChI/MOL/SDF parse+write) `[CPU_LIGHT]`

### Filtering & alerts — `CPU_LIGHT`
- 🟢 `structural_alerts` *(have)* — both RDKit `FilterCatalog` sets, PAINS **and** BRENK, returned as matched descriptions; 🟡 NIH and custom SMARTS sets
- 🟢 `druglikeness` *(have)* — Lipinski Ro5 (≤1 violation tolerated) + Veber only
- 🟢 `medchem_rules` *(have)* — the full 7-rule battery: Lipinski, Veber, Ghose, Egan, Muegge, lead-like, Rule of 3
- 🟢 `property_filter` — pull the orchestrator's inline filter into a first-class tool

### SAR & multi-parameter optimization — `CPU_LIGHT`
- 🟢 `mpo_score` *(have)* — piecewise-linear plateau desirability (Derringer / Pfizer-CNS-MPO convention) aggregated as a **weighted arithmetic mean** over the `oral` / `lead` / `fragment` profiles; returns the aggregate score, per-property desirabilities, and the `limiting` property. The design orchestrator ranks candidates by this score rather than raw QED.
- 🟢 `matched_pairs` *(have)* — Hussain–Rea single-cut MMP via `rdMMPA.FragmentMol(maxCuts=1)` over a caller-supplied set `[CPU_LIGHT, batchable]`
- 🟢 `sar_transforms` *(have)* — per-transformation n / mean / median / min / max Δ over 10 descriptors plus `mpo` (11 selectable properties), ranked by (support, |mean effect|) `[CPU_LIGHT, batchable]`
- 🟡 double-cut MMP (ring / linker replacement — today `maxCuts=1` only), 🟡 R-group decomposition, 🔵 free-Wilson analysis

### Property / ADMET — `CPU_HEAVY` or `GPU`
- 🟢 `sa_score` *(have)* — synthetic accessibility (Ertl & Schuffenhauer), 1=easy..10=hard `[CPU_LIGHT]`; 🟡 `scscore`
- 🟢 `predict_admet` *(have)* — a registered built-in `[GPU, LONG]`, but **adapter-gated**: the default backend refuses with HTTP 501 rather than fabricating values (§6.1). `GLOWSKY_ADMET_BACKEND=rdkit` enables the offline 7-endpoint RDKit-QSPR backend (solubility via Delaney ESOL; the rest logistic/rule heuristics, each carrying applicability domain & confidence). The same seam is satisfied from the outside by `examples/tools/admet_ai/` — ADMET-AI's pretrained Chemprop-RDKit GNN over ~40 TDC endpoints, weights baked in, running sandboxed under `--network none` as a container tool with zero Glowsky code change.
- 🟡 `predict_pka` / `logd`

### Generative — `GPU`/`CPU_HEAVY`, all `emits_structures: true`
- 🟢 `generate_analogs` *(have)* — R-group enumeration
- 🟢 `bioisosteric_replacement` *(have)* — 6 curated bioisostere SMARTS (acid→tetrazole / acylsulfonamide / hydroxamic / amide, ester→amide, ether→thioether) plus 1 aza-walk ring edit; knowledge-based, **not** BRICS `[CPU_HEAVY, SHORT, emits_structures]`
- 🟡 broader `scaffold_hop` (ring-system replacement beyond the nitrogen walk), 🟡 BRICS/fragmentation-based replacement
- 🔵 `de_novo_generate` (REINVENT-class) `[GPU, SEEDED]`
- 🔵 `fragment_grow` / `link` (BRICS, fragment merging)

### Structure-based — `CPU_HEAVY`/`LONG` (🔵 GPU for CNN scoring)
- 🟢 `dock` *(have)* — AutoDock Vina driven as a subprocess `[CPU_HEAVY, LONG]` (**not** GPU), adapter-gated like `predict_admet`: `GLOWSKY_DOCKING_BACKEND=vina` wires it, the default refuses with 501, and receptors are confined to `GLOWSKY_DOCKING_RECEPTORS_DIR`. 🔵 smina / gnina CNN scoring is the GPU step, unbuilt.
- 🟡 `detect_pocket`, `prepare_protein`, `prepare_ligand`
- 🔵 `interaction_fingerprint`, `minimize_pose`

### Retrosynthesis — `LONG`/`EXTERNAL_API`
- 🟢 `synthesizability` *(have)* — SA score + whether a recognised one-step route into building-block-like precursors exists; 🟡 SCScore still open
- 🟢 `retrosynthesize` *(have)* — 7 named one-step disconnections as retro-reaction SMARTS (amide coupling, esterification, sulfonamide formation, urea formation, Suzuki, reductive amination, Williamson ether), every precursor validated. "Purchasable" is the honest heuristic `heavy_atoms <= 12 and sa_score <= 3.5`, **not** a catalog lookup; 🔵 an AiZynth-class multi-step policy search `[LONG]` remains future
- 🔵 `building_block_availability` (catalog lookup) `[EXTERNAL_API]`

### Search — `EXTERNAL_API`/`CPU_HEAVY`
- 🟡 `similarity_search_corpus` (ChEMBL/known compounds) ; 🔵 patent/IP-aware search

> Each entry is small *because the frame does the heavy lifting* — a new tool is a `ToolSpec` + a function/image, and it inherits routing, scaling, caching, provenance, and sandboxing for free.

---

## 11. How this maps onto the code (status)

| Seam | Where it lives now | Status |
|---|---|---|
| The tool contract | `ToolSpec` — a 17-field frozen dataclass with `Resources` + six enums (`services/tools/spec.py`) | ✅ |
| Orchestrator/agent never touch a handler | Both go through `ToolExecutionService.execute()`; `spec.handler` is invoked in exactly one place, `executor.py:157` | ✅ |
| Registry, dispatcher, cache, provenance, jobs, manifests | `services/tools/{registry,catalog,executor,cache,result,store,jobs,context,manifest}.py` + `runtimes/container.py` | ✅ |
| A real catalog on top of the chemistry layer | 22 built-ins over `services/chemistry/*` plus the ADMET/docking adapters | ✅ |
| Compute-class routing | Celery slow path is shipped (`submit()`/`submit_batch()` → `WS /jobs/{id}/stream`), but `ExecutionMode` defaults to `INLINE` and `_dispatch_slow()` runs inline anyway | 🟡 |
| Provenance depth in the run trace | `ToolCallRecord` carries `compute_class` + `cache_hit`, but not `env_digest` or `seed` | 🟡 |
| Breadth + remote tools | `services/chemistry/{clustering,enumeration}.py` and the `REMOTE_HTTP` runtime | ⏳ |

**The seam that paid off:** the `ToolExecutionService.execute()` indirection. Because it landed first — even as a pass-through — every tool since has inherited caching, the firewall, and provenance for free, and the move to queues, GPU pools, and batch is still a change to `_dispatch()` alone. (`services/agent/registry.Tool`, the embryonic contract this section used to describe, no longer exists.)

---

## 12. Decisions — settled and still open
1. **Execution backbone for the slow path** — *settled:* Celery/Redis shipped. `submit()`/`submit_batch()` enqueue `glowsky.run_tool_job` / `run_batch_job`; with no `GLOWSKY_REDIS_URL` Celery runs eager, so the path works with zero infra. **Temporal** (durable workflows) and **Ray** (distributed batch fan-out) remain a Phase-2 evaluation, both behind the same dispatcher.
2. **Custom-tool runtime priority** — *settled:* builtin + container shipped, exactly as recommended. `Runtime.REMOTE_HTTP` is an enum member with no implementation, no manifest field, and no registration path — ⏳ Phase 3.
3. **Tool-catalog focus for the next build** — *still open:* which category to deepen first (cheminformatics breadth vs ADMET vs docking). *Recommendation: cheminformatics breadth + SA score (fast, high-leverage, all CPU-light) before GPU tools.*
4. **GPU strategy** — *settled for V1 as CPU-only:* `dock` is `CPU_HEAVY` (Vina subprocess), the RDKit-QSPR ADMET backend is CPU, and Celery runs one default queue with `task_routes` commented out. The loose end: `predict_admet` still declares `GPU` / `gpu=1` in its `ToolSpec` although both shipped ADMET paths are CPU.
5. **Quota & fair scheduling** — *open, and unimplemented.* Dispatcher step 3 (§4) is still the single line `# 3. quota / fairness check would go here (docs/13 §7).` — there is no quota module and no rate limiting anywhere. §7's per-org concurrency, compute budgets, and priority classes are all still design, not code.
