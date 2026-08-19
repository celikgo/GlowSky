"""Synthetic accessibility (SA score, Ertl & Schuffenhauer) via RDKit Contrib.

SA score ranges ~1 (easy to make) to ~10 (hard). It is computed from fragment
contributions learned over PubChem plus a molecular-complexity penalty — i.e. from how
COMMON a molecule's pieces are in known chemistry, not from any model of a synthesis.

    Ertl, P. & Schuffenhauer, A. "Estimation of synthetic accessibility score of
    drug-like molecules based on molecular complexity and fragment contributions."
    J. Cheminform. 1(1), 8 (2009).  https://doi.org/10.1186/1758-2946-1-8

WHAT THIS IS NOT
    - Not a route, and not evidence one exists. A score of 2.5 does not mean anybody
      can make the compound; it means its fragments are common. Ask retrosynthesize()
      for the "how", and see docs/VALIDATION.md for what that is and is not.
    - Not a yield, a cost, or a time estimate.
    - Not validated in this repository. Reproducing the published algorithm via RDKit
      Contrib is not the same as reproducing the published RESULT: validating it would
      need the expert-assigned synthesizability rankings the authors scored against.
      Listed as unvalidated in docs/VALIDATION.md.
    - The <=6 threshold is a convention, not a decision boundary anyone derived. A
      compound at 6.1 differs from one at 5.9 by nothing in particular.
"""
from __future__ import annotations

import os
import sys

from rdkit import Chem
from rdkit.Chem import RDConfig

# sascorer ships in RDKit's Contrib tree, not the main namespace.
sys.path.append(os.path.join(RDConfig.RDContribDir, "SA_Score"))
import sascorer

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
