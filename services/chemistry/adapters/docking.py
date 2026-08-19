"""Molecular docking adapter (docs/13 §10 structure-based).

Wraps a docking engine (AutoDock Vina / smina / gnina). Phase 0 ships the contract
and an honest "not configured" default — we never invent docking scores or poses.
Wiring a real engine (a binary, or a researcher's container/remote tool) enables the
slow-path tool that already has its ToolSpec + GPU/LONG routing.

Results come back as a `Prediction` (services/chemistry/provenance.py), so a docking
score carries its applicability domain, its spread and its provenance rather than
arriving as a bare number in kcal/mol that reads like a measurement.

The uncertainty attached here is the spread across the poses THIS run returned — a real,
computed ensemble spread, not a quoted constant. Read what it means carefully: it
describes how much the search disagreed with itself, and nothing else. The error of the
scoring function against measured binding affinity is a different and much larger
quantity, and this repository has not measured it (docs/VALIDATION.md measures pose
geometry, via re-docking RMSD, not affinity).

WHAT THIS IS NOT
----------------
A docking score is NOT a binding affinity. It is the value of an empirical scoring
function at the best pose the search found — a number designed to RANK candidate poses
and ligands, tuned on crystallographic complexes. Converting it to a Kd, a Ki, an IC50 or
a ΔG is not supported by anything in this module, and the literature on docking score /
affinity correlation for a single target is not encouraging. Nothing here is a
measurement, a selectivity claim, or a safety or regulatory assessment. Use it to decide
what to look at next.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from services.chemistry.adapters import BackendNotConfigured
from services.chemistry.provenance import (
    CITE_VINA_2010,
    CITE_VINA_2021,
    ApplicabilityDomain,
    Domain,
    ModelKind,
    Prediction,
    Provenance,
    Uncertainty,
    UncertaintyBasis,
)


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


#: Vina's search degrades as ligand flexibility rises; beyond roughly this many
#: rotatable bonds the returned pose is not reliable at default exhaustiveness.
_MAX_ROTATABLE_BONDS = 10
#: The scoring function was parameterised on drug-like complexes from the PDBbind set.
_MAX_HEAVY_ATOMS = 60
_MIN_HEAVY_ATOMS = 6
#: A search box smaller than the ligand cannot contain a valid pose.
_MIN_BOX_ANGSTROM = 10.0

#: Elements the Vina force field assigns types to. A ligand containing anything else is
#: scored with whatever the engine falls back to, which is not a modelled interaction.
_VINA_ELEMENTS = frozenset(
    ["H", "C", "N", "O", "F", "P", "S", "Cl", "Br", "I", "Fe", "Zn", "Mg", "Mn", "Ca"]
)


def _ligand_domain(ligand_smiles: str, size: list[float]) -> ApplicabilityDomain:
    """Applicability of a docking run, judged from the ligand and the search box.

    RDKit is imported here rather than at module scope: this module is the contract seam
    and is imported even in deployments where no docking engine is wired.
    """
    checks = {"search_box_at_least_10A": all(float(s) >= _MIN_BOX_ANGSTROM for s in size)}
    try:
        from rdkit import Chem
        from rdkit.Chem import rdMolDescriptors

        mol = Chem.MolFromSmiles(ligand_smiles)
    except ImportError:  # pragma: no cover - RDKit is a hard dependency in practice
        return ApplicabilityDomain.not_defined(
            "RDKit unavailable, so ligand-side applicability was not assessed"
        )
    if mol is None:
        return ApplicabilityDomain.not_defined(
            f"ligand SMILES could not be parsed ({ligand_smiles!r}), so applicability "
            "was not assessed"
        )
    heavy = mol.GetNumHeavyAtoms()
    checks.update(
        {
            "rotatable_bonds_le_10": rdMolDescriptors.CalcNumRotatableBonds(mol)
            <= _MAX_ROTATABLE_BONDS,
            "heavy_atoms_in_range": _MIN_HEAVY_ATOMS <= heavy <= _MAX_HEAVY_ATOMS,
            "elements_typed_by_force_field": {a.GetSymbol() for a in mol.GetAtoms()}
            <= _VINA_ELEMENTS,
        }
    )
    return ApplicabilityDomain.from_checks(checks)


def _pose_spread(poses: list[dict]) -> Uncertainty:
    """Spread across the affinities this run returned.

    One pose is not a converged answer and is not evidence of confidence — it is a search
    that returned a single mode — so a lone pose reports no sigma rather than a sigma of
    zero, which would read as certainty.
    """
    affinities = [
        float(p["affinity"])
        for p in poses
        if isinstance(p, dict) and p.get("affinity") is not None
    ]
    shared = (
        "spread of the scoring function across the poses returned by this run. It "
        "measures how much the search disagreed with itself, NOT the error of the "
        "scoring function against measured binding affinity, which is larger and is not "
        "measured in this repository"
    )
    if len(affinities) < 2:
        return Uncertainty(
            basis=UncertaintyBasis.ENSEMBLE_SPREAD,
            source=f"only {len(affinities)} pose returned, so no {shared}",
        )
    return Uncertainty(
        basis=UncertaintyBasis.ENSEMBLE_SPREAD,
        sigma=statistics.stdev(affinities),
        interval=(min(affinities), max(affinities)),
        interval_level=1.0,
        source=(
            f"{shared}; interval is the full range over {len(affinities)} poses, not a "
            "confidence interval"
        ),
    )


def dock(
    ligand_smiles: str,
    receptor_ref: str,
    center: list[float],
    size: list[float],
) -> dict:
    """Tool handler. Returns the engine result plus the Prediction envelope.

    The backend's own keys (score, poses, best_pose_pdbqt, ...) are preserved so pose
    viewers and existing callers keep working; `value` is the same number as `score`.
    """
    pocket = Pocket(center=tuple(center), size=tuple(size))  # type: ignore[arg-type]
    result = _backend.dock(ligand_smiles, receptor_ref, pocket)

    poses = result.get("poses") or []
    domain = _ligand_domain(ligand_smiles, size)
    prediction = Prediction(
        value=result.get("score"),
        unit=result.get("score_unit", "kcal/mol"),
        uncertainty=_pose_spread(poses),
        applicability=domain,
        provenance=Provenance(
            model=_backend.name,
            kind=ModelKind.PHYSICS_ENGINE,
            version=str(result.get("engine_version", "unreported by engine")),
            trained_on=(
                "empirical scoring function with weights fitted to crystallographic "
                "protein-ligand complexes with measured affinities (PDBbind); the search "
                "itself is stochastic and seeded"
            ),
            citations=(CITE_VINA_2010, CITE_VINA_2021),
            notes=(
                "A docking score is not a binding affinity and must not be converted to "
                "one. It ranks poses and ligands against the same receptor; comparing "
                "scores across different receptors is not meaningful. Re-docking pose "
                "accuracy for this pipeline is measured in docs/VALIDATION.md; the "
                "accuracy of the SCORE against measured affinity is not measured there "
                "and is not claimed here"
            ),
        ),
        caveat=(
            "docking score, not a binding affinity — a ranking quantity for this receptor"
            if domain.verdict is not Domain.OUT
            else None
        ),
    )
    return {"engine": _backend.name, **result, **prediction.as_dict()}
