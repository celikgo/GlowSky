"""Physicochemical descriptors, druglikeness rules, and structural alerts (RDKit).

All values are deterministic and computed locally — no LLM involved. ADMET/ML
predictors plug in alongside these in Phase 1 (services.chemistry.prediction).

These are the only numbers in Glowsky that are EXACT for a given structure, which is
why they carry no uncertainty band: MW, HBD/HBA counts, ring counts and heavy-atom
counts are properties of the graph, and two correct implementations must agree.

Three values here are not in that category and are worth naming:
    logp    Crippen's atomic-contribution estimate, a MODEL of octanol/water
            partitioning, not a measurement.  https://doi.org/10.1021/ci990307l
    tpsa    Ertl's fragment-based polar surface area — a fast surrogate for the 3D
            quantity, not the 3D quantity.     https://doi.org/10.1021/jm000942e
    qed     Bickerton's desirability aggregate, which encodes a preference in the same
            way MPO does.                      https://doi.org/10.1038/nchem.1243

WHAT THIS IS NOT
    - The alerts are not toxicity predictions. PAINS (https://doi.org/10.1021/jm901137j)
      flags substructures associated with ASSAY INTERFERENCE — compounds that produce
      false positives in screens — and BRENK (https://doi.org/10.1002/cmdc.200700139)
      flags groups undesirable in a screening library. A PAINS match is a reason to
      check the assay readout, not evidence a compound is toxic, and a clean result is
      not evidence it is safe.
    - Both catalogues were derived in specific screening contexts and are known to fire
      on legitimate chemistry; several marketed drugs match a PAINS pattern.
    - druglikeness() reports rule outcomes, not probabilities of success. See
      services/chemistry/medchem.py for what those rules are and are not.
"""
from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import QED, Crippen, Descriptors, rdMolDescriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

# Build alert catalogs once at import (cheap, reused across calls).
_pains_params = FilterCatalogParams()
_pains_params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
_pains_catalog = FilterCatalog(_pains_params)

_brenk_params = FilterCatalogParams()
_brenk_params.AddCatalog(FilterCatalogParams.FilterCatalogs.BRENK)
_brenk_catalog = FilterCatalog(_brenk_params)


def compute_descriptors(canonical_smiles: str) -> dict:
    """Compute core physicochemical descriptors. Assumes a pre-validated SMILES."""
    mol = Chem.MolFromSmiles(canonical_smiles)
    if mol is None:
        raise ValueError(f"compute_descriptors received invalid SMILES: {canonical_smiles!r}")

    return {
        "mw": round(Descriptors.MolWt(mol), 2),
        "logp": round(Crippen.MolLogP(mol), 2),
        "tpsa": round(rdMolDescriptors.CalcTPSA(mol), 2),
        "hbd": rdMolDescriptors.CalcNumHBD(mol),
        "hba": rdMolDescriptors.CalcNumHBA(mol),
        "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(mol),
        "aromatic_rings": rdMolDescriptors.CalcNumAromaticRings(mol),
        "fsp3": round(rdMolDescriptors.CalcFractionCSP3(mol), 3),
        "qed": round(QED.qed(mol), 3),
        "heavy_atoms": mol.GetNumHeavyAtoms(),
    }


def druglikeness(descriptors: dict) -> dict:
    """Lipinski Ro5 and Veber rule checks from a descriptor dict."""
    lipinski_violations = sum(
        [
            descriptors["mw"] > 500,
            descriptors["logp"] > 5,
            descriptors["hbd"] > 5,
            descriptors["hba"] > 10,
        ]
    )
    veber_pass = descriptors["rotatable_bonds"] <= 10 and descriptors["tpsa"] <= 140
    return {
        "lipinski_violations": lipinski_violations,
        "lipinski_pass": lipinski_violations <= 1,
        "veber_pass": veber_pass,
    }


def structural_alerts(canonical_smiles: str) -> dict:
    """Flag PAINS and BRENK substructures. Returns matched descriptions (may be empty)."""
    mol = Chem.MolFromSmiles(canonical_smiles)
    if mol is None:
        raise ValueError(f"structural_alerts received invalid SMILES: {canonical_smiles!r}")
    pains = [m.GetDescription() for m in _pains_catalog.GetMatches(mol)]
    brenk = [m.GetDescription() for m in _brenk_catalog.GetMatches(mol)]
    return {
        "pains": pains,
        "has_pains": len(pains) > 0,
        "brenk": brenk,
        "has_brenk": len(brenk) > 0,
    }


def profile(canonical_smiles: str) -> dict:
    """Full deterministic profile: descriptors + druglikeness + alerts."""
    desc = compute_descriptors(canonical_smiles)
    return {**desc, **druglikeness(desc), **structural_alerts(canonical_smiles)}
