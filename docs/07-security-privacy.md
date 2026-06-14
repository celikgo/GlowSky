# Glowsky — Security & Privacy Considerations

Security is existential here: customers entrust us with (a) **LLM provider credentials** and (b) **proprietary research data / IP** that can be worth hundreds of millions. The architecture treats security as a first-order concern.

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
- **Never store plaintext keys.** Keys go to a dedicated secrets manager (cloud KMS-backed: AWS Secrets Manager / Vault). DB stores only an opaque reference + metadata.
- **Envelope encryption**, per-tenant data keys, key rotation. At-rest encryption everywhere.
- **Decrypt only in-memory, only at call time**, only in the LLM Gateway. Keys are **never logged**, never returned to the client after entry, never placed in traces or error messages (explicit redaction middleware).
- **Scope & least privilege:** user-scoped vs org-scoped credentials; RBAC controls who can add/use/rotate.
- **Egress control:** outbound LLM calls go only to the configured provider endpoints; allowlist; optional egress proxy logging (metadata only) for enterprise.
- **Bring-your-own-everything for enterprise:** customer can point at their own Bedrock/Azure/Vertex/local endpoint so keys/data never leave their boundary.

---

## 3. Research data & IP protection
- **Tenant isolation:** every domain row carries `org_id`; enforced via row-level security (Postgres RLS) + app-layer checks. Self-hosted = single tenant by construction.
- **Data residency:** SaaS regional selection (e.g., EU-only); enterprise self-host/VPC for full control; air-gapped mode (local LLM + no external literature calls).
- **Encryption:** TLS 1.2+ in transit; AES-256 at rest (DB, object storage, backups). Per-tenant encryption keys where feasible.
- **What we send to LLM providers:** make it explicit and controllable. Users see/route which provider receives which data. Default to **no training on customer data** providers (e.g., enterprise endpoints, zero-retention modes) and surface each provider's retention policy. Warn clearly when a chosen provider may retain/train.
- **Minimize what leaves the deterministic core:** chemistry compute is local; only the text/context the agent needs goes to the LLM — not entire libraries by default.
- **No silent telemetry of content.** Product telemetry is metadata/usage only; customer structures/sequences are never in analytics. Opt-in for any content-bearing diagnostics.

---

## 4. Operator / insider controls
- **Least-privilege staff access**, just-in-time elevation, audited. Production data access requires approval + logging.
- **No standing access to secrets.** Engineers cannot read tenant keys; the secrets manager enforces this.
- **Customer-managed keys (CMK/BYOK)** option for enterprise so even we can't decrypt at rest.
- Full **audit log** (`AuditEvent`) of access and admin actions; exportable for enterprise.

---

## 5. Prompt injection & agent safety
- **Tool allowlisting:** the agent acts only through the typed tool registry. No arbitrary actions.
- **No default arbitrary code execution.** Code/notebook execution is opt-in, sandboxed (see §6), and never auto-invoked from untrusted content.
- **Treat RAG/document/tool content as untrusted:** the orchestrator separates instructions from data, constrains tool args by schema, and applies guardrails on high-impact actions (e.g., calling a custom HTTP tool that egresses data → requires explicit user/registration trust).
- **Human-in-the-loop for mutations:** generated molecules/edits are proposals (accept/reject), not silent writes.
- **Output validation:** every LLM-emitted structure is canonicalized/validated by RDKit; invalid → rejected, never persisted as truth.
- **Confused-deputy protection for custom tools:** registered HTTP tools run with declared scopes/auth; data sent to them is shown/consented; egress allowlist applies.

---

## 6. Compute & code sandboxing
- Heavy/code workers run in **isolated containers** with: CPU/mem/time limits, read-only base FS, **no ambient network egress** (code-exec sandbox), dropped capabilities, seccomp.
- One-shot, ephemeral execution environments per job; no shared mutable state.
- Resource quotas per org to prevent abuse/DoS.

---

## 7. Application & platform security
- **AuthN:** OAuth/OIDC (Google/GitHub/ORCID), email; **SSO/SAML/SCIM** for enterprise. MFA support.
- **AuthZ:** RBAC (owner/admin/editor/viewer) + project-level sharing; enforced server-side on every request.
- **Session security:** short-lived tokens, refresh rotation, secure cookies.
- **Input validation & limits:** schema-validate all API input; file-type/size limits; malware scan on uploads; rate-limiting per tenant/user.
- **Secrets hygiene:** no secrets in code/repo; scanning in CI; rotated.
- **Dependency/supply-chain:** SCA scanning, pinned deps, SBOM, signed images, regular patching.
- **SAST/DAST** in CI; periodic third-party pen-tests.

---

## 8. Privacy & data lifecycle
- **Data ownership:** customers own their data and IP; we are processors. Clear DPA.
- **Deletion & export:** full export (molecules, data, reports) and hard-delete on request; defined retention; backup expiry honored.
- **Minimization & purpose limitation:** collect only what's needed; content excluded from analytics/training.
- **Sub-processor transparency:** list LLM/infra sub-processors; let enterprises restrict to chosen providers/regions.

---

## 9. Compliance posture (roadmap)
- **Target SOC 2 Type II** as the early enterprise gate; **GDPR** (EU residency, DPA, DSRs) from the start of EU sales.
- **HIPAA** generally N/A (no PHI) but assess if any customer data implicates it.
- **Patent/FTO disclaimer:** literature/IP features are decision-support, **not legal advice**; clearly labeled to avoid liability and set expectations.
- Self-host docs + Helm hardening guide so enterprises can meet their own controls.

---

## 10. Security non-negotiables for MVP
Even in MVP, these ship from day one:
1. Encrypted, KMS-backed key storage; keys never logged/returned.
2. Tenant isolation (org scoping + RLS).
3. TLS + at-rest encryption.
4. Server-side authz on every endpoint.
5. Sandboxed workers; no default arbitrary code exec.
6. RDKit validation of all LLM-emitted structures.
7. Audit logging of sensitive actions.
Everything else (SSO/SAML, SOC 2, CMK, air-gap) layers on for Team/Enterprise.
