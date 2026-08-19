# Glowsky — Security & Privacy Considerations

Security is existential here: customers entrust us with (a) **LLM provider credentials** and (b) **proprietary research data / IP** that can be worth hundreds of millions. The architecture treats security as a first-order concern.

> **Status legend.** Controls below are tagged ✅ **shipped** (enforced in the current build), 🟡 **partial** (some of it enforced), or ⏳ **planned** (design intent, not yet built). §10 is the authoritative list of what the shipped build enforces today — when the prose and §10 seem to disagree, §10 wins.

---

## 1. Threat model (what we protect against)
- **Credential theft** — exfiltration of BYO-LLM API keys (ours-stored on behalf of users).
- **IP leakage** — proprietary structures/data leaking to other tenants, to us, or to unauthorized LLM providers.
- **Cross-tenant access** — one org reading another's data (SaaS).
- **Prompt injection / tool abuse** — malicious content (uploaded docs, RAG sources, registered tools) steering the agent to exfiltrate data or run unintended tools.
- **Code-execution escape** — sandboxed code/notebook tools breaking isolation.
- **Insider/operator access** — Glowsky staff reading customer data or keys.
- **Supply-chain** — compromised dependency (large Python/JS surface).

---

## 2. BYO-LLM credential security
- 🟡 **Never store plaintext keys.** *Today:* provider keys are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256) in `services/core/crypto.py`, under an operator-supplied `GLOWSKY_SECRET_KEY`; the `llm_provider_credentials` row holds only the ciphertext plus a masked display hint alongside non-secret metadata. `GLOWSKY_ENVIRONMENT` defaults to `production`, and startup (`validate_secret_config`, the first statement of the API lifespan) refuses to boot unless either a real `GLOWSKY_SECRET_KEY` is set or the environment is explicitly a dev tier (`dev`/`development`/`local`/`test`/`testing`/`ci`) — so a self-host that forgets the key fails closed. *Planned (Phase 1+):* move to a KMS-backed secrets manager (AWS Secrets Manager / Vault) so the DB holds only an opaque reference — the `KeyStore` interface in `services/llm_gateway/keys.py` is the seam. Note there is no key-rotation path today: `_fernet()` is `@lru_cache(maxsize=1)` over a single key with no MultiFernet fallback, so rotating `GLOWSKY_SECRET_KEY` makes every stored credential permanently undecryptable.
- ⏳ **Envelope encryption**, per-tenant data keys, key rotation. At-rest encryption everywhere. *None of this exists yet — today it is one process-wide Fernet key, as above.*
- 🟡 **Decrypt only in-memory, only at call time**, only in the LLM Gateway — shipped: ciphertext is decrypted on the way into a completion, and keys are **never logged**, never returned to the client after entry (the API hands back a masked hint only). ⏳ The *explicit redaction middleware* that would also scrub keys from traces and error messages is not built.
- 🟡 **Scope & least privilege:** today credentials are org-scoped only — exactly one row per `(org, provider)` — and adding or deleting one requires `require_write`, so a viewer can neither store nor remove a key. ⏳ User-scoped credentials, and a separate "may use but not manage" grant, are planned.
- 🟡 **Egress control (largely planned):** *today* — outbound LLM calls go directly from the gateway to whatever `provider/model` the active route names (`litellm.acompletion`); for the `local` provider the endpoint is whatever `base_url` the operator or org stored, unvalidated. There is no endpoint allowlist and no egress proxy. The only allowlist in place is a provider-*name* check (`anthropic|openai|groq|local`) enforced when storing a credential; `PUT /settings/routes` does not apply it. *Planned:* provider-endpoint allowlisting and optional egress-proxy logging (metadata only) for enterprise.
- 🟡 **Bring-your-own-endpoint for enterprise:** shipped today as the `local` provider — a customer points it at their own OpenAI-compatible endpoint (vLLM, an internal gateway) so keys and data never leave their boundary. The supported set is exactly `anthropic`, `openai`, `groq`, `local`, plus an offline mock. ⏳ First-class Bedrock/Azure/Vertex providers are *not* supported — a route naming one silently degrades to the offline mock rather than erroring.

---

## 3. Research data & IP protection
- 🟡 **Tenant isolation:** every tenanted domain row carries `org_id`; pure join tables (e.g. `library_memberships`) carry only their parent FKs and inherit tenancy transitively. Enforced today by app-layer checks on every read/write path — `load_project`/`load_library`/`load_run` return **404, never 403**, across tenants, so existence is never confirmed to another org and "not yours" gets the same answer as "not there"; list endpoints filter on `org_id`, and the job store and WebSocket stream re-check the job's `org_id` before relaying anything. Postgres row-level security is planned as defense-in-depth behind those checks; it is not yet enabled (and the default self-host engine is SQLite, which has no RLS). Self-hosted = single tenant by construction. *Known hardening gaps in the schema:* `audit_events.org_id` is an indexed `String` with no foreign key to `organizations.id`, unlike every other tenanted table; and `molecules.org_id` / `agent_runs.org_id` carry an ORM-level default of `LOCAL_ORG_ID` (`"local-org"`) rather than being required, so an ORM write path that omits `org_id` silently lands in the local tenant instead of failing.
- ⏳ **Data residency:** SaaS regional selection (e.g., EU-only); enterprise self-host/VPC for full control; air-gapped mode (local LLM + no external literature calls). *Self-host plus the `local` provider is the shipped approximation — Glowsky makes no external literature calls at all today — but there is no region selector and nothing enforces residency.*
- 🟡 **Encryption:** TLS in transit and AES-256 at rest are **deployment responsibilities** — the app terminates no TLS of its own and ships no disk encryption; put it behind an ingress/reverse proxy and encrypt the volume. ⏳ Per-tenant encryption keys, and object-storage/backup encryption, are planned (there is no object storage yet).
- 🟡 **What we send to LLM providers:** shipped — the Settings screen and `GET`/`PUT /settings/routes` let an org see and change which provider/model serves each task class (`reasoning`, `fast_triage`, `codegen`), so routing is explicit and controllable. ⏳ Surfacing each provider's retention policy, defaulting to zero-retention endpoints, and warning when a chosen provider may retain/train are not built.
- ✅ **Minimize what leaves the deterministic core:** real in the code — chemistry compute is local RDKit, candidate structures are enumerated by reaction SMARTS rather than emitted by a model, and a design run makes exactly two LLM calls carrying the plan/summary context, never entire libraries.
- ✅ **No silent telemetry of content.** There is no telemetry, analytics or crash-reporting client anywhere in the repo — nothing phones home at all. ⏳ Any content-bearing diagnostics that ship later must be opt-in.

---

## 4. Operator / insider controls
- ⏳ **Least-privilege staff access**, just-in-time elevation, audited. Production data access requires approval + logging. *Organizational controls for a hosted plane that does not exist yet; nothing in this repo enforces them.*
- ⏳ **No standing access to secrets.** This depends on the KMS-backed secrets manager in §2, which is not built — today anyone with the database plus `GLOWSKY_SECRET_KEY` can decrypt every stored credential.
- ⏳ **Customer-managed keys (CMK/BYOK)** option for enterprise so even we can't decrypt at rest.
- 🟡 Full **audit log** (`AuditEvent`) of access and admin actions. Shipped as a table plus an `audit()` helper written on the consequential mutations — `project.create`, `library.create`, `library.import`, `credential.add`, `credential.delete`, `route.set`, `route.clear`, `run.design`. ⏳ No read or export endpoint exists yet; the rows are reachable only in the database.

---

## 5. Prompt injection & agent safety
- ✅ **Tool allowlisting:** the agent acts only through the typed tool registry — 22 built-ins, plus any opt-in container tools. No arbitrary actions.
- ✅ **No default arbitrary code execution.** Container execution is opt-in behind *both* `GLOWSKY_ENABLE_CONTAINER_TOOLS=true` and `GLOWSKY_TOOLS_DIR` (see §6), sandboxed, and never auto-invoked from untrusted content.
- 🟡 **Treat RAG/document/tool content as untrusted:** the orchestrator keeps system instructions, conversation, and tool output in separate message roles, and any tool declaring `emits_structures` has its output passed through the RDKit validation firewall before it is surfaced. Sandboxed container tools get no ambient network: the `ALLOWLIST` egress class currently **fails closed** to `--network none`. *Gap today:* tool **arguments are not validated server-side**. `ToolSpec.input_schema` is only advertised to the model and `ToolSpec.output_schema` is never read anywhere in the repo; `execute()` goes resolve → cache lookup → `spec.handler(**kwargs)`, and for container tools the args are `json.dumps`'d verbatim onto the container's stdin. A malformed call therefore fails as a handler `TypeError` surfaced as HTTP 422, not as a schema rejection. Guardrails for registered HTTP tools are **planned, not implemented** — `Runtime.REMOTE_HTTP` has no implementation.
- 🟡 **Human-in-the-loop for library curation:** a design run's output is persisted as provenance — one `AgentRun` row plus a `Molecule` row for the seed and one per filter-passing candidate, linked by `origin_run_id` and recorded as a `run.design` audit event. Those rows are not library members: a candidate enters a **library** only when a chemist explicitly multi-selects and saves it. Note the provenance write itself is on by default: `persist` defaults to `true` on `DesignRequest` and `ChatRequest` and on both WebSocket variants, and the desktop client hard-codes `persist: true` at all three call sites. *Planned:* a client-side zero-write mode, and a `persist=false` default for teams that want no writes without explicit confirmation.
- 🟡 **Output validation:** the design loop never accepts a structure *from* the model at all — every candidate is enumerated by RDKit reaction SMARTS — and every imported structure is canonicalized/validated before it is persisted; invalid → rejected, never persisted as truth. The `_firewall_validate` firewall itself is narrower than the name suggests: it runs only for tools declaring `emits_structures=True` (2 of the 22 built-ins — `generate_analogs`, `bioisosteric_replacement`) and inspects only dict keys named literally `smiles`.
- ⏳ **Confused-deputy protection for custom tools (Phase 3 — not implemented):** registered HTTP tools (`Runtime.REMOTE_HTTP`) are declared in the tool contract but have no runtime yet. When they ship they will run with declared scopes/auth, show/consent the data sent to them, and be subject to an egress allowlist.

---

## 6. Compute & code sandboxing
- ✅ Container tools run in **isolated containers** with: CPU/mem/wall-clock limits, read-only base FS (`--read-only` plus a 256 MB `/tmp` tmpfs for scratch), **no ambient network egress**, dropped capabilities (`--cap-drop ALL`), `--security-opt no-new-privileges`, `--pids-limit 256`, and a non-root `--user` (default `65534:65534`) — Docker's default seccomp profile applies; no custom profile is shipped. Note: container tools that declare `egress: allowlist` in their `glowsky-tool.yaml` are currently also given `--network none` — the allowlist-honoring proxy does not exist yet, so the runtime fails closed rather than falling through to Docker's default bridge. The downgrade is silent — no warning or log line — so treat `allowlist` as equivalent to `none` for now.
- ✅ **Container egress fails closed** for both the NONE and ALLOWLIST classes.
- ✅ One-shot, ephemeral execution environments per job (`docker run --rm --interactive`, fresh tmpfs each time); no shared mutable state.
- ✅ **Path confinement for file-taking tools:** the Vina docking backend resolves a caller-supplied `receptor_ref` against the receptors root (`GLOWSKY_DOCKING_RECEPTORS_DIR`, default `examples/docking`) with a realpath containment check that raises *before* any existence test, so an out-of-bounds path can neither be docked against nor used as a file-existence oracle.
- 🟡 **Today this runtime is off by default, and turning it on is a host-level trade-off.** Container (docker-run) tools require *both* `GLOWSKY_ENABLE_CONTAINER_TOOLS=true` and `GLOWSKY_TOOLS_DIR`; the default stack (`docker-compose.yml`) and the production stack (`docker-compose.prod.yml`) are both socket-free and register none of them. Built-in RDKit chemistry runs in-process and is unaffected. The only shipped way to enable them is the opt-in `docker-compose.tools.yml` overlay, which mounts `/var/run/docker.sock` into **both the api and worker** containers — full control of the host Docker daemon, i.e. **effectively host root**. That is acceptable only on a trusted, single-tenant or local-dev host, and is *not* acceptable for a hosted or multi-tenant deployment. Before this runtime is enabled in multi-tenant SaaS, the socket mount must be replaced by a rootless/sysbox/gVisor builder or a dedicated, network-isolated tool-runner service (deferred).
- ⏳ Resource quotas per org to prevent abuse/DoS. *Not implemented: the quota/fairness check is a single comment line in `services/tools/executor.py`, and there is no rate limiting anywhere in the codebase.*

---

## 7. Application & platform security
- ✅ **AuthN (delegated):** Glowsky runs no identity store of its own and holds no passwords or API keys. Every authenticated request carries a platform JWT issued by **nakitte-carbon-auth** (`Authorization: Bearer <jwt>`; WebSocket endpoints take the same token as a `?token=` query param or in the first init frame). Glowsky verifies the RS256 signature statelessly against the carbon-auth JWKS (`GLOWSKY_NAKITTE_JWKS_URL`), requiring `exp` and `sub`, checking `aud` (default `carbon-platform`) and `iss` when `GLOWSKY_NAKITTE_JWT_ISSUER` is set, with 30 s clock-skew leeway; a token without a `tenant_id` claim is rejected. The token's `sub`/`tenant_id`/`roles` become the request principal, and the tenant is JIT-provisioned into Glowsky's local org/user/membership mirror on first sight. OAuth/OIDC providers, SSO/SAML/SCIM and MFA are therefore properties of the carbon-auth identity service, not of Glowsky.
- ✅ **AuthZ:** org-scoped RBAC (owner/admin/editor/viewer, carried on `Membership`); enforced server-side on every data-bearing request.
- 🟡 **Session security:** bearer JWTs only — no cookies anywhere, so the API carries no ambient credential and no CSRF surface. Every request re-verifies the token. Token lifetime and refresh-token rotation are carbon-auth's to enforce: Glowsky only proxies `POST /auth/refresh`, and the desktop client silently refreshes and replays a REST call once on a 401. Known gaps: the desktop keeps both tokens in `localStorage` rather than an OS keychain, plus a build-time `VITE_AUTH_TOKEN` fallback compiled into the bundle; WebSocket auth passes the JWT as a query param or in the first message frame, and neither path benefits from the silent-refresh retry; and a socket is authorized once at open and never re-authorized for the life of the stream.
- 🟡 **Input validation & limits:** API request bodies are schema-validated by Pydantic; import formats are allowlisted (`smiles`/`csv`/`sdf`); and every imported structure, plus the output of any tool declaring `emits_structures`, passes the RDKit validation firewall. *Not yet implemented:* enforcement of declared tool-argument schemas, request/body-size caps — `ImportRequest.content` is an unbounded `str` carrying whole SMILES/CSV/SDF payloads — content/malware scanning of imported files, and per-tenant/user rate limiting (no rate-limit code exists; the per-org quota check is still a placeholder comment in `services/tools/executor.py`).
- 🟡 **Secrets hygiene:** no secrets in code or repo — `.env.example` carries placeholders only, and the one in-source key is the deliberately public dev Fernet passphrase that the boot guard refuses to use outside a dev environment. ⏳ Nothing scans for leaked secrets: **this repository has no CI of any kind**, so there is nowhere for a scanner to run — and there is no rotation path (§2).
- ⏳ **Dependency/supply-chain:** SCA scanning, SBOM, signed images and a patching cadence are all planned; none exist. Python dependencies are declared as floor constraints in `pyproject.toml` with no lockfile (the desktop side does have `pnpm-lock.yaml`).
- ⏳ **SAST/DAST** and periodic third-party pen-tests. The first two need a CI pipeline, which this repo does not have.

---

## 8. Privacy & data lifecycle
- ⏳ **Data ownership:** customers own their data and IP; we are processors. Clear DPA. *A commercial commitment; no DPA exists yet.*
- 🟡 **Deletion & export:** export is shipped per library (`GET /libraries/{library_id}/export`) and per run (`GET /runs/{run_id}/export`). ⏳ Account-level export, hard-delete on request, defined retention and backup expiry are not built — the only `DELETE` routes today are for provider credentials and route overrides.
- ✅ **Minimization & purpose limitation:** trivially true today — content is excluded from analytics because there is no analytics pipeline, and never trains a model because there is no training pipeline. ⏳ Keeping that property honest is a standing constraint on anything we add.
- ⏳ **Sub-processor transparency:** list LLM/infra sub-processors; let enterprises restrict to chosen providers/regions. *The four supported providers are visible in Settings, but there is no published sub-processor list or restriction mechanism.*

---

## 9. Compliance posture (roadmap)
Nothing in this section is in place today — no audit, no certification, no DPA. It is the sequence we intend to work, not a claim.

- **Target SOC 2 Type II** as the early enterprise gate; **GDPR** (EU residency, DPA, DSRs) from the start of EU sales.
- **HIPAA** generally N/A (no PHI) but assess if any customer data implicates it.
- **Patent/FTO disclaimer:** literature/IP features are decision-support, **not legal advice**; clearly labeled to avoid liability and set expectations.
- Self-host docs + a **Compose hardening guide** so enterprises can meet their own controls (deployment today is four root Compose files and two Dockerfiles — there is no Helm chart, Kubernetes manifest or other IaC in the repo).

---

## 10. Security non-negotiables for MVP
These are the MVP non-negotiables as the current build implements them — the authoritative list. All but item 3 are enforced in code; TLS is the one control here delegated to the deployment.
1. Encrypted key storage (Fernet) under an operator-supplied key, with a fail-fast startup guard; keys never logged, never returned to the client (masked hint only). KMS-backed secrets-manager storage layers on in Phase 1+.
2. Tenant isolation by app-layer org scoping on every read, with cross-tenant reads returning 404. Postgres RLS is planned, not shipped.
3. TLS terminated at the ingress/reverse proxy (deployment responsibility, not enforced by the app); at-rest encryption per deployment.
4. Server-side authz on every data-bearing endpoint — 30 of the 38 HTTP routes are gated (12 `require_write`, 18 `current_principal`), and `current_principal` has no auth bypass in any environment. The 8 ungated routes are deliberate exceptions except where noted: `GET /health`, the four `/auth/*` proxies, `GET /settings/providers`, and two known gaps to close — `GET /tools` (returns the full tool discovery catalog unauthenticated) and `POST /molecules/diff` (the only `/molecules/*` compute route without a principal). All 3 WebSocket routes authenticate too: two enforce write, `/jobs/{job_id}/stream` enforces read.
5. No default arbitrary code exec: container tools are off unless *both* `GLOWSKY_ENABLE_CONTAINER_TOOLS` and `GLOWSKY_TOOLS_DIR` are set, and when on they run one-shot and network-less as a non-root user. Enabling them today means mounting the host Docker socket (§6) — host-root-equivalent, and not acceptable multi-tenant.
6. RDKit validation on every imported structure and on the output of the two tools declaring `emits_structures`; the design loop never takes a structure from the model at all.
7. Audit rows (`AuditEvent`) on the consequential mutations — project/library create, library import, credential add/delete, route set/clear, design run. No read or export endpoint yet.

Everything else — KMS-backed secrets, RLS, rate limiting, egress allowlisting, CMK, air-gap, SOC 2 — is 🟡 or ⏳ above; SSO/SAML lands in nakitte-carbon-auth, not here.
