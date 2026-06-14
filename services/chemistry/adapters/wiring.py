"""Select chemistry prediction/engine backends from settings.

Called once at process startup (API lifespan + Celery worker init) so both the
fast path and the slow-path workers resolve the same configured backends. With the
default config ("none"), nothing is wired and the adapter-gated tools keep returning
their honest "not configured" error.
"""
from __future__ import annotations

from services.chemistry.adapters import admet, docking


def configure_backends(settings=None) -> dict:
    """Apply settings.admet_backend / settings.docking_backend. Returns a summary dict."""
    from services.core.config import get_settings

    settings = settings or get_settings()
    summary = {"admet": "not-configured", "docking": "not-configured"}

    if settings.admet_backend == "rdkit":
        from services.chemistry.adapters.admet_rdkit import RDKitQSPRADMET

        backend = RDKitQSPRADMET()
        admet.set_backend(backend)
        summary["admet"] = backend.name

    if settings.docking_backend == "vina":
        from services.chemistry.adapters.vina import VinaDockingBackend

        backend = VinaDockingBackend(vina_bin=settings.vina_bin, obabel_bin=settings.obabel_bin)
        docking.set_backend(backend)
        summary["docking"] = backend.name

    return summary
