"""Example container tool — molecular formula + exact mass (RDKit).

Demonstrates the Glowsky tool ABI (see services/tools/runtimes/container.py):
read JSON args from stdin, write a single JSON {"ok", "result"|"error"} to stdout.
A researcher's own model/tool follows exactly this shape; Glowsky needs no changes.
"""
import json
import sys

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors


def main() -> None:
    try:
        args = json.load(sys.stdin)
        smiles = args["canonical_smiles"]
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"invalid SMILES: {smiles!r}")
        result = {
            "formula": rdMolDescriptors.CalcMolFormula(mol),
            "exact_mass": round(Descriptors.ExactMolWt(mol), 4),
            "heavy_atoms": mol.GetNumHeavyAtoms(),
        }
        json.dump({"ok": True, "result": result}, sys.stdout)
    except Exception as exc:  # handled failure -> ok:false (ABI contract)
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)


if __name__ == "__main__":
    main()
