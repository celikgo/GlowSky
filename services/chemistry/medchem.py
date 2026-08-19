"""Medicinal-chemistry scoring — multi-parameter optimization (MPO) desirability and the
standard drug-/lead-/fragment-likeness rule battery.

This is the "expert ranking" layer. A medicinal chemist rarely ranks candidates by a single
number like QED; they rank by **multi-parameter desirability toward a target product profile**
and screen against a **battery of rule sets** (not just Lipinski). Both are fully deterministic
and RDKit-computed — no LLM, no fabrication — so they slot in next to `properties.py` and are
testable offline.

MPO design follows the established desirability-function convention (Pfizer CNS MPO, Derringer
desirability): each property maps to a 0–1 desirability via a piecewise-linear plateau function,
and the overall score is the **weighted arithmetic mean** of the per-property desirabilities
(0–1). Arithmetic mean — not geometric — matches the published MPO standard: it's forgiving of a
single boundary property rather than zeroing the whole molecule, while the reported *limiting
property* still surfaces the weakest axis for the chemist to act on.

Citations for the rule battery, all link-checked by .github/workflows/docs-links.yml:
    Lipinski Ro5   https://doi.org/10.1016/S0169-409X(96)00423-1
    Veber          https://doi.org/10.1021/jm020017n
    Ghose          https://doi.org/10.1021/cc9800071
    Egan           https://doi.org/10.1021/jm000292e
    Muegge         https://doi.org/10.1021/jm015507e
    Rule of 3      https://doi.org/10.1016/S1359-6446(03)02831-9
    CNS MPO        https://doi.org/10.1021/cn100008c

WHAT THIS IS NOT
    - The MPO score is NOT a prediction and has no ground truth. It is a weighted
      preference over descriptors: it says what THIS profile values, not what will
      work. Two reasonable chemists would parameterise it differently and neither
      would be wrong. There is nothing here to validate, and docs/VALIDATION.md says
      so rather than leaving the absence of a benchmark to look like an oversight.
    - The rules are not predictions of oral bioavailability. They are property ranges
      derived from sets of compounds that had already succeeded — descriptions of
      where past drugs sat, not causes of why they worked. Plenty of marketed drugs
      violate Lipinski, and every one of these rules was published with exceptions.
    - Passing the whole battery is not evidence of anything. A molecule can satisfy
      all seven rule sets and be inactive, insoluble, toxic, or unmakeable: none of
      these look at the target, and none of them look at the assay.
    - A single aggregate score hides its own trade-offs, which is why `limiting` is
      returned alongside it. Read that field.
"""
from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import Crippen

from services.chemistry.properties import compute_descriptors

# --- desirability ------------------------------------------------------------


def _desirability(value: float, lo0: float, lo1: float, hi1: float, hi0: float) -> float:
    """Piecewise-linear plateau desirability in [0, 1].

    0 below ``lo0``; ramps up to 1 at ``lo1``; plateau 1 across ``[lo1, hi1]``; ramps down to 0
    at ``hi0``. "Lower is better" sets ``lo0 == lo1`` below the range; "higher is better" sets
    ``hi1 == hi0`` above it; a band uses all four.
    """
    if value <= lo0 or value >= hi0:
        return 0.0
    if value < lo1:
        return (value - lo0) / (lo1 - lo0)
    if value <= hi1:
        return 1.0
    return (hi0 - value) / (hi0 - hi1)


# Per-profile property targets: name -> (lo0, lo1, hi1, hi0, weight). The ramps encode medicinal-
# chemistry intuition for an oral small molecule / a lead / a fragment, respectively.
_NEG = -1.0e9  # "no lower bound" sentinel for lower-is-better properties

_PROFILES: dict[str, dict[str, tuple[float, float, float, float, float]]] = {
    # Oral drug-like — the default. Plateaus sit in the sweet spots med-chem aims for.
    "oral": {
        "mw": (120.0, 250.0, 400.0, 520.0, 1.0),
        "logp": (-1.0, 1.0, 3.0, 5.0, 1.0),
        "tpsa": (20.0, 40.0, 90.0, 140.0, 1.0),
        "hbd": (_NEG, _NEG, 2.0, 5.0, 0.75),
        "hba": (_NEG, _NEG, 5.0, 10.0, 0.75),
        "rotatable_bonds": (_NEG, _NEG, 5.0, 10.0, 0.75),
        "aromatic_rings": (_NEG, _NEG, 2.0, 5.0, 0.5),
        "fsp3": (0.1, 0.3, 1.0, 1.0, 0.5),  # higher sp3 fraction = better developability
    },
    # Lead-like — smaller/simpler, leaving room to optimise (Teague lead-like space).
    "lead": {
        "mw": (120.0, 200.0, 350.0, 420.0, 1.0),
        "logp": (-1.0, 1.0, 3.0, 4.0, 1.0),
        "tpsa": (20.0, 40.0, 90.0, 130.0, 1.0),
        "hbd": (_NEG, _NEG, 2.0, 4.0, 0.75),
        "hba": (_NEG, _NEG, 4.0, 8.0, 0.75),
        "rotatable_bonds": (_NEG, _NEG, 4.0, 7.0, 0.75),
        "aromatic_rings": (_NEG, _NEG, 2.0, 3.0, 0.5),
        "fsp3": (0.1, 0.4, 1.0, 1.0, 0.5),
    },
    # Fragment — Rule-of-3 space for fragment-based screening (Congreve Ro3).
    "fragment": {
        "mw": (80.0, 120.0, 250.0, 320.0, 1.0),
        "logp": (-1.0, 0.0, 2.5, 3.5, 1.0),
        "tpsa": (10.0, 20.0, 60.0, 90.0, 1.0),
        "hbd": (_NEG, _NEG, 2.0, 3.0, 0.75),
        "hba": (_NEG, _NEG, 3.0, 4.0, 0.75),
        "rotatable_bonds": (_NEG, _NEG, 2.0, 4.0, 0.75),
        "fsp3": (0.1, 0.4, 1.0, 1.0, 0.5),
    },
}

PROFILES = tuple(_PROFILES)


def mpo_from_descriptors(descriptors: dict, profile: str = "oral") -> dict:
    """Compute the MPO desirability score from an existing descriptor dict (no recompute).

    Returns the aggregate ``score`` in [0, 1], the per-property ``desirability`` map, and the
    ``limiting`` (lowest-scoring) property — the axis a chemist should fix first.
    """
    targets = _PROFILES.get(profile)
    if targets is None:
        raise ValueError(f"unknown MPO profile {profile!r}; choose one of {PROFILES}")

    desir: dict[str, float] = {}
    wsum = 0.0
    acc = 0.0
    for prop, (lo0, lo1, hi1, hi0, weight) in targets.items():
        if prop not in descriptors:
            continue
        d = round(_desirability(float(descriptors[prop]), lo0, lo1, hi1, hi0), 3)
        desir[prop] = d
        acc += weight * d
        wsum += weight

    score = round(acc / wsum, 3) if wsum else 0.0
    limiting = min(desir, key=lambda k: desir[k]) if desir else None
    return {"score": score, "profile": profile, "desirability": desir, "limiting": limiting}


def mpo_score(canonical_smiles: str, profile: str = "oral") -> dict:
    """Multi-parameter desirability score for a molecule against a named profile.

    Profiles: ``oral`` (default), ``lead``, ``fragment``. Assumes a pre-validated SMILES.
    """
    return mpo_from_descriptors(compute_descriptors(canonical_smiles), profile)


# --- rule battery ------------------------------------------------------------


def medchem_rules(canonical_smiles: str) -> dict:
    """Screen a molecule against the standard drug-/lead-/fragment-likeness rule battery.

    Each rule returns ``{"pass": bool, "violations": [str]}``. Goes well beyond Lipinski:
    Lipinski Ro5, Veber, Ghose, Egan, Muegge, lead-likeness (Teague), and Rule of 3 (fragments).
    Assumes a pre-validated SMILES.
    """
    mol = Chem.MolFromSmiles(canonical_smiles)
    if mol is None:
        raise ValueError(f"medchem_rules received invalid SMILES: {canonical_smiles!r}")
    d = compute_descriptors(canonical_smiles)
    mr = round(Crippen.MolMR(mol), 2)  # molar refractivity, for Ghose
    heteroatoms = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() not in (1, 6))

    def rule(checks: list[tuple[bool, str]], max_violations: int = 0) -> dict:
        violations = [msg for ok, msg in checks if not ok]
        return {"pass": len(violations) <= max_violations, "violations": violations}

    rules = {
        # Lipinski Ro5 — oral bioavailability; one violation tolerated.
        "lipinski": rule(
            [
                (d["mw"] <= 500, f"MW {d['mw']} > 500"),
                (d["logp"] <= 5, f"logP {d['logp']} > 5"),
                (d["hbd"] <= 5, f"HBD {d['hbd']} > 5"),
                (d["hba"] <= 10, f"HBA {d['hba']} > 10"),
            ],
            max_violations=1,
        ),
        # Veber — oral bioavailability via flexibility + polar surface.
        "veber": rule(
            [
                (d["rotatable_bonds"] <= 10, f"rotatable bonds {d['rotatable_bonds']} > 10"),
                (d["tpsa"] <= 140, f"TPSA {d['tpsa']} > 140"),
            ]
        ),
        # Ghose — qualifying range for drug-likeness.
        "ghose": rule(
            [
                (160 <= d["mw"] <= 480, f"MW {d['mw']} outside 160-480"),
                (-0.4 <= d["logp"] <= 5.6, f"logP {d['logp']} outside -0.4-5.6"),
                (20 <= d["heavy_atoms"] <= 70, f"heavy atoms {d['heavy_atoms']} outside 20-70"),
                (40 <= mr <= 130, f"molar refractivity {mr} outside 40-130"),
            ]
        ),
        # Egan — passive intestinal absorption (logP / TPSA boundary).
        "egan": rule(
            [
                (d["logp"] <= 5.88, f"logP {d['logp']} > 5.88"),
                (d["tpsa"] <= 131.6, f"TPSA {d['tpsa']} > 131.6"),
            ]
        ),
        # Muegge — pharmacophore-aware drug-likeness (computable subset).
        "muegge": rule(
            [
                (200 <= d["mw"] <= 600, f"MW {d['mw']} outside 200-600"),
                (-2 <= d["logp"] <= 5, f"logP {d['logp']} outside -2-5"),
                (d["tpsa"] <= 150, f"TPSA {d['tpsa']} > 150"),
                (d["rotatable_bonds"] <= 15, f"rotatable bonds {d['rotatable_bonds']} > 15"),
                (d["hbd"] <= 5, f"HBD {d['hbd']} > 5"),
                (d["hba"] <= 10, f"HBA {d['hba']} > 10"),
                (heteroatoms > 1, f"too few heteroatoms ({heteroatoms})"),
            ]
        ),
        # Lead-likeness (Teague) — leave headroom for optimisation.
        "lead_like": rule(
            [
                (d["mw"] <= 350, f"MW {d['mw']} > 350"),
                (d["logp"] <= 3, f"logP {d['logp']} > 3"),
            ]
        ),
        # Rule of 3 (Congreve) — fragment-based screening.
        "rule_of_three": rule(
            [
                (d["mw"] <= 300, f"MW {d['mw']} > 300"),
                (d["logp"] <= 3, f"logP {d['logp']} > 3"),
                (d["hbd"] <= 3, f"HBD {d['hbd']} > 3"),
                (d["hba"] <= 3, f"HBA {d['hba']} > 3"),
                (d["rotatable_bonds"] <= 3, f"rotatable bonds {d['rotatable_bonds']} > 3"),
                (d["tpsa"] <= 60, f"TPSA {d['tpsa']} > 60"),
            ]
        ),
    }
    passed = [name for name, r in rules.items() if r["pass"]]
    return {
        "molar_refractivity": mr,
        "heteroatoms": heteroatoms,
        "rules": rules,
        "passed": passed,
        "n_passed": len(passed),
    }
