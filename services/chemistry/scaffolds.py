"""Bemis–Murcko scaffold extraction."""
from __future__ import annotations

from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold


def murcko_scaffold(canonical_smiles: str) -> dict:
    mol = Chem.MolFromSmiles(canonical_smiles)
    if mol is None:
        raise ValueError(f"invalid SMILES: {canonical_smiles!r}")
    scaffold = MurckoScaffold.GetScaffoldForMol(mol)
    generic = MurckoScaffold.MakeScaffoldGeneric(scaffold)
    return {
        "scaffold": Chem.MolToSmiles(scaffold),
        "generic_scaffold": Chem.MolToSmiles(generic),
    }
