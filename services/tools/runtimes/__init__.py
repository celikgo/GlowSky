"""Tool runtimes (docs/13 §6): how a tool's handler is actually executed.

  • BUILTIN     — in-process Python (core tools + trusted self-host plugins)
  • CONTAINER   — sandboxed Docker image (bring-your-own model)   <-- this module set
  • REMOTE_HTTP — registered endpoint                            [Phase 3]

A container tool is registered (from a manifest) with a handler that delegates to
ContainerRuntime, so the executor — cache, firewall, provenance — treats it exactly
like any other tool. The contract is uniform; only isolation differs.
"""
