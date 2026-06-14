"""The deterministic firewall.

Every structure that enters Glowsky — typed by a user, imported, or emitted by an
LLM — passes through validate_and_canonicalize() before it is trusted, displayed,
or persisted. This is the single most important guard against LLM hallucination
(see docs/12-risks.md #1).
"""
from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem, RDLogger
from rdkit.Chem.MolStandardize import rdMolStandardize

# RDKit is chatty on stderr for bad input; we surface errors via our own result type.
RDLogger.DisableLog("rdApp.*")

_uncharger = rdMolStandardize.Uncharger()
_lfc = rdMolStandardize.LargestFragmentChooser()


@dataclass(frozen=True)
class ValidationResult:
    input: str
    valid: bool
    canonical_smiles: str | None = None
    inchikey: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "input": self.input,
            "valid": self.valid,
            "canonical_smiles": self.canonical_smiles,
            "inchikey": self.inchikey,
            "error": self.error,
        }


def _standardize(mol: Chem.Mol) -> Chem.Mol:
    """Salt strip -> largest fragment -> neutralize. Conservative, deterministic."""
    mol = _lfc.choose(mol)
    mol = _uncharger.uncharge(mol)
    Chem.SanitizeMol(mol)
    return mol


def validate_and_canonicalize(smiles: str, *, standardize: bool = True) -> ValidationResult:
    """Parse, sanitize, (optionally) standardize, and canonicalize a SMILES string.

    Returns a ValidationResult — never raises on bad chemistry. Invalid input yields
    valid=False with a human-readable error, and is never persisted as truth.
    """
    if not smiles or not smiles.strip():
        return ValidationResult(input=smiles, valid=False, error="empty input")

    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        return ValidationResult(input=smiles, valid=False, error="unparseable SMILES")

    try:
        if standardize:
            mol = _standardize(mol)
        canonical = Chem.MolToSmiles(mol)
        inchikey = Chem.MolToInchiKey(mol)
    except Exception as exc:  # RDKit can raise on edge-case structures
        return ValidationResult(input=smiles, valid=False, error=f"sanitization failed: {exc}")

    if not canonical:
        return ValidationResult(input=smiles, valid=False, error="produced empty structure")

    return ValidationResult(
        input=smiles, valid=True, canonical_smiles=canonical, inchikey=inchikey
    )
