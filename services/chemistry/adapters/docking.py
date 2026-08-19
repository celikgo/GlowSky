"""Molecular docking adapter (docs/13 §10 structure-based).

Wraps a docking engine (AutoDock Vina / smina / gnina). Phase 0 ships the contract
and an honest "not configured" default — we never invent docking scores or poses.
Wiring a real engine (a binary, or a researcher's container/remote tool) enables the
slow-path tool that already has its ToolSpec + GPU/LONG routing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from services.chemistry.adapters import BackendNotConfigured


@dataclass(frozen=True)
class Pocket:
    center: tuple[float, float, float]
    size: tuple[float, float, float]


@runtime_checkable
class DockingBackend(Protocol):
    @property
    def name(self) -> str: ...

    def dock(self, ligand_smiles: str, receptor_ref: str, pocket: Pocket) -> dict: ...


class NotConfiguredDocking:
    name = "not-configured"

    def dock(self, ligand_smiles: str, receptor_ref: str, pocket: Pocket) -> dict:
        raise BackendNotConfigured(
            "Docking backend not configured. Register a DockingBackend "
            "(AutoDock Vina/smina/gnina, or your own engine as a container tool) — "
            "see docs/13 §6/§10. Glowsky never fabricates docking results."
        )


_backend: DockingBackend = NotConfiguredDocking()


def set_backend(backend: DockingBackend) -> None:
    # See admet.set_backend: one process-wide engine, wired once at startup.
    global _backend  # noqa: PLW0603
    _backend = backend


def dock(
    ligand_smiles: str,
    receptor_ref: str,
    center: list[float],
    size: list[float],
) -> dict:
    """Tool handler. Returns {engine, score, poses_ref, ...} from the real backend."""
    pocket = Pocket(center=tuple(center), size=tuple(size))  # type: ignore[arg-type]
    result = _backend.dock(ligand_smiles, receptor_ref, pocket)
    return {"engine": _backend.name, **result}
