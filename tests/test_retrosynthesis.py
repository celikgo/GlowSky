"""Template-based retrosynthesis + synthesizability assessment.

Deterministic disconnections, so these assert real chemistry: known bonds disconnect into the
right precursors via the right named reaction, a fused aromatic has no handle, and the
synthesizability verdict combines SA score with route findability. Offline, no key.
"""
import pytest

from services.chemistry.retrosynthesis import retrosynthesize, synthesizability
from services.chemistry.validation import validate_and_canonicalize
from services.tools.catalog import build_default_registry

ACETANILIDE = "CC(=O)Nc1ccccc1"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
BIPHENYL = "c1ccc(-c2ccccc2)cc1"
NAPHTHALENE = "c1ccc2ccccc2c1"  # fused aromatic — no functional handle to disconnect


def _reactions(retro):
    return {d["reaction"] for d in retro["disconnections"]}


# --- retrosynthesize ---------------------------------------------------------


def test_amide_disconnects_to_acid_and_amine():
    r = retrosynthesize(ACETANILIDE)
    assert "amide coupling" in _reactions(r)
    d = next(d for d in r["disconnections"] if d["reaction"] == "amide coupling")
    # acetic acid + aniline
    assert "Nc1ccccc1" in d["precursors"]
    assert any("C(=O)O" in p or "C(O)=O" in p for p in d["precursors"])


def test_aspirin_is_an_esterification():
    r = retrosynthesize(ASPIRIN)
    assert "esterification" in _reactions(r)
    d = next(d for d in r["disconnections"] if d["reaction"] == "esterification")
    # acetic acid + salicylic acid — exactly how aspirin is made
    assert any("O" in p and "c1ccccc1" in p for p in d["precursors"])


def test_biaryl_is_a_suzuki_coupling():
    r = retrosynthesize(BIPHENYL)
    d = next(d for d in r["disconnections"] if d["reaction"] == "Suzuki coupling")
    # an aryl halide + an aryl boronic acid (canonical: OB(O)c1ccccc1)
    assert any("Br" in p for p in d["precursors"])
    assert any("B" in p and "O" in p for p in d["precursors"])  # boronic acid


def test_fused_aromatic_has_no_disconnection():
    r = retrosynthesize(NAPHTHALENE)
    assert r["n_disconnections"] == 0


def test_all_precursors_are_valid():
    for smi in (ACETANILIDE, ASPIRIN, BIPHENYL):
        for d in retrosynthesize(smi)["disconnections"]:
            for p in d["precursors"]:
                assert validate_and_canonicalize(p).valid


def test_routes_to_building_blocks_sort_first():
    r = retrosynthesize(ACETANILIDE)
    flags = [d["all_building_blocks"] for d in r["disconnections"]]
    assert flags == sorted(flags, reverse=True)  # all-purchasable disconnections first


def test_invalid_target_raises():
    with pytest.raises(ValueError):
        retrosynthesize("not-a-molecule((")


# --- synthesizability --------------------------------------------------------


def test_synthesizability_finds_a_route_for_a_simple_drug():
    s = synthesizability(ASPIRIN)
    assert s["route_found"] is True
    assert s["sa_label"] == "easy"
    assert s["best_disconnection"]["reaction"] == "esterification"
    assert "viable" in s["assessment"]


def test_synthesizability_reports_no_route_honestly():
    s = synthesizability(NAPHTHALENE)
    assert s["route_found"] is False
    assert s["best_disconnection"] is None
    assert "no recognised one-step disconnection" in s["assessment"]


def test_synthesizability_carries_sa_and_label():
    s = synthesizability(ACETANILIDE)
    assert "sa_score" in s and s["sa_label"] in ("easy", "moderate", "hard")
    assert isinstance(s["synthesizable"], bool)


# --- registration ------------------------------------------------------------


def test_tools_registered():
    names = {t.name for t in build_default_registry().list()}
    assert {"retrosynthesize", "synthesizability"} <= names
