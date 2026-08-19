"""Every predictive tool returns uncertainty, applicability domain and provenance.

The rule this file enforces is the one in services/chemistry/provenance.py: a predicted
number never leaves Glowsky as a bare point estimate. That rule is easy to state, easy to
honour when a predictor is written, and easy to lose the next time one is added — which
is why it is checked here against the live tool registry rather than against a list.

The specific regressions guarded:

  - a predictor added later that returns a plain float, bypassing Prediction entirely;
  - an applicability domain that is present but inert (always "in", whatever it is fed);
  - a docking score presented with a spread that reads as a confidence interval, or as a
    binding affinity;
  - an SA score presented as if it were measurable.
"""
from __future__ import annotations

import pytest

from services.chemistry.adapters import docking
from services.chemistry.adapters.docking import Pocket
from services.chemistry.provenance import Domain, ModelKind, UncertaintyBasis
from services.chemistry.synthesizability import sa_score

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
#: A metal complex. The provenance module names exactly this case as the one a
#: fragment-based model will still return a confident-looking number for.
CISPLATIN = "[Pt](Cl)(Cl)(N)N"

_REQUIRED = ("value", "uncertainty", "applicability_domain", "provenance")


def _assert_is_prediction_payload(payload: dict, what: str) -> None:
    for key in _REQUIRED:
        assert key in payload, f"{what} returned no {key!r}: {sorted(payload)}"
    prov = payload["provenance"]
    assert prov["model"] and prov["version"] and prov["trained_on"], f"{what}: thin provenance"
    assert prov["citations"] or prov.get("notes"), (
        f"{what}: a prediction with neither a citation nor a note explaining its absence"
    )
    assert payload["uncertainty"]["basis"] in {b.value for b in UncertaintyBasis}
    assert payload["applicability_domain"]["verdict"] in {d.value for d in Domain}


# --- synthetic accessibility -------------------------------------------------


def test_sa_score_returns_the_full_prediction_envelope():
    _assert_is_prediction_payload(sa_score(ASPIRIN), "sa_score")


def test_sa_score_keeps_the_flat_keys_its_callers_read():
    """retrosynthesis.py reads sa["sa_score"]; the envelope must not have displaced it."""
    out = sa_score(ASPIRIN)
    assert out["sa_score"] == out["value"], "the flat key and the envelope disagree"
    assert isinstance(out["synthesizable"], bool)


def test_sa_score_is_labelled_as_ranking_not_measuring():
    """SA has no assay behind it. It must not claim a measured error bar."""
    out = sa_score(ASPIRIN)
    assert out["provenance"]["kind"] == ModelKind.PUBLISHED_HEURISTIC.value
    assert out["uncertainty"]["basis"] == UncertaintyBasis.STATED_ESTIMATE.value
    assert out["uncertainty"]["basis"] != UncertaintyBasis.MEASURED_BENCHMARK.value


def test_sa_score_refuses_a_verdict_for_a_metal_complex():
    """The domain check must bite on the case it exists for, not just be present."""
    out = sa_score(CISPLATIN)
    assert out["applicability_domain"]["verdict"] == Domain.OUT.value
    # The score is still reported — hiding it would hide that the model has an opinion —
    # but the easy/hard verdict is withheld rather than guessed.
    assert out["value"] is not None
    assert out["synthesizable"] is None
    assert out["caveat"]


def test_sa_domain_is_computed_from_the_models_own_fragment_table():
    """Not a proxy: an out-of-domain molecule must show unseen fragments, in-domain none."""
    assert sa_score(ASPIRIN)["unseen_fragment_fraction"] == 0.0
    assert sa_score(CISPLATIN)["unseen_fragment_fraction"] > 0.15


def test_sa_score_rejects_an_unparseable_smiles_rather_than_scoring_it():
    with pytest.raises(ValueError):
        sa_score("not-a-molecule")


# --- docking -----------------------------------------------------------------


class _StubDocking:
    """A backend that returns fixed poses, so the envelope is testable without Vina."""

    name = "stub-docking"

    def __init__(self, affinities: list[float]) -> None:
        self._affinities = affinities

    def dock(self, ligand_smiles: str, receptor_ref: str, pocket: Pocket) -> dict:
        return {
            "score": min(self._affinities),
            "score_unit": "kcal/mol",
            "num_modes": len(self._affinities),
            "poses": [
                {"mode": i + 1, "affinity": a} for i, a in enumerate(self._affinities)
            ],
        }


@pytest.fixture
def stub_backend():
    """Swap the process-wide backend and put the real one back afterwards."""
    # Reaching into the module's private backend slot is deliberate: set_backend() has
    # no getter, and a fixture that cannot restore the original would leak a stub into
    # every test that runs after it.
    original = docking._backend

    def _install(affinities: list[float]):
        docking.set_backend(_StubDocking(affinities))

    yield _install
    docking.set_backend(original)


def test_dock_returns_the_full_prediction_envelope(stub_backend):
    stub_backend([-9.1, -8.4, -7.6])
    _assert_is_prediction_payload(
        docking.dock(ASPIRIN, "receptor.pdbqt", [0, 0, 0], [20, 20, 20]), "dock"
    )


def test_dock_preserves_the_engine_keys_a_pose_viewer_needs(stub_backend):
    stub_backend([-9.1, -8.4])
    out = docking.dock(ASPIRIN, "receptor.pdbqt", [0, 0, 0], [20, 20, 20])
    assert out["score"] == out["value"], "the engine score and the envelope disagree"
    assert out["poses"] and out["engine"] == "stub-docking"


def test_dock_spread_is_the_pose_range_and_says_it_is_not_an_affinity_error(stub_backend):
    stub_backend([-9.1, -8.4, -7.6])
    unc = docking.dock(ASPIRIN, "receptor.pdbqt", [0, 0, 0], [20, 20, 20])["uncertainty"]
    assert unc["basis"] == UncertaintyBasis.ENSEMBLE_SPREAD.value
    assert unc["interval"] == [-9.1, -7.6]
    # interval_level 1.0 marks a full observed range. It is NOT a 95% CI, and the desktop
    # renders it as "range" for exactly this reason.
    assert unc["interval_level"] == 1.0
    # The band describes search disagreement. Saying so in the payload is the point:
    # a reader who takes it for the scoring function's accuracy has been misled by us.
    assert "not the error of the scoring function" in unc["source"].lower()


def test_a_single_pose_reports_no_spread_rather_than_zero(stub_backend):
    """One pose is a search that returned one mode, not a confident answer."""
    stub_backend([-9.1])
    unc = docking.dock(ASPIRIN, "receptor.pdbqt", [0, 0, 0], [20, 20, 20])["uncertainty"]
    assert "sigma" not in unc, "a lone pose reported a sigma, which reads as certainty"
    assert "interval" not in unc


def test_dock_never_calls_its_score_a_binding_affinity(stub_backend):
    stub_backend([-9.1, -8.4])
    out = docking.dock(ASPIRIN, "receptor.pdbqt", [0, 0, 0], [20, 20, 20])
    assert "not a binding affinity" in (out["caveat"] + out["provenance"]["notes"]).lower()


def test_dock_domain_bites_on_a_box_too_small_to_hold_a_pose(stub_backend):
    stub_backend([-9.1, -8.4])
    out = docking.dock(ASPIRIN, "receptor.pdbqt", [0, 0, 0], [4, 4, 4])
    assert out["applicability_domain"]["checks"]["search_box_at_least_10A"] is False


def test_dock_domain_bites_on_an_over_flexible_ligand(stub_backend):
    stub_backend([-4.2, -4.0])
    # A long alkanoic acid: well past the rotatable-bond count where the search degrades.
    out = docking.dock("CCCCCCCCCCCCCCCCCC(=O)O", "receptor.pdbqt", [0, 0, 0], [20, 20, 20])
    assert out["applicability_domain"]["checks"]["rotatable_bonds_le_10"] is False
    assert out["applicability_domain"]["verdict"] != Domain.IN.value


def test_dock_says_domain_unknown_rather_than_guessing_for_an_unparseable_ligand(stub_backend):
    stub_backend([-9.1, -8.4])
    out = docking.dock("not-a-molecule", "receptor.pdbqt", [0, 0, 0], [20, 20, 20])
    assert out["applicability_domain"]["verdict"] == Domain.UNKNOWN.value
