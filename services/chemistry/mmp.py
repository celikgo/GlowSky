"""Matched Molecular Pairs (MMP) and SAR transform mining — the core technique for reading
structure–activity relationships off a series.

Two molecules form a *matched pair* when they differ by a single, well-defined structural change
on an otherwise identical scaffold (e.g. H→F, methyl→ethyl). Aggregating those changes across a
set answers the question a medicinal chemist actually asks: *"what does swapping X for Y do to
this property, on average?"* — the basis of rational optimisation.

Deterministic and RDKit-computed (Hussain–Rea single-cut fragmentation via ``rdMMPA``); no LLM.

Method: every molecule is fragmented at each acyclic single bond into (context, variable). The
larger piece is the **context** (the shared scaffold, carrying an attachment point ``[*:1]``); the
smaller is the **variable** group. Two molecules sharing a canonical context but differing in the
variable group are a matched pair, with transformation ``var_a >> var_b`` (canonicalised to one
direction). When a property is given, the pair carries the signed Δ, and ``sar_transforms``
aggregates Δ per transformation across the set.
"""
from __future__ import annotations

from statistics import median

from rdkit import Chem
from rdkit.Chem import rdMMPA

from services.chemistry.medchem import mpo_from_descriptors
from services.chemistry.properties import compute_descriptors

# Properties a pair's Δ can be measured on — any core descriptor, plus the MPO desirability.
_DESCRIPTOR_KEYS = (
    "mw", "logp", "tpsa", "hbd", "hba", "rotatable_bonds", "aromatic_rings", "fsp3", "qed",
    "heavy_atoms",
)


def _value(canonical_smiles: str, prop: str) -> float:
    """Resolve a property value for a molecule (descriptor or MPO desirability)."""
    if prop == "mpo":
        return mpo_from_descriptors(compute_descriptors(canonical_smiles))["score"]
    if prop in _DESCRIPTOR_KEYS:
        return float(compute_descriptors(canonical_smiles)[prop])
    raise ValueError(f"unknown property {prop!r}; choose from {(*_DESCRIPTOR_KEYS, 'mpo')}")


def _canonical(frag_smiles: str) -> str:
    """Canonicalise a fragment SMILES (keeps the ``[*:1]`` attachment point)."""
    m = Chem.MolFromSmiles(frag_smiles)
    return Chem.MolToSmiles(m) if m is not None else frag_smiles


def _heavy(frag_smiles: str) -> int:
    """Heavy-atom count of a fragment, excluding the attachment dummy."""
    m = Chem.MolFromSmiles(frag_smiles)
    if m is None:
        return 0
    return sum(1 for a in m.GetAtoms() if a.GetAtomicNum() > 1)


def _fragment_contexts(canonical_smiles: str) -> list[tuple[str, str]]:
    """Single-cut fragmentations of a molecule as ``(context, variable)`` canonical pairs.

    Context = the larger fragment (the shared scaffold); variable = the smaller (the group being
    swapped). De-duplicated per molecule (symmetry can yield the same split twice).
    """
    mol = Chem.MolFromSmiles(canonical_smiles)
    if mol is None:
        return []
    out: set[tuple[str, str]] = set()
    for _core, chains in rdMMPA.FragmentMol(mol, maxCuts=1, resultsAsMols=False):
        parts = chains.split(".")
        if len(parts) != 2:
            continue  # single cut yields exactly two pieces
        a, b = parts
        context, variable = (a, b) if _heavy(a) >= _heavy(b) else (b, a)
        out.add((_canonical(context), _canonical(variable)))
    return list(out)


def matched_pairs(
    smiles_list: list[str], property: str | None = None
) -> dict:
    """Find matched molecular pairs in a set of molecules.

    Each pair shares a scaffold (``context``) and differs by one group, giving a ``transformation``
    (``var_a >> var_b``, canonicalised to a single direction). When ``property`` is given (a
    descriptor name or ``"mpo"``), each pair carries the signed Δ in that property.
    """
    # Canonicalise inputs; index every (context -> variable) occurrence by molecule.
    mols: list[str] = []
    for s in smiles_list:
        m = Chem.MolFromSmiles(s)
        if m is not None:
            mols.append(Chem.MolToSmiles(m))

    values: dict[str, float] = {}
    if property is not None:
        for s in set(mols):
            values[s] = _value(s, property)

    # context -> list of (variable, molecule)
    index: dict[str, list[tuple[str, str]]] = {}
    for s in mols:
        for context, variable in _fragment_contexts(s):
            index.setdefault(context, []).append((variable, s))

    seen: set[tuple[str, str, str]] = set()
    pairs: list[dict] = []
    for context, members in index.items():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                var_i, mol_i = members[i]
                var_j, mol_j = members[j]
                if var_i == var_j or mol_i == mol_j:
                    continue
                # Canonical transformation direction: lexically smaller variable first, so the same
                # chemical change always aggregates one way.
                (f1, m1), (f2, m2) = sorted(
                    [(var_i, mol_i), (var_j, mol_j)], key=lambda t: t[0]
                )
                key = (m1, m2, f"{f1}>>{f2}")
                if key in seen:
                    continue
                seen.add(key)
                rec = {
                    "a": m1,
                    "b": m2,
                    "transformation": f"{f1}>>{f2}",
                    "context": context,
                }
                if property is not None:
                    va, vb = values[m1], values[m2]
                    rec["value_a"] = round(va, 3)
                    rec["value_b"] = round(vb, 3)
                    rec["delta"] = round(vb - va, 3)
                pairs.append(rec)

    return {
        "property": property,
        "n_molecules": len(set(mols)),
        "n_pairs": len(pairs),
        "pairs": pairs,
    }


def sar_transforms(
    smiles_list: list[str], property: str = "logp", min_count: int = 1
) -> dict:
    """Mine SAR transforms: aggregate each transformation's effect on a property across the set.

    Returns transforms ranked by support (``n``) then by effect magnitude — e.g. *"H→F lowers
    logP by 0.4 on average (n=6)"*. ``property`` is a descriptor name or ``"mpo"``.
    """
    result = matched_pairs(smiles_list, property=property)
    by_transform: dict[str, list[float]] = {}
    for p in result["pairs"]:
        by_transform.setdefault(p["transformation"], []).append(p["delta"])

    transforms = []
    for t, deltas in by_transform.items():
        if len(deltas) < min_count:
            continue
        transforms.append(
            {
                "transformation": t,
                "n": len(deltas),
                "mean_delta": round(sum(deltas) / len(deltas), 3),
                "median_delta": round(median(deltas), 3),
                "min_delta": round(min(deltas), 3),
                "max_delta": round(max(deltas), 3),
            }
        )
    # Most-supported first; ties broken by larger average effect.
    transforms.sort(key=lambda r: (r["n"], abs(r["mean_delta"])), reverse=True)
    return {
        "property": property,
        "n_molecules": result["n_molecules"],
        "n_transforms": len(transforms),
        "transforms": transforms,
    }
