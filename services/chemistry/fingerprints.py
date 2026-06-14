"""Molecular fingerprints (RDKit, modern generator API)."""
from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import MACCSkeys, rdFingerprintGenerator

_morgan_gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"invalid SMILES: {smiles!r}")
    return mol


def morgan_bitvect(smiles: str):
    """ECFP4-style 2048-bit Morgan fingerprint (internal object, not serialized)."""
    return _morgan_gen.GetFingerprint(_mol(smiles))


def maccs_bitvect(smiles: str):
    return MACCSkeys.GenMACCSKeys(_mol(smiles))


def fingerprint(canonical_smiles: str, kind: str = "morgan") -> dict:
    """Tool handler: serializable fingerprint summary (on-bit indices)."""
    fp = morgan_bitvect(canonical_smiles) if kind == "morgan" else maccs_bitvect(canonical_smiles)
    on_bits = list(fp.GetOnBits())
    return {"kind": kind, "n_bits": fp.GetNumBits(), "on_bits": on_bits, "count": len(on_bits)}
