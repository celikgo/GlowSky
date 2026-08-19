"""Bioisosteric replacement and scaffold hopping — deterministic, knowledge-based.

R-group enumeration (``generative.py``) decorates a fixed scaffold; this module changes the
*functional groups and the scaffold itself* the way a medicinal chemist does to keep activity
while tuning properties, metabolic stability, or IP. Each rule is a curated, well-established
bioisosteric transformation encoded as an RDKit reaction SMARTS — no ML/LLM invents structures,
and every product passes the validation firewall.

Two families:
  * **bioisosteres** — functional-group swaps (carboxylic-acid → tetrazole / acylsulfonamide /
    hydroxamic acid / primary amide; methyl ester → amide; ether → thioether).
  * **scaffold hops** — ring edits (the "nitrogen walk": replace an aromatic C–H with ring N,
    benzene → pyridine and friends).
"""
from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from services.chemistry.validation import validate_and_canonicalize

# Functional-group bioisosteres. Each maps a recognised group to a classic replacement; the
# attachment context (mapped atom :1) is preserved so the rest of the molecule is untouched.
_BIOISOSTERES = {
    "acid->tetrazole": "[C:1](=O)[OX2H1]>>[C:1]1=NN=NN1",
    "acid->acylsulfonamide": "[C:1](=O)[OX2H1]>>[C:1](=O)NS(=O)(=O)C",
    "acid->hydroxamic": "[C:1](=O)[OX2H1]>>[C:1](=O)NO",
    "acid->amide": "[C:1](=O)[OX2H1]>>[C:1](=O)N",
    "ester->amide": "[C:1](=O)[OX2][CH3]>>[C:1](=O)N",
    # Ether oxygen → sulfur, guarded so esters/acids (carbonyl-adjacent O) don't false-match.
    "ether->thioether": "[#6;!$([CX3]=O):2][OX2;!$(O[CX3]=O):1][#6;!$([CX3]=O):3]"
    ">>[#6:2][S:1][#6:3]",
}

# Scaffold hops — ring-atom edits. The nitrogen walk turns an aromatic C–H into a ring nitrogen.
_SCAFFOLD_HOPS = {
    "aza-walk": "[cH:1]>>[n:1]",
}

_BIOISOSTERE_RXNS = {k: AllChem.ReactionFromSmarts(v) for k, v in _BIOISOSTERES.items()}
_SCAFFOLD_HOP_RXNS = {k: AllChem.ReactionFromSmarts(v) for k, v in _SCAFFOLD_HOPS.items()}


def _apply(rxns: dict, mol: Chem.Mol, seen: set[str]) -> list[tuple[str, str]]:
    """Run each reaction; return (label, canonical_smiles) for valid, unique products."""
    out: list[tuple[str, str]] = []
    for label, rxn in rxns.items():
        for products in rxn.RunReactants((mol,)):
            try:
                Chem.SanitizeMol(products[0])
            except Exception:  # noqa: BLE001,S112 - RDKit raises several unrelated C++-mapped
                # sanitization exceptions (valence, kekulization, ...). A transform product
                # that will not sanitize is not a molecule, and silently dropping it IS the
                # firewall: there is nothing to log that the caller could act on.
                continue
            result = validate_and_canonicalize(Chem.MolToSmiles(products[0]))
            if result.valid and result.key not in seen:
                seen.add(result.key)
                out.append((label, result.smiles))
    return out


def bioisosteric_analogs(canonical_smiles: str, *, max_results: int = 20) -> list[dict]:
    """Generate bioisostere + scaffold-hop analogs of a pre-validated parent molecule.

    Returns ``{smiles, inchikey, modification}`` dicts (modification = the transformation that
    produced it), de-duplicated by InChIKey, excluding the parent, capped at ``max_results``.
    Bioisosteres are emitted before scaffold hops so the higher-value functional-group swaps
    survive the cap.
    """
    parent = validate_and_canonicalize(canonical_smiles)
    if not parent.valid:
        raise ValueError(f"bioisosteric_analogs received invalid parent: {parent.error}")

    mol = Chem.MolFromSmiles(parent.smiles)
    seen = {parent.key}
    products = _apply(_BIOISOSTERE_RXNS, mol, seen) + _apply(_SCAFFOLD_HOP_RXNS, mol, seen)

    analogs: list[dict] = []
    for label, smiles in products:
        result = validate_and_canonicalize(smiles)
        analogs.append(
            {
                "smiles": result.canonical_smiles,
                "inchikey": result.inchikey,
                "modification": label,
            }
        )
        if len(analogs) >= max_results:
            break
    return analogs
