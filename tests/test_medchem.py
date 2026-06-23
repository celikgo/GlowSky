"""Medicinal-chemistry scoring — the MPO desirability score and the rule battery.

Deterministic RDKit math, so these assert real chemistry: known drugs pass the right rules, MPO
ranks drug-like ahead of greasy/oversized, profiles shift the sweet spot, and the design loop
ranks by MPO. Offline, no key.
"""
import pytest

from services.chemistry.medchem import (
    PROFILES,
    medchem_rules,
    mpo_from_descriptors,
    mpo_score,
)
from services.chemistry.properties import compute_descriptors
from services.tools.catalog import build_default_registry

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
CAFFEINE = "Cn1cnc2c1c(=O)n(C)c(=O)n2C"
# A deliberately oversized, greasy molecule (long alkyl chain) — should fail lead-like / Ro3 and
# score poorly on the oral MPO.
GREASY = "CCCCCCCCCCCCCCCCCCCCCC(=O)O"
# A small fragment.
FRAGMENT = "c1ccncc1"  # pyridine


# --- rule battery ------------------------------------------------------------


def test_rule_battery_shape():
    r = medchem_rules(ASPIRIN)
    expected = {"lipinski", "veber", "ghose", "egan", "muegge", "lead_like", "rule_of_three"}
    assert set(r["rules"]) == expected
    for rule in r["rules"].values():
        assert set(rule) == {"pass", "violations"}
    assert r["n_passed"] == len(r["passed"])
    assert "molar_refractivity" in r and "heteroatoms" in r


def test_aspirin_is_broadly_druglike():
    r = medchem_rules(ASPIRIN)
    # Aspirin is a small, friendly molecule — passes the core oral rules.
    assert r["rules"]["lipinski"]["pass"]
    assert r["rules"]["veber"]["pass"]
    assert r["rules"]["lead_like"]["pass"]


def test_greasy_molecule_fails_lead_and_fragment_rules():
    r = medchem_rules(GREASY)
    # Too lipophilic / too large for lead-like and fragment space; violations are reported.
    assert not r["rules"]["lead_like"]["pass"]
    assert not r["rules"]["rule_of_three"]["pass"]
    assert r["rules"]["lead_like"]["violations"]  # non-empty, human-readable reasons


def test_fragment_passes_rule_of_three():
    assert medchem_rules(FRAGMENT)["rules"]["rule_of_three"]["pass"]


def test_invalid_smiles_rejected():
    with pytest.raises(ValueError):
        medchem_rules("not-a-molecule((")


# --- MPO desirability --------------------------------------------------------


def test_mpo_score_shape_and_range():
    m = mpo_score(ASPIRIN)
    assert m["profile"] == "oral"
    assert 0.0 <= m["score"] <= 1.0
    assert m["limiting"] in m["desirability"]
    assert all(0.0 <= d <= 1.0 for d in m["desirability"].values())


def test_mpo_ranks_druglike_above_greasy():
    assert mpo_score(CAFFEINE)["score"] > mpo_score(GREASY)["score"]


def test_mpo_limiting_property_is_the_lowest():
    m = mpo_score(GREASY)
    worst = min(m["desirability"], key=lambda k: m["desirability"][k])
    assert m["limiting"] == worst
    # The greasy acid's weak axis is lipophilicity or size, not a polar term.
    assert m["limiting"] in ("logp", "mw", "fsp3", "aromatic_rings")


def test_mpo_profiles_shift_the_sweet_spot():
    # A small fragment scores better under the fragment profile than under the oral profile,
    # because the oral profile wants more mass than a fragment carries.
    desc = compute_descriptors(FRAGMENT)
    frag = mpo_from_descriptors(desc, "fragment")["score"]
    oral = mpo_from_descriptors(desc, "oral")["score"]
    assert frag > oral


def test_all_named_profiles_score():
    desc = compute_descriptors(ASPIRIN)
    for p in PROFILES:
        out = mpo_from_descriptors(desc, p)
        assert 0.0 <= out["score"] <= 1.0


def test_unknown_profile_raises():
    with pytest.raises(ValueError):
        mpo_from_descriptors(compute_descriptors(ASPIRIN), "nonsense")


# --- tool registration -------------------------------------------------------


def test_new_tools_are_registered():
    names = {t.name for t in build_default_registry().list()}
    assert {"mpo_score", "medchem_rules"} <= names
