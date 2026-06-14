"""ADMET prediction adapter (docs/13 §10 property tools).

The contract a predictor backend must satisfy. Real backends (e.g. ADMET-AI,
DeepChem models, or a lab's own model registered as a container tool) implement
predict(); we never invent values. Predictions always carry confidence /
applicability-domain so the UI can show honest uncertainty (docs/12 #5).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from services.chemistry.adapters import BackendNotConfigured

# Endpoints a backend may support. Backends declare which they cover.
DEFAULT_ENDPOINTS = ["solubility", "logd", "herg", "cyp3a4", "metabolic_stability"]


@runtime_checkable
class ADMETBackend(Protocol):
    name: str
    endpoints: list[str]

    def predict(self, canonical_smiles: str, endpoints: list[str]) -> dict: ...


class NotConfiguredADMET:
    """Default backend: refuses to guess. Swap for a real model to enable the tool."""

    name = "not-configured"
    endpoints: list[str] = []

    def predict(self, canonical_smiles: str, endpoints: list[str]) -> dict:
        raise BackendNotConfigured(
            "ADMET predictor backend not configured. Register an ADMETBackend "
            "(e.g. ADMET-AI, or your own model as a container tool) — see docs/13 §6/§10. "
            "Glowsky never fabricates ADMET values."
        )


# Module-level backend; replaced via set_backend() when a real model is available.
_backend: ADMETBackend = NotConfiguredADMET()


def set_backend(backend: ADMETBackend) -> None:
    global _backend
    _backend = backend


def predict_admet(canonical_smiles: str, endpoints: list[str] | None = None) -> dict:
    """Tool handler. Returns {endpoint: {value, confidence, applicability_domain}}."""
    eps = endpoints or DEFAULT_ENDPOINTS
    result = _backend.predict(canonical_smiles, eps)
    return {"backend": _backend.name, "predictions": result}
