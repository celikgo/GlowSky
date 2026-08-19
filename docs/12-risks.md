# Glowsky — Key Technical Risks & Mitigations

Ordered roughly by severity × likelihood. The coloured dot on each heading is **severity** — 🔴 critical · 🟠 high · 🟡 medium · 🟢 lower — not the ✅/🟡/⏳ build-status key the other docs use. Each: **risk → why it matters → mitigation.** Where a mitigation is already in the code it is labelled **(today)**; **Known gaps** / **Known exposure** flag what is missing or currently unsafe, and **Planned** marks what is still to build — a mitigation with no such label is a plan, not a shipped control.

---

## 1. LLM hallucination of chemistry (correctness/trust) — 🔴 Critical
**Risk:** the model invents invalid SMILES, fake properties, or plausible-but-wrong reasoning. Chemists are expert skeptics; one bad fabricated structure destroys trust permanently.
**Mitigation:**
- **Deterministic firewall:** LLMs *plan and explain*; validated tools *compute*. No LLM-emitted structure is persisted until RDKit canonicalizes/validates it (`chemistry/validation`). Today no *candidate* structure originates from the model at all — analogs, bioisosteres/scaffold hops and retro precursors are enumerated by hard-coded RDKit reaction SMARTS (`generative.py`: 10 templates; `bioisosteres.py`: 6 bioisostere rules + 1 aza-walk; `retrosynthesis.py`: 7 named disconnections). The model emits a JSON plan, prose, and the tool arguments it selects in the tool-calling loop; each tool re-parses those inputs through RDKit. Known gap before a real generative model lands: the executor's second-net firewall runs only for the 2 of 22 built-in tools that set `emits_structures=True`, and inside their output it re-validates only dict keys named literally `smiles` — `canonical_smiles`, `scaffold`, `precursors` and bare SMILES lists pass through unchecked.
- Always surface **provenance + confidence + applicability domain**; never present predictions as ground truth. The `rdkit-qspr` ADMET adapter already emits a per-endpoint `confidence` and `applicability_domain`, but it is adapter-gated and off by default (`GLOWSKY_ADMET_BACKEND=none` → HTTP 501), so that honesty reaches only an operator who turns it on.
- **Plan and trace are visible (today):** every design run carries its `plan` and a step-numbered tool trace — tool, version, compute class, inputs, duration, cache hit — into `AgentRun.trace`, and the Design screen renders it as an **Execution trace** panel, so users see *how* a result was produced.
- **Planned:** a golden-set **chemistry-correctness suite**, advisor-reviewed. Today's chemistry tests assert invariants — canonicalization stability, salt stripping, invalid SMILES rejected rather than raised — not advisor-blessed reference values, and with no CI in the repo there is nowhere for such a suite to run on every change.
- **Validate before write; accept before promote.** Every generated structure is RDKit-validated first, then the run and its filter-passing candidates are persisted automatically — `persist` defaults to `true` on `/agent/design`, `/agent/chat` and both WebSocket variants, and the desktop client always sends `true`. `_persist()` writes an `AgentRun` plus a `Molecule` row for the seed and for each candidate whose `passed_filters` is set, linked by `origin_run_id`. The explicit human step today is *promotion*: "Save to library" decides what joins a library. Accept/reject *before* the write, and any way to delete a persisted candidate (there is no molecule `PATCH`/`DELETE` endpoint yet), are still to build.

## 2. BYO-LLM credential & IP security — 🔴 Critical
**Risk:** leaked API keys or proprietary structures = catastrophic, possibly company-ending for us and our customers.
**Mitigation (today):** provider keys are stored as Fernet ciphertext in `llm_provider_credentials.encrypted_secret` — plaintext is never persisted — and decrypted in-memory only at call time inside the Gateway's provider call; keys are never logged and are returned only as a masked hint. The single Fernet key comes from `GLOWSKY_SECRET_KEY`; `GLOWSKY_ENVIRONMENT` defaults to `production` and `validate_secret_config()` runs at API startup, so any non-dev environment refuses to boot without a real key. Tenant isolation is app-layer: tenant-owned tables carry `org_id` and cross-tenant reads 404 rather than 403. Every credential mutation writes an `AuditEvent`. See `07-security-privacy.md`.

**Planned:** move to a KMS-backed secrets manager (opaque refs only in the DB) with envelope encryption and per-tenant data keys — today's single-key design has no rotation path, since `_fernet()` caches one key with no MultiFernet fallback; add Postgres RLS behind the app-layer checks, explicit redaction middleware, and enterprise CMK/BYOK plus self-host/VPC. Third-party pen-tests before enterprise sales.

## 3. Provider fragmentation & capability drift (BYO-LLM) — 🟠 High
**Risk:** providers differ in tool-calling, context windows, streaming, JSON reliability; a local Llama can't do what Claude/GPT can. Agent features may silently break per model.
**Mitigation (today):** one Gateway (`services/llm_gateway/`) owns provider choice, key resolution and routing, and LiteLLM normalises tool-calling across the four supported providers — `anthropic`, `openai`, `groq` and the OpenAI-compatible `local`. Routing is per task class (`reasoning`, `fast_triage`, `codegen`) with per-org overrides through `PUT /settings/routes`, so planning can use a capable model even if a cheap one does triage. A route whose provider has no key degrades to the deterministic offline mock rather than failing, so the loop always runs.

**Known gaps:** that degradation is *credential*-level, not *capability*-level — nothing inspects whether the routed model can tool-call before handing it the registry's schemas, and there are no capability flags. Structured output is best-effort: `_propose_plan()` wraps `json.loads` in a bare `except` and returns a default plan instead of validating against a schema and retrying. `codegen` is routable and surfaced in `/health` and `/settings/routes`, yet no code path ever issues a completion with it, and there is no provider-compatibility test matrix.

**Planned:** capability flags with per-feature degradation, schema-validated structured output with retries, a curated "recommended models" list, and continuous provider-compatibility tests.

## 4. Long-running compute: cost, latency, reliability — 🟠 High
**Risk:** docking, generation, ML inference are slow/expensive/flaky; naive sync design stalls UX and bills explode.
**Mitigation (today):** a Celery/Redis slow path with WebSocket progress streaming backs `POST /jobs`, `POST /jobs/batch` and `WS /jobs/{id}/stream` (Celery falls back to eager in-process execution when `GLOWSKY_REDIS_URL` is unset); deterministic tool results are cached on a tenant-scoped key of `(tool, version, env_digest, org, args, seed)`; per-tool timeouts are enforced for container tools and for the Vina docking subprocess (600 s).

**Known gaps:** `POST /tools/{name}` and the agent loop still execute every tool inline on the request thread regardless of compute class — `ExecutionMode.QUEUE` is never set and `_dispatch_slow()` runs inline anyway — so `dock` (CPU_HEAVY/LONG) and `predict_admet` (GPU/LONG) block a request worker. The result cache is an unbounded per-process dict with no TTL or eviction, and the API and each Celery worker hold separate copies. Deployment is one generic `default` queue and a single `worker` service, not isolated autoscaling pools. There are no per-org quotas, no Celery retry policy, no idempotency key, no timeout on in-process handlers or LLM-gateway calls, and no cost budget.

**Planned:** route by compute class to autoscaling pools, a shared Redis + object-store result cache, quota/fairness at the dispatcher hook, Temporal for durable workflows in Phase 2, and user-facing cost budgets.

## 5. Scientific credibility of predictions/generation — 🟠 High
**Risk:** open ADMET/docking/generative models can be inaccurate or misapplied; over-promising "AI drug design" invites expert backlash.
**Mitigation:** honest framing (decision-support, with uncertainty), applicability-domain warnings, cite model provenance, let users swap in their own validated models (extensibility), CADD advisor reviews defaults, under-promise in marketing. Position as augmenting the chemist, not replacing judgment.

## 6. Sandboxing & prompt-injection / tool abuse — 🟠 High
**Risk:** untrusted content (uploaded PDFs, RAG sources, registered HTTP tools) hijacks the agent to exfiltrate data or run unintended tools; code-exec escapes isolation.
**Mitigation (today):** the typed registry *is* the allowlist — `registry_to_tool_schemas()` offers the model every registered spec and nothing else, with `tool_choice="auto"`; there is no per-org or per-agent tool scoping yet. No arbitrary code exec. Container tools are **off by default**; when enabled each call runs one-shot as `docker run --rm --interactive --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --memory <mem_mb>m --cpus <cpu> --tmpfs /tmp:rw,size=256m --network none --user 65534:65534 -- <image>` under a hard wall-clock timeout, with the image after an explicit `--` so an image ref cannot inject flags. Egress **fails closed**: a manifest declaring `egress: allowlist` still gets `--network none`. See `07-security-privacy.md` §5–6.

**Known exposure — host Docker socket:** the only shipped way to turn container tools on is the `docker-compose.tools.yml` overlay, which mounts `/var/run/docker.sock` into **both** the `api` and `worker` services. That is root-equivalent on the host. It is therefore opt-in, kept out of `docker-compose.yml` and `docker-compose.prod.yml`, and documented as **trusted single-tenant / local dev only**. Replacing the socket with a rootless/sysbox/gVisor builder or a dedicated tool-runner service is a prerequisite for any hosted/multi-tenant deployment.

**Planned:** instruction/data separation for retrieved and tool-returned content, per-tool consent + a real egress-allowlist proxy, explicit human-in-loop gates, and per-org tool scoping.

## 7. Chemistry deployment/dependency complexity — 🟡 Medium
**Risk:** RDKit, docking binaries, ML frameworks (CUDA), conda-heavy deps are painful to containerize and to self-host reproducibly.
**Mitigation (today):** the whole chemistry stack is pip-installable wheels — `rdkit>=2024.3` is the *only* chemistry dependency, with no conda and no ML framework anywhere — and the images stay deliberately boring: `infra/docker/api.Dockerfile` (`python:3.13-slim` plus the few shared libs RDKit needs, and the docker CLI) serves both the API and the Celery worker, while `infra/docker/docking.Dockerfile` layers AutoDock Vina 1.2.5 + OpenBabel behind the opt-in `docker-compose.docking.yml` overlay, pinned to `linux/amd64` because Vina ships x86_64 binaries only.

**Known gaps:** dependencies are floors (`>=`), not pins, and there is no Python lockfile — `apps/desktop/pnpm-lock.yaml` is the only lockfile in the repo — so a rebuild is not reproducible. With no CI, nothing rebuilds or smoke-tests the self-host images; `python:3.13-slim` is the only interpreter actually exercised even though `pyproject.toml` claims 3.11–3.13. No Helm chart, no IaC, no air-gapped recipe, no documented GPU/CPU requirements, and the "light API image" and the heavy chem/GPU worker image are still the same image.

**Planned:** pin/lock the dependency set, split a purpose-built worker image from the API image, build and test the self-host images once a CI pipeline exists, and publish Helm + air-gapped configs alongside Compose.

## 8. UX complexity — the "Cursor-like" bar is high — 🟡 Medium
**Risk:** delivering true IDE-grade fluidity (instant render, streaming, multi-panel, Cmd+K, diffs) is hard; a clunky UX kills the core promise.
**Mitigation (today):** reuse battle-tested libraries rather than hand-rolling renderers — client-side RDKit-JS (WASM, `@rdkit/rdkit` 2025.3.4-1.0.0) for instant 2D validation/depiction, Ketcher 3.15 standalone for 2D editing, and lazy-loaded 3Dmol.js 2.5.5 for conformers and docking poses; WebSocket streaming so Composer and Design fill in as the run progresses; a ⌘K command palette and an inspector openable from any card; ship the loop narrow-but-polished (Maya) before broad.

**Planned:** Mol\*/NGL if 3Dmol.js runs out of road, Monaco once anything in-app needs a code editor (notebooks are generated server-side and downloaded today), AG Grid or TanStack Table when library views need virtualization, explicit perf budgets (sub-second interactions) and a design-partner feedback loop.

## 9. Scope creep / boiling the ocean — 🟡 Medium
**Risk:** chemistry is vast (ADMET, docking, retrosynth, RAG, generative, MPO, FEP…); trying to do all in MVP = ship nothing.
**Mitigation:** ruthless MVP scoping (`08`) — one persona deep, one of each capability; phased roadmap; the extensibility seam (manifest-declared container tools) was **not** deferred — it shipped in Phase 0 alongside the registry — but it stays **off by default**: `build_registry()` registers container tools only when *both* `GLOWSKY_ENABLE_CONTAINER_TOOLS=true` (default `false`) and `GLOWSKY_TOOLS_DIR` are set, and the default + prod compose stacks are socket-free; "one engine per capability" rule for MVP (one ADMET backend, `none|rdkit`; one docking backend, `none|vina`).

**Watch item:** the container seam already carries non-chemistry partner tools — `logistics` is a member of the core `ToolCategory` enum and three of the five `examples/tools/` manifests are ULD-line tools (`apron_energy`, `cargo_dimensioning`, `damage_detect`). Useful proof that the registry is domain-agnostic, and exactly the surface where scope creep would enter first.

## 10. Concentrated demand / market & GTM risk — 🟡 Medium
**Risk:** niche audience; academics pay little; enterprises buy slowly and demand security/compliance before adopting.
**Mitigation:** BYO-LLM keeps our cost-to-serve near zero for the free/academic base (bottom-up growth + word-of-mouth); land in academia → expand to teams → enterprise; champion-led (Dr. Chen) enterprise motion; SOC 2 + self-host unlock pharma; clear, defensible value (the loop) rather than feature-matching incumbents.

## 11. Reproducibility/provenance debt — 🟡 Medium
**Risk:** if provenance isn't captured from the start, notebook export and "defensible in DRC" promises fail, and retrofitting is painful.
**Mitigation (today):** the provenance schema landed in Phase 0 and everything hangs off it — `AgentRun` stores the goal, the plan, `models_used` and the full tool trace; every generated `Molecule` carries `origin_run_id`; and each `ExecutionRecord` pins tool name, version, compute class, `env_digest`, an input hash, the seed, cache-hit and duration. `GET /runs/{run_id}/export` renders a run as a Jupyter notebook or a Markdown report, and the export tests *execute* the generated code cells rather than merely parsing them. The `run_id` is surfaced in the Design and Composer screens.

**Known gaps:** prompts themselves are neither hashed nor stored — provenance records which models ran and the plan they produced, not the text that produced it. There is no molecule versioning and no `updated_at` on any table; a persisted structure is immutable only by omission (no `PATCH`/`DELETE` endpoint exists), not by design.

## 12. Vendor/library longevity & lock-in — 🟢 Lower
**Risk:** dependence on a single provider abstraction (LiteLLM), and — if we later adopt one — on a fast-moving agent framework.
**Status:** no agent framework is used today. `langgraph`/`langchain` appear in no source file, in `pyproject.toml`, or in `apps/desktop/package.json`. The orchestration is hand-written against the versioned typed tool registry: `orchestrator.py` is a fixed six-stage design loop making exactly two LLM calls, and `tool_loop.py` is a `for _ in range(max_steps)` tool-calling loop (`max_steps` defaults to 6). So LangGraph-class lock-in has not been taken on.
**Mitigation:** keep the tool layer framework-agnostic; the Gateway confines LiteLLM to a single `LiteLLMProvider` class whose `import litellm` is lazy, inside `complete()`, and is the only such import in the codebase; everything self-hostable/open so no single managed vendor is load-bearing.

---

## Risk posture summary
The two existential risks are **chemistry hallucination/trust (#1)** and **credential/IP security (#2)** — both are addressed by core architectural decisions made in **Phase 0**, not bolted on later: the deterministic firewall, and an isolated key-resolution boundary in the Gateway (`KeyStore`), designed so a KMS-backed store drops in behind the same interface. The remaining risks are managed by phasing, abstraction layers, caching/async infra, and a disciplined MVP scope.
