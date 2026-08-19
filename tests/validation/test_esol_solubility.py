"""Validation: the ESOL solubility model against Delaney's published measurements.

WHAT IS BEING VALIDATED
    That Glowsky's implementation of the ESOL regression, applied to 1128 compounds
    with MEASURED aqueous solubilities, reproduces those measurements to a stated
    accuracy — and that the accuracy does not silently degrade.

WHY THIS IS THE TEST THAT MATTERS
    tests/test_backends.py already checks that solubility returns a number in a
    plausible range for aspirin. That test would pass if every coefficient in the
    model were wrong by 20%. This one would not.

WHAT THIS IS NOT
    It is not a claim that Glowsky predicts solubility well. Read the numbers: the
    RMSE is on the order of one log unit, which is a factor of ten in concentration.
    That is the accuracy of the published model itself, and it is the reason the
    predictor reports an interval rather than a point. This test establishes that the
    error is the KNOWN error and not a larger one hiding in an implementation bug.

    It is also not an independent test set. The Delaney compilation includes the
    compounds the ESOL coefficients were fitted on, so this measures reproduction of
    a published model on its own domain, not generalisation to new chemistry. Stated
    plainly here and in docs/VALIDATION.md rather than left for a reader to discover.
"""
from __future__ import annotations

import pytest
from rdkit import Chem, RDLogger

from services.chemistry.adapters.admet_rdkit import ESOL_MEASURED_RMSE, RDKitQSPRADMET
from tests.validation._harness import (
    ValidationResult,
    environment,
    mae,
    r_squared,
    read_reference_csv,
    rmse,
)

RDLogger.DisableLog("rdApp.*")

# --- gates -------------------------------------------------------------------------
#
# Set just above the measured values, with enough headroom that they do not flap on a
# harmless RDKit descriptor change, and tight enough that a real regression trips them.
# The measured values at the time of writing are in the comment beside each one; if a
# change moves any of these, the honest response is to investigate, and only then to
# move the gate and update docs/VALIDATION.md.

RMSE_CEILING = 1.15          # measured: 1.0994
MAE_CEILING = 0.90           # measured: 0.8439
R2_FLOOR = 0.70              # measured: 0.7247
ABS_BIAS_CEILING = 0.35      # measured: +0.2782
WITHIN_1_LOG_FLOOR = 0.65    # measured: 0.681

_SOURCE = (
    "Delaney, J. S., J. Chem. Inf. Comput. Sci. 44(3), 1000-1005 (2004); retrieved via "
    "MoleculeNet (Wu et al., Chem. Sci. 9, 513-530, 2018)"
)
_SOURCE_URL = "https://doi.org/10.1021/ci034243x"


@pytest.fixture(scope="module")
def comparison() -> dict:
    """Predict every reference compound once; the assertions below all read this."""
    backend = RDKitQSPRADMET()
    measured: list[float] = []
    predicted: list[float] = []
    unparseable: list[str] = []

    for row in read_reference_csv("delaney_esol_solubility.csv"):
        smiles = row["smiles"]
        if Chem.MolFromSmiles(smiles) is None:
            # Recorded rather than silently skipped: a reference row this repository
            # cannot even parse is a fact about the chemistry toolkit, and burying it
            # would let coverage of the benchmark quietly shrink over time.
            unparseable.append(row["compound_id"])
            continue
        measured.append(float(row["measured_log_solubility_mol_per_l"]))
        predicted.append(backend.predict(smiles, ["solubility"])["solubility"]["value"])

    errors = [p - m for m, p in zip(measured, predicted, strict=True)]
    n = len(errors)
    return {
        "n": n,
        "unparseable": unparseable,
        "measured": measured,
        "predicted": predicted,
        "errors": errors,
        "rmse": rmse(errors),
        "mae": mae(errors),
        "bias": sum(errors) / n,
        "r2": r_squared(measured, predicted),
        "within_1_log": sum(1 for e in errors if abs(e) <= 1.0) / n,
    }


def test_the_whole_reference_set_is_parseable(comparison):
    """Every reference compound must be usable, or the benchmark is quietly shrinking."""
    assert not comparison["unparseable"], (
        f"{len(comparison['unparseable'])} reference compounds no longer parse: "
        f"{comparison['unparseable'][:10]}"
    )
    assert comparison["n"] == 1128, (
        f"expected the full 1128-compound reference set, compared {comparison['n']}"
    )


def test_esol_reproduces_measured_solubility_within_the_published_error(comparison):
    """The headline gate: agreement with 1128 measured values."""
    assert comparison["rmse"] <= RMSE_CEILING, (
        f"RMSE {comparison['rmse']:.4f} exceeds the {RMSE_CEILING} ceiling — the "
        f"solubility model has regressed against Delaney's measurements"
    )
    assert comparison["mae"] <= MAE_CEILING, f"MAE {comparison['mae']:.4f} > {MAE_CEILING}"
    assert comparison["r2"] >= R2_FLOOR, f"R^2 {comparison['r2']:.4f} < {R2_FLOOR}"


def test_esol_is_not_systematically_biased(comparison):
    """A model can hit its RMSE while being wrong in one direction throughout.

    RMSE alone cannot see that. Bias can, and a drifting bias is the signature of a
    coefficient or a descriptor changing underneath the model.
    """
    assert abs(comparison["bias"]) <= ABS_BIAS_CEILING, (
        f"mean signed error {comparison['bias']:+.4f} exceeds ±{ABS_BIAS_CEILING}"
    )


def test_most_predictions_land_within_one_log_unit(comparison):
    """The chemist-facing statement of accuracy, rather than a summary statistic."""
    assert comparison["within_1_log"] >= WITHIN_1_LOG_FLOOR, (
        f"only {comparison['within_1_log']:.1%} of predictions within 1 log unit "
        f"(floor {WITHIN_1_LOG_FLOOR:.0%})"
    )


def test_the_published_uncertainty_matches_the_measured_error(comparison):
    """The error bar the predictor SHOWS must be the error it actually HAS.

    ESOL_MEASURED_RMSE is what services/chemistry/adapters/admet_rdkit.py uses to build
    every solubility confidence interval it returns. If that constant and this
    measurement drift apart, then Glowsky is displaying an uncertainty it cannot
    support — which is the specific failure this whole validation suite exists to
    prevent. Tolerance is tight on purpose.
    """
    measured_rmse = comparison["rmse"]
    assert abs(ESOL_MEASURED_RMSE - measured_rmse) <= 0.05, (
        f"admet_rdkit.ESOL_MEASURED_RMSE is {ESOL_MEASURED_RMSE} but the measured RMSE "
        f"is {measured_rmse:.4f}. The published confidence interval would be wrong. "
        f"Update the constant to the measured value and regenerate docs/VALIDATION.md."
    )


def test_record_result_for_the_validation_report(comparison):
    """Publish this benchmark's outcome into docs/VALIDATION.md."""
    passed = (
        comparison["rmse"] <= RMSE_CEILING
        and comparison["mae"] <= MAE_CEILING
        and comparison["r2"] >= R2_FLOOR
        and abs(comparison["bias"]) <= ABS_BIAS_CEILING
        and comparison["within_1_log"] >= WITHIN_1_LOG_FLOOR
    )
    ValidationResult(
        capability="ADMET — aqueous solubility (logS)",
        model=(
            "ESOL (Delaney 2004 coefficients), as implemented in "
            "services/chemistry/adapters/admet_rdkit.py"
        ),
        benchmark="Delaney / ESOL compilation, 1128 measured aqueous solubilities",
        source=_SOURCE,
        source_url=_SOURCE_URL,
        n=comparison["n"],
        metrics={
            "rmse_log_units": round(comparison["rmse"], 4),
            "mae_log_units": round(comparison["mae"], 4),
            "r_squared": round(comparison["r2"], 4),
            "mean_signed_error": round(comparison["bias"], 4),
            "fraction_within_1_log": round(comparison["within_1_log"], 4),
        },
        gates={
            "rmse_log_units": f"<= {RMSE_CEILING}",
            "mae_log_units": f"<= {MAE_CEILING}",
            "r_squared": f">= {R2_FLOOR}",
            "mean_signed_error": f"|x| <= {ABS_BIAS_CEILING}",
            "fraction_within_1_log": f">= {WITHIN_1_LOG_FLOOR}",
        },
        passed=passed,
        notes=(
            "Reproduction of a published model on its own domain, NOT generalisation: the "
            "Delaney compilation includes the compounds ESOL was fitted on. An RMSE near one "
            "log unit is a factor of ten in concentration, which is why the predictor returns "
            "an interval rather than a point estimate. The measured RMSE here is the value "
            "used to build every solubility confidence interval Glowsky reports."
        ),
        environment=environment(),
    ).record()
    assert passed
