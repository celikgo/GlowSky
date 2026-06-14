"""Substructure / SMARTS search over a provided set of molecules (batchable)."""
from __future__ import annotations

from rdkit import Chem


def substructure_search(query_smarts: str, smiles_list: list[str]) -> dict:
    pattern = Chem.MolFromSmarts(query_smarts)
    if pattern is None:
        raise ValueError(f"invalid SMARTS pattern: {query_smarts!r}")
    matches: list[str] = []
    for smi in smiles_list:
        mol = Chem.MolFromSmiles(smi)
        if mol is not None and mol.HasSubstructMatch(pattern):
            matches.append(smi)
    return {"query": query_smarts, "matched": matches, "n_matched": len(matches),
            "n_searched": len(smiles_list)}
