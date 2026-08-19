"""The uncertainty vocabulary itself: intervals, domains, and the payload shape.

services/chemistry/provenance.py is what every predictor speaks through, so a defect
here is a defect in every number Glowsky reports at once. The arithmetic in particular
is worth pinning: an interval that is quietly too narrow is worse than no interval,
because it looks like a stronger claim than the model can support.
"""
from __future__ import annotations

import math

import pytest

from services.chemistry.provenance import (
    ApplicabilityDomain,
    Citation,
    Domain,
    ModelKind,
    Prediction,
    Provenance,
    Uncertainty,
    UncertaintyBasis,
    _erfinv,
)

# --- the interval arithmetic --------------------------------------------------------


@pytest.mark.parametrize(
    ("level", "expected_z"),
    [
        (0.90, 1.6448536),
        (0.95, 1.9599640),
        (0.99, 2.5758293),
    ],
)
def test_the_critical_value_is_right_at_every_level(level, expected_z):
    """z = sqrt(2) * erfinv(level). Python's stdlib has erf but not its inverse.

    These are the standard normal two-sided critical values. If this drifts, every
    confidence interval Glowsky displays is the wrong width — silently, and in the
    direction of looking more certain than it is.
    """
    assert math.sqrt(2) * _erfinv(level) == pytest.approx(expected_z, abs=1e-6)


def test_from_sigma_builds_a_symmetric_interval_around_the_value():
    u = Uncertainty.from_sigma(
        -4.21, 0.87, basis=UncertaintyBasis.MEASURED_BENCHMARK, source="test"
    )
    lo, hi = u.interval
    assert lo == pytest.approx(-4.21 - 1.959964 * 0.87, abs=1e-4)
    assert hi == pytest.approx(-4.21 + 1.959964 * 0.87, abs=1e-4)
    # The point estimate must lie inside its own band.
    assert lo < -4.21 < hi


def test_a_wider_confidence_level_gives_a_wider_interval():
    """Monotonicity, because an inverted comparison here would be invisible."""
    args = {"basis": UncertaintyBasis.STATED_ESTIMATE, "source": "test"}
    narrow = Uncertainty.from_sigma(0.0, 1.0, level=0.90, **args)
    wide = Uncertainty.from_sigma(0.0, 1.0, level=0.99, **args)
    assert wide.interval[1] > narrow.interval[1] > 0


# --- the applicability domain --------------------------------------------------------


def test_all_checks_passing_is_in_domain():
    ad = ApplicabilityDomain.from_checks({"a": True, "b": True})
    assert ad.verdict is Domain.IN


def test_one_failing_check_is_borderline_not_out():
    """A molecule just over one boundary is a different situation from one outside on
    several axes, and collapsing the two loses the distinction a chemist would make."""
    ad = ApplicabilityDomain.from_checks({"a": True, "b": False})
    assert ad.verdict is Domain.BORDERLINE
    assert "b" in ad.explanation


def test_two_failing_checks_are_out_of_domain_and_name_the_axes():
    ad = ApplicabilityDomain.from_checks({"a": False, "b": False})
    assert ad.verdict is Domain.OUT
    assert "a" in ad.explanation and "b" in ad.explanation


def test_a_model_with_no_domain_says_unknown_rather_than_claiming_one():
    ad = ApplicabilityDomain.not_defined("this rule states no domain")
    assert ad.verdict is Domain.UNKNOWN
    assert ad.checks == {}


# --- the payload shape ---------------------------------------------------------------


def _prediction(domain: ApplicabilityDomain, caveat: str | None = None) -> Prediction:
    return Prediction(
        value=1.0,
        provenance=Provenance(
            model="m",
            kind=ModelKind.PUBLISHED_QSPR,
            version="1",
            trained_on="data",
            citations=(Citation(reference="r", doi="10.0/x", url="https://doi.org/10.0/x"),),
        ),
        uncertainty=Uncertainty.from_sigma(
            1.0, 0.5, basis=UncertaintyBasis.MEASURED_BENCHMARK, source="s"
        ),
        applicability=domain,
        caveat=caveat,
    )


def test_an_out_of_domain_prediction_grows_a_caveat_even_if_none_was_set():
    """The caveat must reach the caller's payload, not just the documentation.

    A predictor that forgets to set one on an out-of-domain value would otherwise ship
    an unusable number that looks exactly like a usable one.
    """
    out = _prediction(ApplicabilityDomain.from_checks({"a": False, "b": False}))
    assert "caveat" in out.as_dict()
    assert "not for decision-making" in out.as_dict()["caveat"]


def test_an_in_domain_prediction_has_no_invented_caveat():
    ok = _prediction(ApplicabilityDomain.from_checks({"a": True}))
    assert "caveat" not in ok.as_dict()


def test_an_explicit_caveat_is_not_overwritten():
    out = _prediction(
        ApplicabilityDomain.from_checks({"a": False, "b": False}), caveat="specific reason"
    )
    assert out.as_dict()["caveat"] == "specific reason"


def test_the_payload_always_carries_all_three_fields():
    d = _prediction(ApplicabilityDomain.from_checks({"a": True})).as_dict()
    assert set(d) >= {"value", "uncertainty", "applicability_domain", "provenance"}
    assert d["provenance"]["citations"][0]["doi"] == "10.0/x"


def test_exact_uncertainty_is_available_for_quantities_that_have_none():
    """Descriptors like MW are exact. They must be able to say so rather than being
    given a fabricated band to satisfy a uniform shape."""
    u = Uncertainty.exact()
    assert u.basis is UncertaintyBasis.NOT_APPLICABLE
    assert u.as_dict() == {"basis": "not-applicable"}
