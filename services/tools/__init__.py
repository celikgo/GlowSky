"""The chemistry tools subsystem (see docs/13-chemistry-tools-architecture.md).

One versioned, typed contract (ToolSpec) describes every tool — built-in or
researcher-contributed. The ToolExecutionService routes each call to the right
backend by compute class, applies the validation firewall, caches deterministic
results, and records provenance. The agent only ever sees the contract.
"""
