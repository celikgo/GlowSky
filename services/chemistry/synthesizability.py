"""Synthetic accessibility (SA score, Ertl & Schuffenhauer) via RDKit Contrib.

SA score ranges ~1 (easy to make) to ~10 (hard). It is computed from fragment
contributions learned over PubChem plus a molecular-complexity penalty — i.e. from how
COMMON a molecule's pieces are in known chemistry, not from any model of a synthesis.

    Ertl, P. & Schuffenhauer, A. "Estimation of synthetic accessibility score of
    drug-like molecules based on molecular complexity and fragment contributions."
    J. Cheminform. 1(1), 8 (2009).  https://doi.org/10.1186/1758-2946-1-8

Like every predictor in Glowsky this returns a `Prediction`: the score travels with its
applicability domain, its resolution, and its provenance. See services/chemistry/
provenance.py for why a bare number is not an acceptable output.

The applicability domain here is not a proxy — it is read out of the model's own
internals. `sascorer` scores a molecule by looking up each of its Morgan fragments in a
table built from PubChem, and any fragment MISSING from that table silently contributes a
default of -4 (i.e. "rare, therefore hard"). So the fraction of a molecule's fragments
that are absent from the table is a direct measure of how much of its score is evidence
and how much is that default. For a metal complex it is ~30%; for a drug-like organic it
is 0%. That fraction is what `applicability` reports.

WHAT THIS IS NOT
    - Not a route, and not evidence one exists. A score of 2.5 does not mean anybody
      can make the compound; it means its fragments are common. Ask retrosynthesize()
      for the "how", and see docs/VALIDATION.md for what that is and is not.
    - Not a yield, a cost, or a time estimate.
    - Not a measurement, and not measurable. There is no assay for "synthetic
      accessibility", so this number has no true value to be right or wrong about. It
      ranks; it does not quantify.
    - Not validated in this repository. Reproducing the published algorithm via RDKit
      Contrib is not the same as reproducing the published RESULT: validating it would
      need the expert-assigned synthesizability rankings the authors scored against.
      Listed as unvalidated in docs/VALIDATION.md.
    - Not the published algorithm exactly. RDKit's sascorer deviates from the paper on
      the macrocycle term (a flat log10(2) penalty for any ring >8 atoms, rather than the
      paper's log10(nMacrocycles+1)); the RDKit authors note this in the source. The
      provenance below records the deviation rather than papering over it.
    - The <=6 threshold is a convention, not a decision boundary anyone derived. A
      compound at 6.1 differs from one at 5.9 by nothing in particular.
"""
from __future__ import annotations

import os
import sys

from rdkit import Chem
from rdkit.Chem import RDConfig, rdFingerprintGenerator

from services.chemistry.provenance import (
    CITE_ERTL_SA,
    ApplicabilityDomain,
    Domain,
    ModelKind,
    Prediction,
    Provenance,
    Uncertainty,
    UncertaintyBasis,
)

# sascorer ships in RDKit's Contrib tree, not the main namespace.
sys.path.append(os.path.join(RDConfig.RDContribDir, "SA_Score"))
import sascorer

SYNTHESIZABLE_THRESHOLD = 6.0

#: The SA scale is reported to 0.1 in the source paper and its differences are only
#: interpretable in bands ("easy" / "moderate" / "hard"). This is the width below which
#: two scores should be treated as the same answer. It is a stated convention, not a
#: measured error — UncertaintyBasis.STATED_ESTIMATE says exactly that.
SA_RESOLUTION = 1.0

#: Above this fraction of unseen Morgan fragments, the score is being driven by
#: sascorer's -4 default for unknown fragments rather than by PubChem evidence.
#: 0.30 is where cisplatin — a metal complex, the textbook out-of-domain case — lands.
_UNSEEN_FRAGMENT_LIMIT = 0.15

#: Ertl & Schuffenhauer fitted and validated on drug-like organics from PubChem.
_MIN_HEAVY_ATOMS = 3
_MAX_HEAVY_ATOMS = 100

#: Elements that appear in ordinary small-molecule drug space. A molecule built from
#: anything else is not what the fragment table was compiled over.
_ORGANIC_ELEMENTS = frozenset(
    ["H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Se", "Br", "I"]
)

_MORGAN = rdFingerprintGenerator.GetMorganGenerator(radius=2)


def _unseen_fragment_fraction(mol: Chem.Mol) -> float:
    """Fraction of this molecule's Morgan fragments absent from sascorer's table.

    Mirrors sascorer.calculateScore's own featurisation (Morgan radius 2, count-based) so
    the number describes the scoring actually performed, not an approximation of it.
    """
    # sascorer loads its table lazily on first use; scoring has already happened by the
    # time we are called, but be explicit rather than depending on that ordering.
    if sascorer._fscores is None:
        sascorer.readFragmentScores()
    counts = _MORGAN.GetSparseCountFingerprint(mol).GetNonzeroElements()
    total = sum(counts.values())
    if not total:
        return 1.0
    unseen = sum(n for frag_id, n in counts.items() if frag_id not in sascorer._fscores)
    return unseen / total


def _applicability(mol: Chem.Mol, unseen_fraction: float) -> ApplicabilityDomain:
    heavy = mol.GetNumHeavyAtoms()
    elements = {a.GetSymbol() for a in mol.GetAtoms()}
    domain = ApplicabilityDomain.from_checks(
        {
            "fragments_present_in_pubchem_table": unseen_fraction <= _UNSEEN_FRAGMENT_LIMIT,
            "heavy_atoms_in_range": _MIN_HEAVY_ATOMS <= heavy <= _MAX_HEAVY_ATOMS,
            "organic_elements_only": elements <= _ORGANIC_ELEMENTS,
        }
    )
    # The fragment check is the one that speaks for the model itself, so when it is the
    # reason for the verdict, say so in the numbers rather than only naming the criterion.
    if unseen_fraction > _UNSEEN_FRAGMENT_LIMIT:
        return ApplicabilityDomain(
            verdict=domain.verdict,
            checks=domain.checks,
            explanation=(
                f"{unseen_fraction:.0%} of this molecule's fragments are absent from the "
                "PubChem-derived table sascorer scores against; each contributes the "
                "model's -4 'unknown fragment' default, so the score reflects the "
                f"default more than the evidence ({domain.explanation})"
            ),
        )
    return domain


def sa_score(canonical_smiles: str) -> dict:
    """Synthetic accessibility for a canonical SMILES, as a Prediction payload.

    The flat `sa_score` / `synthesizable` / `scale` keys are retained at the top level
    because callers in this repository (retrosynthesis.py) read them; they are the same
    numbers as `value`, not a second opinion.
    """
    mol = Chem.MolFromSmiles(canonical_smiles)
    if mol is None:
        raise ValueError(f"invalid SMILES: {canonical_smiles!r}")

    score = sascorer.calculateScore(mol)
    unseen = _unseen_fragment_fraction(mol)
    domain = _applicability(mol, unseen)

    prediction = Prediction(
        value=round(score, 3),
        unit="SA score (1 easy – 10 hard)",
        uncertainty=Uncertainty(
            basis=UncertaintyBasis.STATED_ESTIMATE,
            sigma=SA_RESOLUTION,
            source=(
                f"stated resolution of {SA_RESOLUTION} SA units, not a measured error: "
                "synthetic accessibility has no assay, so this band is the width below "
                "which two scores should be read as the same answer. It is a convention "
                "of this repository, not a figure from the source paper"
            ),
        ),
        applicability=domain,
        provenance=Provenance(
            model="Ertl & Schuffenhauer SA score",
            kind=ModelKind.PUBLISHED_HEURISTIC,
            version=f"RDKit Contrib sascorer, RDKit {Chem.rdBase.rdkitVersion}",
            trained_on=(
                "Morgan-fragment frequencies compiled over ~1M PubChem compounds, plus a "
                "hand-specified complexity penalty (size, stereocentres, spiro, "
                "bridgeheads, macrocycles). Not fitted to any measured quantity"
            ),
            citations=(CITE_ERTL_SA,),
            notes=(
                "RDKit's implementation deviates from the published paper on the "
                "macrocycle term: a flat log10(2) penalty for any ring larger than 8 "
                "atoms, rather than the paper's log10(nMacrocycles+1). Not validated in "
                "this repository — reproducing the algorithm is not reproducing the "
                "published result, which was scored against expert rankings this project "
                "does not have. Listed as unvalidated in docs/VALIDATION.md"
            ),
        ),
        extra={
            "unseen_fragment_fraction": round(unseen, 4),
            "unseen_fragment_note": (
                "share of this molecule's Morgan fragments missing from sascorer's "
                "PubChem table; each such fragment scores the model's -4 default"
            ),
        },
    )

    out = prediction.as_dict()
    out.update(
        {
            "sa_score": round(score, 3),
            "synthesizable": (
                score <= SYNTHESIZABLE_THRESHOLD if domain.verdict is not Domain.OUT else None
            ),
            "scale": "1 (easy) – 10 (hard); threshold 6.0 by convention, not derived",
        }
    )
    return out
