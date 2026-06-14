"""Tanimoto similarity — single pair and bulk (batchable)."""
from __future__ import annotations

from rdkit import DataStructs

from services.chemistry.fingerprints import morgan_bitvect


def tanimoto(smiles_a: str, smiles_b: str) -> dict:
    sim = DataStructs.TanimotoSimilarity(morgan_bitvect(smiles_a), morgan_bitvect(smiles_b))
    return {"similarity": round(sim, 4)}


def bulk_similarity(query_smiles: str, smiles_list: list[str], top_k: int | None = None) -> dict:
    """Rank a set of molecules by Tanimoto similarity to a query. Batchable tool."""
    query_fp = morgan_bitvect(query_smiles)
    scored: list[dict] = []
    for smi in smiles_list:
        try:
            sim = DataStructs.TanimotoSimilarity(query_fp, morgan_bitvect(smi))
        except ValueError:
            continue  # skip unparseable members; never fabricate
        scored.append({"smiles": smi, "similarity": round(sim, 4)})
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    if top_k:
        scored = scored[:top_k]
    return {"query": query_smiles, "results": scored}
