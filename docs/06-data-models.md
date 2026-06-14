# Glowsky — Data Models (high level)

Conceptual model, not final DDL. Postgres is the system of record; JSONB used for flexible/extensible attributes; object storage holds large artifacts (SDF, PDB, notebooks, reports); vector store holds embeddings. IDs are UUIDs. Most domain rows carry `org_id` for tenant scoping + audit fields (`created_at`, `updated_at`, `created_by`).

---

## Identity & tenancy

### User
`id, email, name, orcid?, auth_provider, status, created_at, last_active_at`

### Organization
`id, name, plan (free|pro|team|enterprise), sso_config?, data_residency, settings(jsonb), created_at`
- Personal accounts are modeled as a single-member org for uniformity.

### Membership
`id, org_id, user_id, role (owner|admin|editor|viewer), created_at`

---

## BYO-LLM & model config

### LLMProviderCredential
`id, owner_scope (user|org), owner_id, provider (anthropic|openai|xai|google|groq|together|mistral|bedrock|azure|vertex|ollama|vllm|custom), encrypted_secret_ref, base_url?, label, status, created_at`
- Secret stored via a secrets manager; row holds only a **reference**, never plaintext. Never logged.

### ModelRoute
`id, owner_scope, owner_id, task_class (reasoning|fast_triage|codegen|embedding|vision), provider_credential_id, model_name, params(jsonb), fallback_route_id?, priority`
- Resolves "which model for this task" at call time; project-level overrides supported.

### ModelUsageRecord
`id, org_id, user_id, run_id?, provider, model_name, task_class, input_tokens?, output_tokens?, est_cost?, latency_ms, created_at`

---

## Workspace domain

### Project
`id, org_id, name, description, target_profile(jsonb: goals, constraints), default_model_routes(jsonb?), settings(jsonb), created_by, created_at`
- Container for everything below; carries data-residency + model defaults.

### Molecule
`id, org_id, project_id, name?, canonical_smiles, inchikey, mol_block_ref?, properties(jsonb), tags[], status (idea|proposed|synthesized|tested|rejected), source (user|import|generated), origin_run_id?, current_version_id, created_by, created_at`
- `inchikey` indexed for dedup/lookup; `canonical_smiles` always RDKit-canonicalized on write.
- `properties` jsonb holds computed/predicted props, each ideally `{value, predictor, version, confidence}`.

### MoleculeVersion
`id, molecule_id, version_no, canonical_smiles, mol_block_ref?, properties_snapshot(jsonb), change_summary, parent_version_id?, origin_run_id?, created_by, created_at`
- Enables diff/revert/branch and links each state to the agent run that produced it.

### Library
`id, org_id, project_id, name, description, type (set|series|virtual_screen), columns_config(jsonb), created_at`

### LibraryMembership
`library_id, molecule_id, added_by, added_at` (join; a molecule can belong to many libraries)

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

### AgentStep / ToolCall
`id, agent_run_id, step_no, tool_name, tool_version, input(jsonb), output_ref/output(jsonb), status, error?, tokens?, duration_ms, created_at`
- Full execution trace → powers transparency UI, debugging, and notebook export.

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
- `Project 1—* Molecule 1—* MoleculeVersion`; `Molecule *—* Library`.
- `MoleculeVersion 1—* Prediction | DockingResult | SynthesisRoute`.
- `Project 1—* Conversation 1—* Message`; `Project 1—* AgentRun 1—* AgentStep`.
- `AgentRun` is the **provenance hub**: generated molecules/predictions/docking/reports all reference their `run_id`.
- `Project 1—* Hypothesis *—* (molecules|docs|runs)` via `HypothesisLink`.
- `Document 1—* DocumentChunk` (embeddings) powers cited RAG.

## Indexing & storage notes
- Index `inchikey`, `(project_id, status)`, `tags` (GIN), `properties` (GIN/jsonb) for fast library queries.
- Consider RDKit Postgres cartridge for in-DB substructure/similarity at scale; otherwise compute in Chemistry Service + cache.
- Large blobs (mol blocks for big libs, poses, notebooks, PDFs) live in object storage; rows hold `*_ref`.
- Embeddings in pgvector (start) → Qdrant (scale).
