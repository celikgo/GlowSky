"""Pluggable adapters for heavy/external predictors (ADMET) and engines (docking).

These define the integration SEAM (docs/13 §6, §10). Phase 0 ships the contract and
an honest "not configured" default — we never fabricate ADMET values or docking
scores. A real backend (an ML model, a Vina binary, a researcher's container tool)
is wired in by registering an implementation; the ToolSpec and routing already exist.
"""


class BackendNotConfigured(RuntimeError):
    """Raised when a tool's compute backend (model/engine) is not installed/configured."""
