"""Synthetic accessibility (SA score, Ertl & Schuffenhauer) via RDKit Contrib.

SA score ranges ~1 (easy to make) to ~10 (hard). The 'synthesizable' flag uses the
common <=6 heuristic — a triage aid, not a guarantee (docs/12: honest framing)."""
from __future__ import annotations

import os
import sys

from rdkit import Chem
from rdkit.Chem import RDConfig

# sascorer ships in RDKit's Contrib tree, not the main namespace.
sys.path.append(os.path.join(RDConfig.RDContribDir, "SA_Score"))
import sascorer  # noqa: E402

SYNTHESIZABLE_THRESHOLD = 6.0


def sa_score(canonical_smiles: str) -> dict:
    mol = Chem.MolFromSmiles(canonical_smiles)
    if mol is None:
        raise ValueError(f"invalid SMILES: {canonical_smiles!r}")
    score = sascorer.calculateScore(mol)
    return {
        "sa_score": round(score, 3),
        "synthesizable": score <= SYNTHESIZABLE_THRESHOLD,
        "scale": "1 (easy) – 10 (hard); threshold 6.0",
    }
