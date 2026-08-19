"""The vocabulary every Glowsky prediction speaks: uncertainty, applicability domain, provenance.

Glowsky's founding rule is that the molecule is never a model-generated string — it is
validated, canonicalized and deterministic. This module extends that same discipline to
the NUMBERS attached to a molecule, which is the harder half.

A predicted property presented as a bare point estimate is worse than no number at all.
"logS = -4.21" reads like a measurement. It is not one: it is the output of a linear
regression fitted to a few thousand compounds two decades ago, and its honest form is

    logS = -4.21 ± 1.71 (95%), inside the fitted domain,
           by ESOL (Delaney 2004), as implemented here and measured against
           <benchmark> in docs/VALIDATION.md

Three things make the difference, and every predictor in this package returns all three:

  applicability domain  Is this molecule the KIND of molecule the model was fitted on?
                        A regression fitted on drug-like organics will still return a
                        number for a metal complex or a 2 kDa peptide. That number is
                        meaningless, and only the model knows why.

  uncertainty           A band, not a point. Where the band comes from is itself
                        recorded (`basis`), because "±1.71 from the residual spread we
                        measured in CI" and "±1.71 because the author said so" are
                        different claims and a chemist is entitled to tell them apart.

  provenance            Which model, which version, fitted on what, and a citation that
                        resolves. `.github/workflows/docs-links.yml` checks the URLs in
                        this package on every push, so a citation that rots fails a build.

WHAT THIS IS NOT
----------------
Nothing in this module, and nothing that returns a Prediction, is a measurement. These
are triage and prioritisation aids: they exist to help a chemist decide which compound
to make next, and they carry their uncertainty precisely so that decision is made with
open eyes. They are not a substitute for an assay, they are not a regulatory or safety
assessment, and they must not be used as one.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum


class ModelKind(str, Enum):
    """What sort of thing produced a number — the first question about any prediction."""

    #: A regression or classifier fitted to measured data and published with its error.
    #: Carries a real, quotable uncertainty.
    PUBLISHED_QSPR = "published-qspr"
    #: A published threshold rule (Lipinski, Veber, Ro3). Not fitted, not predictive of a
    #: continuous quantity; it answers "is this inside a range someone published".
    PUBLISHED_RULE = "published-rule"
    #: A published substructure alert catalogue (PAINS, BRENK). Deterministic pattern
    #: matching — the uncertainty is in what a match MEANS, not in whether it matched.
    SUBSTRUCTURE_ALERT = "substructure-alert"
    #: A physics-based search-and-score engine (docking). Reproducible given a seed;
    #: its score is not a free energy.
    PHYSICS_ENGINE = "physics-engine"
    #: An in-house correlation with no published validation behind THIS parameterisation.
    #: The weakest class, and the one that must be labelled loudest.
    HEURISTIC = "heuristic"
    #: A deterministic descriptor computed from the graph (MW, TPSA, ring count). Exact
    #: for a given structure — the only class with genuinely no predictive uncertainty.
    DETERMINISTIC_DESCRIPTOR = "deterministic-descriptor"


class Domain(str, Enum):
    """Whether the molecule is the kind of molecule the model was built for."""

    IN = "in"                  #: inside the fitted/stated domain
    BORDERLINE = "borderline"  #: at the edge; the number is directional at best
    OUT = "out"                #: outside it — the value should not be used
    UNKNOWN = "unknown"        #: the model does not define a domain (say so, don't guess)


class UncertaintyBasis(str, Enum):
    """WHERE an uncertainty band came from. Not decoration — it is the band's warrant."""

    #: Measured by this repository's own validation suite against a public benchmark,
    #: regenerated in CI. The strongest basis, because it is reproducible from this tree.
    MEASURED_BENCHMARK = "measured-against-benchmark"
    #: The error the model's own publication reports.
    PUBLISHED_ERROR = "published-by-source"
    #: Spread across an ensemble of models or replicate runs.
    ENSEMBLE_SPREAD = "ensemble-spread"
    #: An order-of-magnitude judgement. Honest label for a heuristic: it says
    #: "this is roughly how wrong this can be", and claims nothing more.
    STATED_ESTIMATE = "stated-estimate"
    #: The quantity is exact given the structure (a descriptor, a rule outcome).
    NOT_APPLICABLE = "not-applicable"


@dataclass(frozen=True)
class Citation:
    """A source that can be looked up. `url` is link-checked in CI."""

    reference: str            #: human-readable, e.g. "Delaney, J. Chem. Inf. Comput. Sci. 2004"
    doi: str | None = None
    url: str | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class Provenance:
    """Which model produced a number, and on what authority."""

    model: str                       #: "ESOL", "AutoDock Vina", "Ertl SA score"
    kind: ModelKind
    version: str                     #: the model/implementation version, not Glowsky's
    trained_on: str                  #: the fitting set, or an explicit "not fitted"
    citations: tuple[Citation, ...] = ()
    #: Anything a reader needs in order to reproduce or distrust this specific number.
    notes: str | None = None

    def as_dict(self) -> dict:
        out = {
            "model": self.model,
            "kind": self.kind.value,
            "version": self.version,
            "trained_on": self.trained_on,
            "citations": [c.as_dict() for c in self.citations],
        }
        if self.notes:
            out["notes"] = self.notes
        return out


@dataclass(frozen=True)
class Uncertainty:
    """An uncertainty band and the warrant for it.

    ``sigma`` is a 1-sigma spread in the value's own units. ``interval`` is the reported
    band (95% by default). A classifier reports ``probability`` instead of an interval.
    """

    basis: UncertaintyBasis
    sigma: float | None = None
    interval: tuple[float, float] | None = None
    interval_level: float = 0.95
    probability: float | None = None
    #: Where the number in `sigma` came from, in one line. Required whenever sigma is set —
    #: an error bar with no stated origin is decoration.
    source: str | None = None

    def as_dict(self) -> dict:
        out: dict = {"basis": self.basis.value}
        if self.sigma is not None:
            out["sigma"] = round(self.sigma, 4)
        if self.interval is not None:
            out["interval"] = [round(self.interval[0], 4), round(self.interval[1], 4)]
            out["interval_level"] = self.interval_level
        if self.probability is not None:
            out["probability"] = round(self.probability, 4)
        if self.source:
            out["source"] = self.source
        return out

    @classmethod
    def from_sigma(
        cls,
        value: float,
        sigma: float,
        *,
        basis: UncertaintyBasis,
        source: str,
        level: float = 0.95,
    ) -> Uncertainty:
        """Build a symmetric normal interval around ``value``.

        Assumes the residuals are roughly normal, which is what an RMSE-shaped error
        summary already assumes. For a skewed endpoint this over-promises symmetry, so a
        predictor whose residuals are not symmetric should construct the interval itself
        rather than call this.
        """
        # 1.959963985 for 95%; computed rather than hardcoded so `level` means something.
        z = math.sqrt(2.0) * _erfinv(level)
        return cls(
            basis=basis,
            sigma=sigma,
            interval=(value - z * sigma, value + z * sigma),
            interval_level=level,
            source=source,
        )

    @classmethod
    def exact(cls) -> Uncertainty:
        """For a quantity that is exact given the structure (MW, ring count, a rule outcome)."""
        return cls(basis=UncertaintyBasis.NOT_APPLICABLE)


def _erfinv(p: float) -> float:
    """Inverse error function at the two-sided level ``p`` — i.e. erfinv(p) for z = sqrt(2)*erfinv(p).

    Python's stdlib has erf but not its inverse. Newton refinement on math.erf converges in
    a handful of iterations over the range of confidence levels anyone asks for, and keeps
    this module dependency-free (it is imported by every predictor).
    """
    # Bisection: erf is strictly increasing on [0, 4], which covers p up to 1 - 1e-8.
    # 80 halvings take the bracket well below double precision, so this is exact for
    # any confidence level anyone asks for.
    lo, hi = 0.0, 4.0
    x = 0.0
    for _ in range(80):
        x = 0.5 * (lo + hi)
        if math.erf(x) < p:
            lo = x
        else:
            hi = x
    return x


@dataclass(frozen=True)
class ApplicabilityDomain:
    """Is this molecule the kind of molecule the model was built for?

    ``checks`` records each individual criterion and whether the molecule met it, so a
    chemist reading an "out" verdict can see WHICH property put it there rather than
    being told only that the model declined.
    """

    verdict: Domain
    #: criterion name -> passed?
    checks: dict[str, bool] = field(default_factory=dict)
    #: One line a chemist can act on.
    explanation: str = ""

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "checks": dict(self.checks),
            "explanation": self.explanation,
        }

    @classmethod
    def from_checks(
        cls, checks: dict[str, bool], *, borderline_if_one_fails: bool = True
    ) -> ApplicabilityDomain:
        """Derive a verdict from named criteria.

        All pass -> IN. Exactly one fails and ``borderline_if_one_fails`` -> BORDERLINE:
        a molecule just over a single boundary is a different situation from one that is
        outside on several axes at once, and flattening the two loses the distinction a
        chemist would actually make. Two or more -> OUT.
        """
        failed = [name for name, ok in checks.items() if not ok]
        if not failed:
            return cls(Domain.IN, checks, "inside the model's stated domain")
        if len(failed) == 1 and borderline_if_one_fails:
            return cls(
                Domain.BORDERLINE,
                checks,
                f"outside the model's domain on one axis ({failed[0]}); treat as directional",
            )
        return cls(
            Domain.OUT,
            checks,
            "outside the model's domain on "
            f"{len(failed)} axes ({', '.join(failed)}); the value should not be used",
        )

    @classmethod
    def not_defined(cls, why: str) -> ApplicabilityDomain:
        """For a model that defines no domain. Says so, instead of inventing one."""
        return cls(Domain.UNKNOWN, {}, why)


@dataclass(frozen=True)
class Prediction:
    """A predicted value with everything needed to judge it.

    This is the shape every predictive tool in Glowsky returns, and the shape the desktop
    app renders. ``value`` is deliberately last in importance: a caller that reads only
    ``value`` and ignores the rest has reduced a prediction back to the bare number this
    whole module exists to prevent.
    """

    value: float | str | bool | None
    provenance: Provenance
    uncertainty: Uncertainty
    applicability: ApplicabilityDomain
    unit: str | None = None
    #: Set when the value must not be used as-is (out of domain, backend not configured).
    caveat: str | None = None
    #: Endpoint-specific derived quantities (e.g. mg/mL alongside logS). These inherit the
    #: prediction's uncertainty and must never be presented as separately-known values.
    extra: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        out: dict = {
            "value": self.value,
            "uncertainty": self.uncertainty.as_dict(),
            "applicability_domain": self.applicability.as_dict(),
            "provenance": self.provenance.as_dict(),
        }
        if self.unit:
            out["unit"] = self.unit
        out.update(self.extra)
        # A value the caller should not act on says so in the payload, not only in docs.
        caveat = self.caveat
        if caveat is None and self.applicability.verdict is Domain.OUT:
            caveat = (
                "outside the model's applicability domain — reported for transparency, "
                "not for decision-making"
            )
        if caveat:
            out["caveat"] = caveat
        return out


# --- the citations this package uses -----------------------------------------------
# Every DOI here was verified against the Crossref API, and every URL is re-checked on
# each push by .github/workflows/docs-links.yml.

CITE_DELANEY_ESOL = Citation(
    reference=(
        "Delaney, J. S. 'ESOL: Estimating Aqueous Solubility Directly from Molecular "
        "Structure.' J. Chem. Inf. Comput. Sci. 44(3), 1000-1005 (2004)"
    ),
    doi="10.1021/ci034243x",
    url="https://doi.org/10.1021/ci034243x",
)

CITE_ERTL_SA = Citation(
    reference=(
        "Ertl, P. & Schuffenhauer, A. 'Estimation of synthetic accessibility score of "
        "drug-like molecules based on molecular complexity and fragment contributions.' "
        "J. Cheminform. 1(1), 8 (2009)"
    ),
    doi="10.1186/1758-2946-1-8",
    url="https://doi.org/10.1186/1758-2946-1-8",
)

CITE_VINA_2010 = Citation(
    reference=(
        "Trott, O. & Olson, A. J. 'AutoDock Vina: Improving the speed and accuracy of "
        "docking with a new scoring function, efficient optimization, and multithreading.' "
        "J. Comput. Chem. 31(2), 455-461 (2010)"
    ),
    doi="10.1002/jcc.21334",
    url="https://doi.org/10.1002/jcc.21334",
)

CITE_VINA_2021 = Citation(
    reference=(
        "Eberhardt, J., Santos-Martins, D., Tillack, A. F. & Forli, S. 'AutoDock Vina "
        "1.2.0: New Docking Methods, Expanded Force Field, and Python Bindings.' "
        "J. Chem. Inf. Model. 61(8), 3891-3898 (2021)"
    ),
    doi="10.1021/acs.jcim.1c00203",
    url="https://doi.org/10.1021/acs.jcim.1c00203",
)

CITE_LIPINSKI = Citation(
    reference=(
        "Lipinski, C. A., Lombardo, F., Dominy, B. W. & Feeney, P. J. 'Experimental and "
        "computational approaches to estimate solubility and permeability in drug "
        "discovery and development settings.' Adv. Drug Deliv. Rev. 23(1-3), 3-25 (1997)"
    ),
    doi="10.1016/S0169-409X(96)00423-1",
    url="https://doi.org/10.1016/S0169-409X(96)00423-1",
)

CITE_VEBER = Citation(
    reference=(
        "Veber, D. F. et al. 'Molecular Properties That Influence the Oral "
        "Bioavailability of Drug Candidates.' J. Med. Chem. 45(12), 2615-2623 (2002)"
    ),
    doi="10.1021/jm020017n",
    url="https://doi.org/10.1021/jm020017n",
)

CITE_GHOSE = Citation(
    reference=(
        "Ghose, A. K., Viswanadhan, V. N. & Wendoloski, J. J. 'A Knowledge-Based "
        "Approach in Designing Combinatorial or Medicinal Chemistry Libraries for Drug "
        "Discovery.' J. Comb. Chem. 1(1), 55-68 (1998)"
    ),
    doi="10.1021/cc9800071",
    url="https://doi.org/10.1021/cc9800071",
)

CITE_EGAN = Citation(
    reference=(
        "Egan, W. J., Merz, K. M. & Baldwin, J. J. 'Prediction of Drug Absorption Using "
        "Multivariate Statistics.' J. Med. Chem. 43(21), 3867-3877 (2000)"
    ),
    doi="10.1021/jm000292e",
    url="https://doi.org/10.1021/jm000292e",
)

CITE_MUEGGE = Citation(
    reference=(
        "Muegge, I., Heald, S. L. & Brittelli, D. 'Simple Selection Criteria for "
        "Drug-like Chemical Matter.' J. Med. Chem. 44(12), 1841-1846 (2001)"
    ),
    doi="10.1021/jm015507e",
    url="https://doi.org/10.1021/jm015507e",
)

CITE_CONGREVE_RO3 = Citation(
    reference=(
        "Congreve, M., Carr, R., Murray, C. & Jhoti, H. 'A rule of three for fragment-"
        "based lead discovery?' Drug Discov. Today 8(19), 876-877 (2003)"
    ),
    doi="10.1016/S1359-6446(03)02831-9",
    url="https://doi.org/10.1016/S1359-6446(03)02831-9",
)

CITE_QED = Citation(
    reference=(
        "Bickerton, G. R., Paolini, G. V., Besnard, J., Muresan, S. & Hopkins, A. L. "
        "'Quantifying the chemical beauty of drugs.' Nat. Chem. 4(2), 90-98 (2012)"
    ),
    doi="10.1038/nchem.1243",
    url="https://doi.org/10.1038/nchem.1243",
)

CITE_PAINS = Citation(
    reference=(
        "Baell, J. B. & Holloway, G. A. 'New Substructure Filters for Removal of Pan "
        "Assay Interference Compounds (PAINS) from Screening Libraries and for Their "
        "Exclusion in Bioassays.' J. Med. Chem. 53(7), 2719-2740 (2010)"
    ),
    doi="10.1021/jm901137j",
    url="https://doi.org/10.1021/jm901137j",
)

CITE_BRENK = Citation(
    reference=(
        "Brenk, R. et al. 'Lessons Learnt from Assembling Screening Libraries for Drug "
        "Discovery for Neglected Diseases.' ChemMedChem 3(3), 435-444 (2008)"
    ),
    doi="10.1002/cmdc.200700139",
    url="https://doi.org/10.1002/cmdc.200700139",
)

CITE_CRIPPEN_LOGP = Citation(
    reference=(
        "Wildman, S. A. & Crippen, G. M. 'Prediction of Physicochemical Parameters by "
        "Atomic Contributions.' J. Chem. Inf. Comput. Sci. 39(5), 868-873 (1999)"
    ),
    doi="10.1021/ci990307l",
    url="https://doi.org/10.1021/ci990307l",
)

CITE_TPSA = Citation(
    reference=(
        "Ertl, P., Rohde, B. & Selzer, P. 'Fast Calculation of Molecular Polar Surface "
        "Area as a Sum of Fragment-Based Contributions and Its Application to the "
        "Prediction of Drug Transport Properties.' J. Med. Chem. 43(20), 3714-3717 (2000)"
    ),
    doi="10.1021/jm000942e",
    url="https://doi.org/10.1021/jm000942e",
)

CITE_CNS_MPO = Citation(
    reference=(
        "Wager, T. T., Hou, X., Verhoest, P. R. & Villalobos, A. 'Moving beyond Rules: "
        "The Development of a Central Nervous System Multiparameter Optimization (CNS "
        "MPO) Approach...' ACS Chem. Neurosci. 1(6), 435-449 (2010)"
    ),
    doi="10.1021/cn100008c",
    url="https://doi.org/10.1021/cn100008c",
)
