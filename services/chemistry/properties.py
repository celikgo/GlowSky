"""Physicochemical descriptors, druglikeness rules, and structural alerts (RDKit).

All values are deterministic and computed locally — no LLM involved. ADMET/ML
predictors plug in alongside these in Phase 1 (services.chemistry.prediction).
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
