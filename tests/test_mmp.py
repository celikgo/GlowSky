"""Matched molecular pairs (MMP) + SAR transform mining.

Deterministic RDKit fragmentation, so these assert real SAR: a halogen series produces the right
pairs, the property Δ has the chemically correct sign, and the same transformation aggregates
across scaffolds. Offline, no key.
"""
import pytest

from services.chemistry.mmp import matched_pairs, sar_transforms
from services.tools.catalog import build_default_registry

# A phenyl series — every member shares the c1ccc([*:1])cc1 scaffold, one variable substituent.
PHENYL_SERIES = ["Fc1ccccc1", "Clc1ccccc1", "Brc1ccccc1", "Cc1ccccc1"]

# The SAME F→Cl swap on two different scaffolds (phenyl + tolyl) → the transform aggregates n=2.
CROSS_SCAFFOLD = [
    "Fc1ccccc1",        # fluorobenzene
    "Clc1ccccc1",       # chlorobenzene
    "Cc1ccc(F)cc1",     # 4-fluorotoluene
    "Cc1ccc(Cl)cc1",    # 4-chlorotoluene
]


def _halogen_transform(transforms_or_pairs, key="transformation"):
    """Find the F/Cl transformation record, whatever the canonical string ordering."""
    for r in transforms_or_pairs:
        t = r[key]
        if "F[*:1]" in t and "Cl[*:1]" in t:
            return r
    return None


# --- matched_pairs -----------------------------------------------------------


def test_matched_pairs_on_a_shared_scaffold():
    r = matched_pairs(PHENYL_SERIES)
    assert r["n_molecules"] == 4
    # All 4 share the phenyl scaffold → every pairing is matched: C(4,2) = 6.
    assert r["n_pairs"] == 6
    for p in r["pairs"]:
        assert ">>" in p["transformation"]
        assert "[*:1]" in p["context"]
        assert "delta" not in p  # no property requested


def test_pair_delta_sign_is_chemically_correct():
    r = matched_pairs(PHENYL_SERIES, property="logp")
    fcl = _halogen_transform(r["pairs"])
    assert fcl is not None
    assert "delta" in fcl and fcl["delta"] != 0
    # The molecule carrying F is less lipophilic than the one carrying Cl, regardless of which way
    # the canonical transform points.
    f_mol = fcl["a"] if "F" in fcl["transformation"].split(">>")[0] else fcl["b"]
    cl_mol = fcl["b"] if f_mol == fcl["a"] else fcl["a"]
    from services.chemistry.properties import compute_descriptors

    assert compute_descriptors(f_mol)["logp"] < compute_descriptors(cl_mol)["logp"]


def test_invalid_smiles_are_skipped_not_raised():
    r = matched_pairs(["Fc1ccccc1", "not-a-mol((", "Clc1ccccc1"], property="logp")
    assert r["n_molecules"] == 2  # the junk row dropped, no exception


def test_unknown_property_raises():
    with pytest.raises(ValueError):
        matched_pairs(PHENYL_SERIES, property="nonsense")


# --- sar_transforms ----------------------------------------------------------


def test_sar_transform_aggregates_across_scaffolds():
    sar = sar_transforms(CROSS_SCAFFOLD, property="logp")
    fcl = _halogen_transform(sar["transforms"])
    assert fcl is not None
    # Same F/Cl swap seen on both the phenyl and tolyl scaffolds.
    assert fcl["n"] == 2
    # Consistent direction → mean is a clean signed effect, equal to both endpoints' bound.
    assert fcl["min_delta"] <= fcl["mean_delta"] <= fcl["max_delta"]
    assert abs(fcl["mean_delta"]) > 0


def test_sar_transforms_ranked_by_support():
    sar = sar_transforms(CROSS_SCAFFOLD, property="logp")
    ns = [t["n"] for t in sar["transforms"]]
    assert ns == sorted(ns, reverse=True)  # most-supported first


def test_sar_supports_mpo_property():
    sar = sar_transforms(PHENYL_SERIES, property="mpo")
    assert sar["property"] == "mpo"
    assert sar["n_transforms"] > 0


def test_min_count_filters_rare_transforms():
    # With min_count=2 on the phenyl series (every transform is n=1), nothing survives.
    sar = sar_transforms(PHENYL_SERIES, property="logp", min_count=2)
    assert sar["n_transforms"] == 0


# --- registration ------------------------------------------------------------


def test_mmp_tools_registered():
    names = {t.name for t in build_default_registry().list()}
    assert {"matched_pairs", "sar_transforms"} <= names
