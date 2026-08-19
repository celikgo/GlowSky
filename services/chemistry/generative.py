"""Deterministic analog enumeration (Phase 0).

This is a real, validated R-group enumeration: a curated set of common medicinal-
chemistry substituents is attached at open aromatic/aliphatic C-H positions via
RDKit reaction SMARTS. Every product is sanitized, canonicalized, validated, and
de-duplicated by InChIKey. No ML/LLM generates structures here — the LLM only
chooses parameters (count, constraints); the chemistry is deterministic.

Phase 1 swaps/augments this with scaffold hopping, bioisosteres, and an ML
generative model (REINVENT-class) behind the same tool interface.

WHAT THIS IS NOT
    - Not a claim that any product is synthesizable, active, or novel. Enumeration
      asks "what structures can I write", which is a different question from all three.
      Score the outputs (sa_score, mpo_score, medchem_rules) before treating any of
      them as a suggestion.
    - Not exhaustive, and not a designed set. The substituent list is curated by hand;
      what comes out reflects what is in that list and nothing about what would be
      good here.
    - The structures ARE guaranteed valid: every product is sanitized, canonicalized
      and put through the validation firewall, and anything that fails is dropped. That
      is the one guarantee this module makes, and it is a guarantee about chemistry
      being well-formed, not about it being useful.
"""
from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from services.chemistry.validation import validate_and_canonicalize

# Common substituents -> reaction templates replacing one ring C-H (aromatic) or
# a terminal methyl C-H (aliphatic fallback). Keys are human-readable labels.
_AROMATIC_SUBSTITUENTS = {
    "F": "[cH:1]>>[c:1]F",
    "Cl": "[cH:1]>>[c:1]Cl",
    "Me": "[cH:1]>>[c:1]C",
    "OMe": "[cH:1]>>[c:1]OC",
    "OH": "[cH:1]>>[c:1]O",
    "NH2": "[cH:1]>>[c:1]N",
    "CN": "[cH:1]>>[c:1]C#N",
    "CF3": "[cH:1]>>[c:1]C(F)(F)F",
}
_ALIPHATIC_SUBSTITUENTS = {
    "F(alkyl)": "[CH3:1]>>[CH2:1]F",
    "OH(alkyl)": "[CH3:1]>>[CH2:1]O",
}

_AROMATIC_RXNS = {k: AllChem.ReactionFromSmarts(v) for k, v in _AROMATIC_SUBSTITUENTS.items()}
_ALIPHATIC_RXNS = {k: AllChem.ReactionFromSmarts(v) for k, v in _ALIPHATIC_SUBSTITUENTS.items()}


def _apply(rxns: dict, mol: Chem.Mol) -> list[tuple[str, str]]:
    """Run each reaction, return (label, canonical_smiles) for valid, unique products."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, rxn in rxns.items():
        for products in rxn.RunReactants((mol,)):
            product = products[0]
            try:
                Chem.SanitizeMol(product)
            except Exception:  # noqa: BLE001,S112 - see bioisosteres._apply: an unsanitizable
                # reaction product is discarded by design, and RDKit's sanitization errors do
                # not share a single catchable base class.
                continue
            result = validate_and_canonicalize(Chem.MolToSmiles(product))
            if result.valid and result.key not in seen:
                seen.add(result.key)
                out.append((label, result.smiles))
    return out


def generate_analogs(canonical_smiles: str, *, max_analogs: int = 20) -> list[dict]:
    """Enumerate validated analogs of a pre-validated parent molecule.

    Returns a list of {smiles, inchikey, modification} dicts, de-duplicated and
    excluding the parent. Capped at max_analogs.
    """
    parent = validate_and_canonicalize(canonical_smiles)
    if not parent.valid:
        raise ValueError(f"generate_analogs received invalid parent: {parent.error}")

    mol = Chem.MolFromSmiles(parent.canonical_smiles)
    candidates = _apply(_AROMATIC_RXNS, mol)
    if not candidates:  # no aromatic C-H -> aliphatic fallback
        candidates = _apply(_ALIPHATIC_RXNS, mol)

    analogs: list[dict] = []
    seen = {parent.inchikey}
    for label, smiles in candidates:
        result = validate_and_canonicalize(smiles)
        if result.inchikey in seen:
            continue
        seen.add(result.inchikey)
        analogs.append(
            {
                "smiles": result.canonical_smiles,
                "inchikey": result.inchikey,
                "modification": f"+{label}",
            }
        )
        if len(analogs) >= max_analogs:
            break
    return analogs
