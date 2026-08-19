# Glowsky — Data Models (high level)

Conceptual model, not final DDL. Postgres is the system of record; JSONB used for flexible/extensible attributes; object storage holds large artifacts (SDF, PDB, notebooks, reports); vector store holds embeddings. IDs are UUID **strings** in plain `String`/`text` columns (SQLAlchemy `default=_uuid`, i.e. `str(uuid.uuid4())`), never a native `uuid` column type, and never validated as UUIDs. Two exceptions: `organizations.id` and `users.id` carry that default too but never fire it — every row is written with the carbon-auth JWT's `tenant_id` and `sub` claims verbatim on JIT provisioning — and the built-in fallback tenant that `init_db()` seeds into every database (including production) uses the literals `local-org` / `local-user`, which are also the column defaults for `org_id` on molecules and agent runs. Most domain rows carry `org_id` for tenant scoping + audit fields (`created_at`, `updated_at`, `created_by`).

> **Status legend.** ✅ shipped · 🟡 partial · ⏳ planned. Per-entity notes below open with
> **Shipped** wherever a real table backs the sketch — read that as the ✅ of this page — and
> spell out how the table departs from the sketch; an unannotated entity is ⏳.

**What ships today.** 28 entities are sketched below; 12 SQLAlchemy tables actually exist (`services/core/models.py`), over a linear 3-revision Alembic chain, head `f68490608234`: ✅ `organizations`, `users`, `memberships`, `api_keys`, `projects`, `libraries`, `library_memberships`, `llm_provider_credentials`, `model_route_overrides`, `audit_events`, `molecules`, `agent_runs` — eleven of those sketches, plus `api_keys`, which has no sketch on this page. Everything else here is ⏳ — a design target, not a table. Four caveats on the shipped twelve:
- **`updated_at` exists on zero tables.** Rows are append-mostly; only `created_at` (and `added_at`/`last_used_at`) is real, so the audit triple above is really a pair today.
- **JSON columns are portable `sa.JSON()`, not `jsonb`.** SQLite is the default (`sqlite:///glowsky.db`) and Postgres 16 appears only in `docker-compose.prod.yml` — so none of the GIN/jsonb indexing in the notes at the bottom is in place, and there is no object storage and no vector store.
- **BYO-LLM secrets are Fernet ciphertext stored in-row** (`llm_provider_credentials.encrypted_secret`) under `GLOWSKY_SECRET_KEY` — not a secrets-manager reference, and with no rotation path.
- **`api_keys` ships but is dead code.** No route, service, or test reads or writes it; identity is delegated entirely to nakitte-carbon-auth JWTs, and Glowsky stores no user credentials.

---

## Identity & tenancy

### User
`id, email, name, orcid?, auth_provider, status, created_at, last_active_at`

### Organization
`id, name, plan (free|pro|team|enterprise), sso_config?, data_residency, settings(jsonb), created_at`
- Personal accounts are modeled as a single-member org for uniformity.

### Membership
`id, org_id, user_id, role (owner|admin|editor|viewer), created_at`
- **Shipped** exactly as written. The other two tables in this spine are thinner than the spec above: `organizations` is `id, name, plan, created_at` and `users` is `id, email (unique, indexed), name?, created_at` — no `orcid`, `auth_provider`, `status`, `last_active_at`, `sso_config`, `data_residency` or `settings`, because carbon-auth owns all of that. All three rows are JIT-provisioned from the token on first sight, and the membership `role` is re-synced from the token's `roles[]` on every request.

---

## BYO-LLM & model config

### LLMProviderCredential
`id, owner_scope (user|org), owner_id, provider (anthropic|openai|xai|google|groq|together|mistral|bedrock|azure|vertex|ollama|vllm|custom), encrypted_secret_ref, base_url?, label, status, created_at`
- Secret stored via a secrets manager; row holds only a **reference**, never plaintext. Never logged.
- **Shipped** as `id, org_id, provider, encrypted_secret, hint, base_url?, label?, status, created_by, created_at`, unique on `(org_id, provider)`. Two departures: there is no secrets manager — `encrypted_secret` is Fernet **ciphertext in-row** under `GLOWSKY_SECRET_KEY` — and the provider set is exactly the four the gateway supports (`anthropic|openai|groq|local`), enforced with a 422 on `POST /settings/credentials`, not the long enum above. The offline `mock` is a keyless gateway fallback, never a stored credential. `hint` is the masked, safe-to-show tail (e.g. `sk-…AB12`); plaintext is still never persisted or logged.

### ModelRoute
`id, owner_scope, owner_id, task_class (reasoning|fast_triage|codegen|embedding|vision), provider_credential_id, model_name, params(jsonb), fallback_route_id?, priority`
- Resolves "which model for this task" at call time; project-level overrides supported.
- **Shipped** as `model_route_overrides` — `id, org_id, task_class, provider, model, created_by, created_at`, unique on `(org_id, task_class)`, absence meaning "fall back to the env-configured default". It is a per-**org** override, not per-project; there are exactly three task classes (`reasoning|fast_triage|codegen` — `codegen` is routable and surfaced in `/health` and `/settings/routes`, but no code path issues a completion with it), and no `params`, `fallback_route_id` or `priority`.

### ModelUsageRecord
`id, org_id, user_id, run_id?, provider, model_name, task_class, input_tokens?, output_tokens?, est_cost?, latency_ms, created_at`

---

## Workspace domain

### Project
`id, org_id, name, description, target_profile(jsonb: goals, constraints), default_model_routes(jsonb?), settings(jsonb), created_by, created_at`
- Container for everything below; carries data-residency + model defaults.
- **Shipped** as `id, org_id, name, description?, target_profile, created_by, created_at` — `default_model_routes` and `settings` are ⏳; model defaults live on the org (`model_route_overrides`), not the project.

### Molecule
`id, org_id, project_id, name?, canonical_smiles, inchikey, mol_block_ref?, properties(jsonb), tags[], status (idea|proposed|synthesized|tested|rejected), source (user|import|generated), origin_run_id?, current_version_id, created_by, created_at`
- `inchikey` indexed for dedup/lookup; `canonical_smiles` always RDKit-canonicalized on write.
- `properties` jsonb holds computed/predicted props, each ideally `{value, predictor, version, confidence}`.
- **Shipped** as `id, org_id, project_id?, name?, canonical_smiles, inchikey, properties, source, origin_run_id?, created_by, created_at`, with `inchikey` and `origin_run_id` indexed. Missing versus the spec: `mol_block_ref` (no object storage), `tags[]`, `status`, and `current_version_id` — there is no versioning, so `properties` is a flat computed-descriptor dict rather than the `{value, predictor, version, confidence}` envelope above.

### MoleculeVersion
`id, molecule_id, version_no, canonical_smiles, mol_block_ref?, properties_snapshot(jsonb), change_summary, parent_version_id?, origin_run_id?, created_by, created_at`
- Enables diff/revert/branch and links each state to the agent run that produced it.

### Library
`id, org_id, project_id, name, description, kind (set|series|virtual_screen), columns_config(jsonb), created_by, created_at`
- **Shipped** exactly as written; `columns_config` holds the per-library grid layout, but no endpoint reads or writes that column yet.

### LibraryMembership
`library_id, molecule_id, added_by, added_at` (join; a molecule can belong to many libraries)
- **Shipped** as written, plus a surrogate `id` primary key rather than a composite `(library_id, molecule_id)` one — duplicate membership is prevented by an app-layer existence check on import, not by a database constraint.

---

## Chemistry artifacts

### Prediction
`id, molecule_id, molecule_version_id, kind (physchem|admet|docking_score|sa_score|custom), name, value(jsonb), predictor_name, predictor_version, confidence?, applicability_domain?, run_id, created_at`
- First-class so predictions are queryable, comparable, and provenance-tracked separately from the molecule blob.

### Structure (macromolecule / target)
`id, org_id, project_id, name, kind (pdb|alphafold|custom), pdb_id?, file_ref, pockets(jsonb?), created_at`

### DockingResult
`id, molecule_version_id, structure_id, engine, engine_version, pocket(jsonb), score, poses_ref (object storage), params(jsonb), run_id, created_at`

### SynthesisRoute
`id, molecule_version_id, provider (aizynth|external|custom), route(jsonb: steps, building_blocks), score, run_id, created_at`

---

## Agent & workflow

### Conversation
`id, project_id, title, created_by, created_at` → **Message** `id, conversation_id, role (user|assistant|tool|system), content(jsonb), attachments(jsonb: @-refs), model_used?, created_at`

### AgentRun
`id, project_id, conversation_id?, goal_text, plan(jsonb: steps/DAG), status (planning|running|paused|done|failed|cancelled), model_routes_used(jsonb), started_at, ended_at`
- The provenance anchor: molecules/predictions/docking link back via `origin_run_id`/`run_id`.
- **Shipped** as `id, org_id, project_id?, goal_text, status, plan, trace, models_used, explanation, created_by, created_at`, plus a viewonly `molecules` relationship joined on `Molecule.origin_run_id`. Differences from the model above: the field is `models_used`, not `model_routes_used`, and it holds only the two resolved `provider/model` route strings `{"reasoning": …, "fast_triage": …}` — no tokens or cost. The status column comments `planning|running|done|failed` and defaults to `"done"`; in practice it is never assigned, so every persisted run is `"done"` — there is no pause or cancel path anywhere in the API. `explanation` (Text) stores the model's final synthesis. `created_at` stands in for `started_at`/`ended_at`, and `conversation_id` does not exist.

### AgentStep / ToolCall
`id, agent_run_id, step_no, tool_name, tool_version, input(jsonb), output_ref/output(jsonb), status, error?, tokens?, duration_ms, created_at`
- Full execution trace → powers transparency UI, debugging, and notebook export.
- **Not yet a table.** No `agent_steps` table exists in the models or the migrations; the step trace is an inline JSON list on `AgentRun.trace`. Each entry is a `ToolCallRecord` (`step, tool, tool_version, compute_class, input, summary, duration_ms, cache_hit, calls`), which projects the tool layer's richer `ExecutionRecord` (`tool, version, compute_class, determinism, env_digest, input_hash, cache_hit, duration_ms, seed, error`) down — dropping `determinism`, `env_digest`, `input_hash`, `seed` and `error`. So `step_no` and `input` already ship as `step`/`input`; what is missing versus the spec above is `agent_run_id` (implicit in the parent row), the full `output` (only a human-readable `summary` is kept), `status`/`error`, and `tokens`. Promoting `trace` to `agent_steps` rows — and restoring the dropped provenance fields plus token counts — is what would make step-level querying and partial replay possible.

### WorkflowTemplate
`id, owner_scope, owner_id, name, description, definition(jsonb: parameterized steps), shared (bool), created_at`

---

## Knowledge & collaboration

### Hypothesis
`id, project_id, statement, status (open|supported|refuted|parked), rationale, created_by, created_at`
### HypothesisLink
`hypothesis_id, entity_type (molecule|prediction|document|run), entity_id, relation (supports|refutes|relates)`

### Document (literature / uploads)
`id, org_id, project_id?, title, source (pubmed|patent|upload), external_id?, file_ref?, metadata(jsonb), created_at`
### DocumentChunk
`id, document_id, chunk_index, text, embedding (vector), metadata(jsonb)` — in/linked to vector store; carries citation locus.

### Comment
`id, entity_type, entity_id, author_id, body, created_at` (polymorphic: molecules, hypotheses, runs, etc.)

### Report
`id, project_id, title, format (md|pdf|ipynb), content_ref, generated_from_run_ids[], created_by, created_at`

### AuditEvent
`id, org_id, actor_id, action, entity_type, entity_id, metadata(jsonb), created_at` — security/compliance trail.
- **Shipped** with the JSON column named `event_metadata` (`metadata` is reserved on a SQLAlchemy declarative class) and `org_id`/`actor_id` as plain strings rather than FKs. Rows are append-only and best-effort — `audit()` never blocks the caller — and nothing reads them back yet: there is no `/audit` route and no export path, so the trail is write-only until one exists.

---

## Extensibility

### CustomTool
`id, owner_scope, owner_id, name, description, schema(jsonb: params/returns), endpoint_url|handler_ref, auth_config_ref, enabled, created_at`
- Registered tools become agent-callable through the tool registry (typed + validated).

### CustomAgent
`id, owner_scope, owner_id, name, system_prompt, allowed_tools[], default_model_route_id?, created_at`

---

## Relationship summary
- `Org 1—* Membership *—1 User`; `Org 1—* Project`.
- `Project 1—* Molecule 1—* MoleculeVersion`; `Molecule *—* Library`. — ⏳ the `MoleculeVersion` leg only: there is no version table, so a molecule is one immutable row today. `Molecule *—* Library` ships as `library_memberships`.
- `MoleculeVersion 1—* Prediction | DockingResult | SynthesisRoute`. — ⏳ none of these four tables exists; predictions live in the molecule's `properties` JSON and docking/route results only in a tool result.
- `Project 1—* Conversation 1—* Message`; `Project 1—* AgentRun 1—* AgentStep` — ⏳ neither leg is shipped: there is no `conversations`/`messages` table, and steps are a JSON list on `AgentRun.trace`, not rows. What does ship is `Project 1—* AgentRun 1—* Molecule` (viewonly, joined on `Molecule.origin_run_id`).
- `AgentRun` is the **provenance hub**: generated molecules/predictions/docking/reports all reference their `run_id`.
- `Project 1—* Hypothesis *—* (molecules|docs|runs)` via `HypothesisLink`.
- `Document 1—* DocumentChunk` (embeddings) powers cited RAG.

## Indexing & storage notes
- Index `inchikey`, `(project_id, status)`, `tags` (GIN), `properties` (GIN/jsonb) for fast library queries.
- Consider RDKit Postgres cartridge for in-DB substructure/similarity at scale; otherwise compute in Chemistry Service + cache.
- Large blobs (mol blocks for big libs, poses, notebooks, PDFs) live in object storage; rows hold `*_ref`.
- Embeddings in pgvector (start) → Qdrant (scale).
