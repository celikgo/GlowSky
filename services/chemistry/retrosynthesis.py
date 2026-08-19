"""Template-based retrosynthetic analysis and a synthesizability assessment.

SA score (``synthesizability.py``) answers *"how hard is this to make?"* as a number. This module
answers the next question a chemist asks: *"how would I actually make it?"* — by disconnecting the
target at recognised bonds into purchasable-looking precursors, the way a one-step retrosynthesis
does on paper.

It is **deliberately not** a full ML route planner (AiZynth-class) — that needs a trained policy
model + a reaction corpus + a live building-block catalog, none of which we provision before
they're needed (the activation-threshold rule). Instead it applies a curated set of **robust,
named disconnections** as RDKit retro-reaction SMARTS, deterministically. Each disconnection names
the forward reaction that would re-form the bond, and every precursor passes the validation
firewall. The building-block call is an honest **heuristic** (small + easy-to-make), not a catalog
lookup — labelled as such.
"""
from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from services.chemistry.properties import compute_descriptors
from services.chemistry.synthesizability import sa_score
from services.chemistry.validation import validate_and_canonicalize

# Named single-step disconnections: forward reaction -> retro SMARTS (target >> precursors).
# Each is a workhorse coupling a medicinal chemist reaches for first.
_RETRO_TEMPLATES = {
    "amide coupling": "[C:1](=O)[NX3:2]>>[C:1](=O)O.[N:2]",
    "esterification": "[C:1](=O)[O:2][#6:3]>>[C:1](=O)O.[O:2][#6:3]",
    "sulfonamide formation": "[S:1](=O)(=O)[NX3:2]>>[S:1](=O)(=O)Cl.[N:2]",
    "urea formation": "[NX3:1][CX3:2](=O)[NX3:3]>>[N:1].[N:3]",
    "Suzuki coupling": "[c:1]-[c:2]>>[c:1]Br.[c:2]B(O)O",
    "reductive amination": "[#6:1][CH2;!R:2][NX3:3]>>[#6:1][CH:2]=O.[N:3]",
    "Williamson ether": "[#6;!$([CX3]=O):1][OX2:2][#6;!$([CX3]=O):3]>>[#6:1][O:2].[#6:3]Br",
}
_RETRO_RXNS = {name: AllChem.ReactionFromSmarts(s) for name, s in _RETRO_TEMPLATES.items()}

# Building-block heuristic thresholds — a precursor "looks purchasable" if it's small and easy to
# make. An honest proxy for a catalog lookup, not the real thing.
_BB_MAX_HEAVY_ATOMS = 12
_BB_MAX_SA = 3.5


def _precursor_is_building_block(canonical_smiles: str) -> bool:
    desc = compute_descriptors(canonical_smiles)
    return (
        desc["heavy_atoms"] <= _BB_MAX_HEAVY_ATOMS
        and sa_score(canonical_smiles)["sa_score"] <= _BB_MAX_SA
    )


def retrosynthesize(canonical_smiles: str, max_routes: int = 10) -> dict:
    """One-step retrosynthetic disconnections of a pre-validated target.

    Returns each disconnection as ``{reaction, precursors, all_building_blocks}`` — the named
    forward reaction, the validated precursor SMILES, and whether every precursor looks like a
    purchasable building block (heuristic). De-duplicated, capped at ``max_routes``.
    """
    target = validate_and_canonicalize(canonical_smiles)
    if not target.valid:
        raise ValueError(f"retrosynthesize received invalid target: {target.error}")
    mol = Chem.MolFromSmiles(target.canonical_smiles)

    disconnections: list[dict] = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for reaction, rxn in _RETRO_RXNS.items():
        for products in rxn.RunReactants((mol,)):
            precursors: list[str] = []
            ok = True
            for p in products:
                try:
                    Chem.SanitizeMol(p)
                except Exception:  # noqa: BLE001 - an unsanitizable precursor invalidates the
                    # disconnection; RDKit's sanitization errors have no common base class.
                    ok = False
                    break
                res = validate_and_canonicalize(Chem.MolToSmiles(p))
                if not res.valid:
                    ok = False
                    break
                precursors.append(res.smiles)
            if not ok or not precursors:
                continue
            key = (reaction, frozenset(precursors))
            if key in seen:
                continue
            seen.add(key)
            disconnections.append(
                {
                    "reaction": reaction,
                    "precursors": precursors,
                    "all_building_blocks": all(
                        _precursor_is_building_block(s) for s in precursors
                    ),
                }
            )
            if len(disconnections) >= max_routes:
                break
        if len(disconnections) >= max_routes:
            break

    # Surface the most tractable routes first: those whose precursors all look purchasable.
    disconnections.sort(key=lambda d: d["all_building_blocks"], reverse=True)
    return {
        "target": target.canonical_smiles,
        "n_disconnections": len(disconnections),
        "disconnections": disconnections,
    }


def _sa_label(score: float) -> str:
    return "easy" if score <= 4 else "moderate" if score <= 6 else "hard"


def synthesizability(canonical_smiles: str) -> dict:
    """A synthesizability assessment: SA score + whether a known one-step route exists.

    Combines the Ertl SA score (how hard) with a template retrosynthesis (how — a named
    disconnection into building-block-like precursors). ``route_found`` is True when at least one
    disconnection yields all-purchasable-looking precursors (heuristic).
    """
    sa = sa_score(canonical_smiles)
    retro = retrosynthesize(canonical_smiles)
    routes_to_bb = [d for d in retro["disconnections"] if d["all_building_blocks"]]
    route_found = len(routes_to_bb) > 0
    # Chosen inside each branch rather than before them: the previous form built
    # `best` from a conditional and then re-derived the same condition to index it,
    # which left the None case reachable on paper.
    best: dict | None
    if route_found:
        best = routes_to_bb[0]
        assessment = (
            f"SA {sa['sa_score']} ({_sa_label(sa['sa_score'])}); a one-step "
            f"{best['reaction']} from building-block-like precursors looks viable."
        )
    elif retro["disconnections"]:
        best = retro["disconnections"][0]
        assessment = (
            f"SA {sa['sa_score']} ({_sa_label(sa['sa_score'])}); disconnectable via "
            f"{best['reaction']}, but the precursors are non-trivial — expect a multi-step route."
        )
    else:
        best = None
        assessment = (
            f"SA {sa['sa_score']} ({_sa_label(sa['sa_score'])}); no recognised one-step "
            f"disconnection — needs route design beyond these templates."
        )

    return {
        "sa_score": sa["sa_score"],
        "sa_label": _sa_label(sa["sa_score"]),
        "synthesizable": sa["synthesizable"],
        "n_disconnections": retro["n_disconnections"],
        "route_found": route_found,
        "best_disconnection": best,
        "assessment": assessment,
    }
