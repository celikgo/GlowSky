# Glowsky — Key Technical Risks & Mitigations

Ordered roughly by severity × likelihood. Each: **risk → why it matters → mitigation.**

---

## 1. LLM hallucination of chemistry (correctness/trust) — 🔴 Critical
**Risk:** the model invents invalid SMILES, fake properties, or plausible-but-wrong reasoning. Chemists are expert skeptics; one bad fabricated structure destroys trust permanently.
**Mitigation:**
- **Deterministic firewall:** LLMs *plan and explain*; validated tools *compute*. No LLM-emitted structure is persisted until RDKit canonicalizes/validates it (`chemistry/validation`).
- Always surface **provenance + confidence + applicability domain**; never present predictions as ground truth.
- Show the **plan and tool calls** so users see *how* a result was produced.
- Golden-set **chemistry-correctness test suite**, advisor-reviewed.
- Human-in-the-loop accept/reject for all generated structures.

## 2. BYO-LLM credential & IP security — 🔴 Critical
**Risk:** leaked API keys or proprietary structures = catastrophic, possibly company-ending for us and our customers.
**Mitigation:** KMS-backed secrets manager (refs only in DB), decrypt in-memory only in the Gateway, never log/return keys, redaction middleware, tenant isolation (RLS + app checks), enterprise CMK/BYOK and self-host/VPC. See `07-security-privacy.md`. Third-party pen-tests before enterprise sales.

## 3. Provider fragmentation & capability drift (BYO-LLM) — 🟠 High
**Risk:** providers differ in tool-calling, context windows, streaming, JSON reliability; a local Llama can't do what Claude/GPT can. Agent features may silently break per model.
**Mitigation:** LiteLLM + Gateway abstraction; **capability flags** gate features per model with **graceful degradation**; per-task routing (use a capable model for planning even if a cheap one does triage); robust structured-output handling (schema validation + retries); a curated "recommended models" list; continuous provider-compatibility tests.

## 4. Long-running compute: cost, latency, reliability — 🟠 High
**Risk:** docking, generation, ML inference are slow/expensive/flaky; naive sync design stalls UX and bills explode.
**Mitigation:** async task queue + isolated autoscaling workers from day one; WS streaming progress; aggressive **caching keyed by (input-hash, tool-version)** for deterministic ops; resource quotas per org; retries/timeouts; consider Temporal for durable workflows in Phase 2; cost budgets/limits surfaced to users.

## 5. Scientific credibility of predictions/generation — 🟠 High
**Risk:** open ADMET/docking/generative models can be inaccurate or misapplied; over-promising "AI drug design" invites expert backlash.
**Mitigation:** honest framing (decision-support, with uncertainty), applicability-domain warnings, cite model provenance, let users swap in their own validated models (extensibility), CADD advisor reviews defaults, under-promise in marketing. Position as augmenting the chemist, not replacing judgment.

## 6. Sandboxing & prompt-injection / tool abuse — 🟠 High
**Risk:** untrusted content (uploaded PDFs, RAG sources, registered HTTP tools) hijacks the agent to exfiltrate data or run unintended tools; code-exec escapes isolation.
**Mitigation:** tool allowlisting (typed registry only), no default arbitrary code exec, sandboxed workers (no ambient egress, resource/seccomp limits), treat all retrieved/tool content as untrusted (instruction/data separation), consent + egress allowlist for custom tools, human-in-loop on high-impact actions. See security §5–6.

## 7. Chemistry deployment/dependency complexity — 🟡 Medium
**Risk:** RDKit, docking binaries, ML frameworks (CUDA), conda-heavy deps are painful to containerize and to self-host reproducibly.
**Mitigation:** pin everything; purpose-built worker images (chem deps isolated from the light API image); test self-host images in CI; provide Helm + Compose + air-gapped configs; document GPU/CPU requirements; prefer pip/uv-installable wheels where possible.

## 8. UX complexity — the "Cursor-like" bar is high — 🟡 Medium
**Risk:** delivering true IDE-grade fluidity (instant render, streaming, multi-panel, Cmd+K, diffs) is hard; a clunky UX kills the core promise.
**Mitigation:** client-side RDKit-JS (WASM) for instant 2D validation/depiction; reuse battle-tested libs (Monaco, Mol*, Ketcher, AG Grid); invest in perf budgets (sub-second interactions); design-partner feedback loop; ship the loop narrow-but-polished (Maya) before broad.

## 9. Scope creep / boiling the ocean — 🟡 Medium
**Risk:** chemistry is vast (ADMET, docking, retrosynth, RAG, generative, MPO, FEP…); trying to do all in MVP = ship nothing.
**Mitigation:** ruthless MVP scoping (`08`) — one persona deep, one of each capability; phased roadmap; extensibility deferred until the tool registry is proven; "one engine per capability" rule for MVP.

## 10. Concentrated demand / market & GTM risk — 🟡 Medium
**Risk:** niche audience; academics pay little; enterprises buy slowly and demand security/compliance before adopting.
**Mitigation:** BYO-LLM keeps our cost-to-serve near zero for the free/academic base (bottom-up growth + word-of-mouth); land in academia → expand to teams → enterprise; champion-led (Dr. Chen) enterprise motion; SOC 2 + self-host unlock pharma; clear, defensible value (the loop) rather than feature-matching incumbents.

## 11. Reproducibility/provenance debt — 🟡 Medium
**Risk:** if provenance isn't captured from the start, notebook export and "defensible in DRC" promises fail, and retrofitting is painful.
**Mitigation:** provenance schema in Phase 0 (`run_id` on every artifact; tool/model/params/prompt-hash recorded); notebook export validated against real runs early; trace IDs surfaced in UI.

## 12. Vendor/library longevity & lock-in — 🟢 Lower
**Risk:** dependence on a fast-moving agent framework (LangGraph) or a single provider abstraction (LiteLLM).
**Mitigation:** keep the tool layer framework-agnostic (swap LangGraph if needed); Gateway isolates LiteLLM; everything self-hostable/open so no single managed vendor is load-bearing in the core path.

---

## Risk posture summary
The two existential risks are **chemistry hallucination/trust (#1)** and **credential/IP security (#2)** — both are addressed by core architectural decisions (deterministic firewall; KMS-backed gateway) made in **Phase 0**, not bolted on later. The remaining risks are managed by phasing, abstraction layers, caching/async infra, and a disciplined MVP scope.
