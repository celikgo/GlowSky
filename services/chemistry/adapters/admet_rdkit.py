"""An offline ADMET backend: published QSPR where one exists, labelled heuristics elsewhere.

Every endpoint here returns a `Prediction` — a value WITH its uncertainty, its
applicability domain, and a citation — because a bare ADMET number is a claim this
project has no right to make. See services/chemistry/provenance.py for why that shape
exists and what each field means.

The endpoints are NOT of equal standing, and the code says so rather than presenting
them as a uniform panel:

  solubility  is the real thing: Delaney's ESOL regression, reproduced coefficient for
              coefficient from the 2004 paper, with an uncertainty band MEASURED by this
              repository's own validation suite against a public dataset and regenerated
              in CI (docs/VALIDATION.md). ModelKind.PUBLISHED_QSPR.

  bbb         is a published-style threshold rule on TPSA/MW/logP/HBD. It answers "is
              this inside a range associated with CNS penetration", not "what is the
              brain:plasma ratio". ModelKind.PUBLISHED_RULE.

  logd, herg, cyp3a4, metabolic_stability, ppb
              are in-house correlations on lipophilicity and a couple of substructure
              flags. They are directionally reasonable and they are NOT validated
              against anything. ModelKind.HEURISTIC, confidence low, and every one of
              them is labelled `unvalidated` in docs/VALIDATION.md rather than being
              listed beside the endpoint that is validated.

That asymmetry is the honest picture, and flattening it — which is what a uniform
"ADMET panel" UI does by default — is how a heuristic ends up quoted like a measurement.

For genuinely predictive numbers, register the ADMET-AI container tool
(examples/tools/admet_ai) instead: same adapter seam, GNN-grade models, and it brings its
own published benchmark performance.

Enabled via GLOWSKY_ADMET_BACKEND=rdkit. The module default remains "not configured", so
Glowsky returns no ADMET numbers at all unless a backend is explicitly chosen.

WHAT THIS IS NOT
----------------
These are triage and prioritisation aids for deciding which compound to make next.
They are not measurements and not a substitute for an assay. A predicted hERG risk is
not a cardiac safety assessment; a predicted solubility is not a formulation input; none
of this is a regulatory or safety assessment of any kind. Anything reported OUT of its
applicability domain is printed for transparency and must not be used for a decision.
"""
from __future__ import annotations

import math

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, rdMolDescriptors

from services.chemistry.provenance import (
    CITE_DELANEY_ESOL,
    CITE_TPSA,
    ApplicabilityDomain,
    Citation,
    Domain,
    ModelKind,
    Prediction,
    Provenance,
    Uncertainty,
    UncertaintyBasis,
)

# SMARTS for a likely-basic nitrogen (protonatable amine), excluding amides/anilines/etc.
_BASIC_N = Chem.MolFromSmarts("[NX3;H2,H1,H0;!$(NC=O);!$(N=*);!$([N+]);!$(Nc)]")

# Endpoints this backend can estimate.
_ENDPOINTS = ["solubility", "logd", "herg", "cyp3a4", "metabolic_stability", "ppb", "bbb"]

#: Residual spread of THIS implementation of ESOL against the reference set in
#: tests/validation/reference/. Not a number quoted from the paper and not a guess: it is
#: measured by tests/validation/test_esol_solubility.py, which fails if the implementation
#: drifts away from it, and republished into docs/VALIDATION.md on every CI run.
#:
#: The test is the authority; this constant only carries the measured value to the place
#: the uncertainty band is built, and
#: tests/validation/test_esol_solubility.py::test_the_published_uncertainty_matches_the_measured_error
#: fails if the two drift apart by more than 0.05 — so Glowsky cannot display an
#: uncertainty it does not have.
#:
#: 1.10 log units is a factor of ~12.6 in concentration. That is genuinely how good this
#: model is, and quoting a smaller number to make the output look better would be exactly
#: the dishonesty this whole module exists to prevent.
ESOL_MEASURED_RMSE = 1.10

#: Version of THIS backend's parameterisation, distinct from Glowsky's version. Bump it
#: whenever a coefficient or a threshold below changes, because a stored prediction is
#: only interpretable next to the parameterisation that produced it.
BACKEND_VERSION = "1.0.0"

_CITE_ESOL_DOMAIN = Citation(
    reference=(
        "Applicability bounds are this implementation's, chosen to cover the drug-like "
        "region of Delaney's fitting set; see docs/VALIDATION.md for how they were set"
    ),
)


def _aromatic_proportion(mol: Chem.Mol) -> float:
    heavy = mol.GetNumHeavyAtoms()
    if heavy == 0:
        return 0.0
    aromatic = sum(1 for a in mol.GetAtoms() if a.GetIsAromatic())
    return aromatic / heavy


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _heuristic_provenance(model: str, basis: str) -> Provenance:
    """Provenance for the unvalidated endpoints. Says 'heuristic' in the payload, not just here."""
    return Provenance(
        model=model,
        kind=ModelKind.HEURISTIC,
        version=BACKEND_VERSION,
        trained_on="not fitted to measured data — an in-house correlation",
        citations=(),
        notes=(
            f"Directional only: {basis}. This endpoint has NO published validation behind "
            "this parameterisation and is listed as unvalidated in docs/VALIDATION.md. Use it "
            "to rank a series, never to quote a value."
        ),
    )


class RDKitQSPRADMET:
    """Deterministic ADMET estimates from RDKit descriptors + published correlations."""

    name = "rdkit-qspr"
    endpoints = _ENDPOINTS

    def predict(self, canonical_smiles: str, endpoints: list[str]) -> dict:
        mol = Chem.MolFromSmiles(canonical_smiles)
        if mol is None:
            raise ValueError(f"RDKitQSPRADMET received invalid SMILES: {canonical_smiles!r}")

        mw = Descriptors.MolWt(mol)
        logp = Crippen.MolLogP(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        rb = rdMolDescriptors.CalcNumRotatableBonds(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        arom_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        ap = _aromatic_proportion(mol)
        has_basic_n = mol.HasSubstructMatch(_BASIC_N) if _BASIC_N is not None else False

        computed = {
            "solubility": lambda: self._solubility(mw, logp, rb, ap),
            "logd": lambda: self._logd(logp, mw),
            "herg": lambda: self._herg(logp, mw, has_basic_n),
            "cyp3a4": lambda: self._cyp3a4(logp, mw),
            "metabolic_stability": lambda: self._metabolic_stability(logp, arom_rings, mw),
            "ppb": lambda: self._ppb(logp, mw),
            "bbb": lambda: self._bbb(tpsa, mw, logp, hbd),
        }

        out: dict = {}
        for ep in endpoints:
            key = ep.strip().lower()
            if key in computed:
                out[key] = computed[key]().as_dict()
            else:
                out[ep] = {"error": "endpoint not supported by rdkit-qspr backend"}
        return out

    # --- endpoint models ------------------------------------------------------

    @staticmethod
    def _solubility(mw: float, logp: float, rb: int, ap: float) -> Prediction:
        """Delaney ESOL (2004): logS (mol/L) from cLogP, MW, rotatable bonds, aromatic fraction.

        The four coefficients are the published ones. This is the only endpoint in this
        backend with a real fitted model behind it, and the only one whose error bar is a
        measurement rather than a judgement.
        """
        log_s = 0.16 - 0.63 * logp - 0.0062 * mw + 0.066 * rb - 0.74 * ap

        # Domain: the drug-like region of the fitting set. A number is still computed
        # outside it — refusing would hide the fact that the model HAS an opinion — but
        # the verdict travels with it and Prediction.as_dict() attaches a caveat.
        domain = ApplicabilityDomain.from_checks(
            {
                "mw_100_to_600": 100.0 <= mw <= 600.0,
                "clogp_-3_to_7": -3.0 <= logp <= 7.0,
                "rotatable_bonds_le_15": rb <= 15,
            }
        )

        # mg/mL is the unit a bench chemist actually thinks in, so it is worth carrying —
        # but note it is a TRANSFORM of the value above, not an independent estimate: the
        # ±0.9 log-unit band becomes a multiplicative factor of ~8x either way once
        # exponentiated, which is why the interval is published in log units.
        mg_per_ml = (10.0 ** log_s) * mw

        return Prediction(
            value=round(log_s, 2),
            unit="logS (mol/L)",
            extra={
                "mg_per_ml": round(mg_per_ml, 4),
                "mg_per_ml_note": (
                    "derived from logS by 10**logS * MW; inherits the same uncertainty, "
                    "which on this scale is roughly an 8x band in each direction"
                ),
            },
            uncertainty=Uncertainty.from_sigma(
                log_s,
                ESOL_MEASURED_RMSE,
                basis=UncertaintyBasis.MEASURED_BENCHMARK,
                source=(
                    f"RMSE {ESOL_MEASURED_RMSE} log units, measured by "
                    "tests/validation/test_esol_solubility.py against the reference set in "
                    "tests/validation/reference/ and regenerated in CI"
                ),
            ),
            applicability=domain,
            provenance=Provenance(
                model="ESOL",
                kind=ModelKind.PUBLISHED_QSPR,
                version=f"Delaney-2004 coefficients, impl {BACKEND_VERSION}",
                trained_on=(
                    "2874 measured aqueous solubilities (Delaney 2004); this "
                    "implementation reproduces the published coefficients and is checked "
                    "against an independent public reference set in CI"
                ),
                citations=(CITE_DELANEY_ESOL, _CITE_ESOL_DOMAIN),
                notes=(
                    "logS is an intrinsic aqueous solubility of the neutral species. It is "
                    "not a formulation solubility, not a dissolution rate, and not pH-adjusted."
                ),
            ),
        )

    @staticmethod
    def _logd(logp: float, mw: float) -> Prediction:
        """logD7.4 approximated by cLogP — exact only for a molecule with no ionizable group."""
        return Prediction(
            value=round(logp, 2),
            unit="logD7.4 (estimated)",
            uncertainty=Uncertainty.from_sigma(
                logp,
                1.5,
                basis=UncertaintyBasis.STATED_ESTIMATE,
                source=(
                    "order-of-magnitude judgement, not a measurement: for an ionizable "
                    "compound logD7.4 sits below cLogP by up to several log units, and this "
                    "approximation does not model that at all. The band is deliberately wide "
                    "and deliberately symmetric-and-wrong: the real error is one-sided"
                ),
            ),
            applicability=ApplicabilityDomain(
                verdict=Domain.BORDERLINE,
                checks={"mw_100_to_700": 100.0 <= mw <= 700.0},
                explanation=(
                    "neutral-species proxy: treat as cLogP. For any acid or base this is an "
                    "upper bound on logD7.4, not an estimate of it"
                ),
            ),
            provenance=Provenance(
                model="cLogP as a logD7.4 proxy",
                kind=ModelKind.HEURISTIC,
                version=BACKEND_VERSION,
                trained_on="not fitted — the underlying cLogP is Wildman-Crippen atomic contributions",
                citations=(),
                notes=(
                    "UNVALIDATED. No ionization model: substituting logP for logD is a "
                    "known-wrong simplification, kept because it is still useful for ranking "
                    "a neutral series and removed from nothing else."
                ),
            ),
            caveat="not an ionization-aware logD; unvalidated (docs/VALIDATION.md)",
        )

    @staticmethod
    def _herg(logp: float, mw: float, has_basic_n: bool) -> Prediction:
        """hERG liability rises with lipophilicity and a basic amine. A flag, not a safety result."""
        score = _logistic(1.1 * (logp - 3.0) + (1.2 if has_basic_n else -0.3))
        risk = "high" if score >= 0.66 else "medium" if score >= 0.33 else "low"
        return Prediction(
            value=risk,
            uncertainty=Uncertainty(
                basis=UncertaintyBasis.STATED_ESTIMATE,
                probability=score,
                source=(
                    "the probability is the logistic output of a two-term correlation, not a "
                    "calibrated probability — it has never been compared against measured "
                    "hERG IC50 data"
                ),
            ),
            applicability=ApplicabilityDomain.from_checks(
                {"mw_150_to_600": 150.0 <= mw <= 600.0, "clogp_-1_to_8": -1.0 <= logp <= 8.0}
            ),
            provenance=_heuristic_provenance(
                "hERG liability flag",
                "two known risk factors (lipophilicity, a protonatable amine) combined by hand",
            ),
            caveat=(
                "NOT a cardiac safety assessment. This flags a structural risk factor for "
                "follow-up; only an assay can answer the question it gestures at"
            ),
        )

    @staticmethod
    def _cyp3a4(logp: float, mw: float) -> Prediction:
        score = _logistic(0.9 * (logp - 2.8) + 0.004 * (mw - 350))
        risk = "high" if score >= 0.66 else "medium" if score >= 0.33 else "low"
        return Prediction(
            value=risk,
            uncertainty=Uncertainty(
                basis=UncertaintyBasis.STATED_ESTIMATE,
                probability=score,
                source="uncalibrated logistic output of a size + lipophilicity correlation",
            ),
            applicability=ApplicabilityDomain.from_checks(
                {"mw_150_to_700": 150.0 <= mw <= 700.0, "clogp_-1_to_8": -1.0 <= logp <= 8.0}
            ),
            provenance=_heuristic_provenance(
                "CYP3A4 substrate-likelihood flag",
                "CYP3A4 turnover tends to favour larger, more lipophilic substrates",
            ),
            caveat="not a drug-drug-interaction assessment; unvalidated",
        )

    @staticmethod
    def _metabolic_stability(logp: float, aromatic_rings: int, mw: float) -> Prediction:
        score = _logistic(0.8 * (logp - 3.0) + 0.4 * (aromatic_rings - 2))
        label = "low" if score >= 0.66 else "medium" if score >= 0.33 else "high"
        return Prediction(
            value=label,  # stability label (high = stable)
            uncertainty=Uncertainty(
                basis=UncertaintyBasis.STATED_ESTIMATE,
                probability=score,
                source=(
                    "uncalibrated: `probability` here is an instability score, not a predicted "
                    "clearance or half-life, and it maps to no experimental unit"
                ),
            ),
            applicability=ApplicabilityDomain.from_checks(
                {"mw_100_to_700": 100.0 <= mw <= 700.0, "clogp_-1_to_8": -1.0 <= logp <= 8.0}
            ),
            provenance=_heuristic_provenance(
                "metabolic stability flag",
                "lipophilic and aromatic-rich compounds tend toward faster CYP metabolism",
            ),
            caveat="no species, no matrix, no clearance units — a ranking signal only; unvalidated",
        )

    @staticmethod
    def _ppb(logp: float, mw: float) -> Prediction:
        fraction = _logistic(0.9 * (logp - 1.0))
        return Prediction(
            value=round(fraction, 3),
            unit="fraction bound",
            uncertainty=Uncertainty(
                basis=UncertaintyBasis.STATED_ESTIMATE,
                sigma=0.2,
                # Clamped to [0, 1] because the quantity is a fraction; an unclamped
                # normal band would report an impossible bound and look like a bug.
                interval=(max(0.0, fraction - 0.392), min(1.0, fraction + 0.392)),
                source=(
                    "stated estimate (±1.96 x 0.2, clamped to the physical range 0-1). PPB is "
                    "reported here on 0-1, where the decisions that depend on it turn on the "
                    "FREE fraction: the difference between 99% and 99.9% bound is a 10x change "
                    "in free drug, and a model with a ±0.2 band cannot resolve it at all"
                ),
            ),
            applicability=ApplicabilityDomain.from_checks(
                {"mw_100_to_700": 100.0 <= mw <= 700.0, "clogp_-1_to_8": -1.0 <= logp <= 8.0}
            ),
            provenance=_heuristic_provenance(
                "plasma protein binding flag",
                "binding to albumin broadly increases with lipophilicity",
            ),
            caveat="unvalidated; cannot resolve the high-binding region that matters most",
        )

    @staticmethod
    def _bbb(tpsa: float, mw: float, logp: float, hbd: int) -> Prediction:
        """A TPSA/MW/logP/HBD threshold rule for CNS penetration — a rule, not a regression."""
        checks = {
            "tpsa_lt_90": tpsa < 90.0,
            "mw_lt_450": mw < 450.0,
            "clogp_1_to_4": 1.0 < logp < 4.0,
            "hbd_le_3": hbd <= 3,
        }
        penetrant = all(checks.values())
        return Prediction(
            value=bool(penetrant),
            uncertainty=Uncertainty(
                basis=UncertaintyBasis.STATED_ESTIMATE,
                # Smooth score around the TPSA=90 boundary: a molecule at TPSA 89 and one
                # at 91 differ by nothing chemically, and a bare boolean hides that.
                probability=_logistic((90.0 - tpsa) / 25.0 + 0.3 * (logp - 2.0)),
                source=(
                    "the boolean is a threshold rule; `probability` is a smooth reading of "
                    "distance from the TPSA boundary, provided so a borderline compound is "
                    "visibly borderline rather than silently rounded to true or false"
                ),
            ),
            applicability=ApplicabilityDomain.from_checks(
                {"mw_lt_600": mw < 600.0, "clogp_-1_to_8": -1.0 <= logp <= 8.0}
            ),
            provenance=Provenance(
                model="CNS penetration threshold rule (TPSA / MW / cLogP / HBD)",
                kind=ModelKind.PUBLISHED_RULE,
                version=BACKEND_VERSION,
                trained_on=(
                    "not fitted — property thresholds of the kind established by the CNS "
                    "MPO literature; the exact cut-offs used here are this implementation's"
                ),
                citations=(CITE_TPSA,),
                notes=(
                    "Answers 'is this inside a property range associated with CNS "
                    "penetration', NOT 'what is the brain:plasma ratio'. It models passive "
                    "diffusion only: it knows nothing about efflux (P-gp), which is the usual "
                    "reason a compound that passes this rule still fails in vivo."
                ),
            ),
            caveat="no efflux model; a property-range rule, not a predicted brain:plasma ratio",
        )
