"""Deterministic chemistry core — the firewall and tools."""
from services.chemistry.generative import generate_analogs
from services.chemistry.properties import druglikeness, profile
from services.chemistry.validation import validate_and_canonicalize


def test_canonicalization_is_stable():
    a = validate_and_canonicalize("OC(=O)c1ccccc1")
    b = validate_and_canonicalize("c1ccccc1C(O)=O")
    assert a.valid and b.valid
    assert a.canonical_smiles == b.canonical_smiles
    assert a.inchikey == b.inchikey


def test_invalid_smiles_is_rejected_not_raised():
    r = validate_and_canonicalize("this-is-not-a-molecule((")
    assert r.valid is False
    assert r.canonical_smiles is None
    assert r.error


def test_salt_is_stripped():
    r = validate_and_canonicalize("CC(=O)O.[Na+]")
    assert r.valid
    assert "Na" not in r.canonical_smiles  # largest fragment kept


def test_profile_has_core_descriptors():
    p = profile("CC(=O)Oc1ccccc1C(=O)O")  # aspirin
    for key in ("mw", "logp", "tpsa", "hbd", "hba", "qed", "has_pains"):
        assert key in p
    assert 170 < p["mw"] < 190  # aspirin ~180


def test_druglikeness_flags_violations():
    dl = druglikeness({"mw": 600, "logp": 6, "hbd": 6, "hba": 12, "rotatable_bonds": 3, "tpsa": 50})
    assert dl["lipinski_violations"] == 4
    assert dl["lipinski_pass"] is False
    assert dl["veber_pass"] is True


def test_analog_generation_produces_valid_unique_structures():
    analogs = generate_analogs("c1ccccc1C(=O)O", max_analogs=10)
    assert len(analogs) > 0
    inchikeys = [a["inchikey"] for a in analogs]
    assert len(inchikeys) == len(set(inchikeys))  # de-duplicated
    for a in analogs:
        assert validate_and_canonicalize(a["smiles"]).valid  # every analog passes the firewall


def test_analog_generation_rejects_invalid_parent():
    try:
        generate_analogs("garbage((", max_analogs=5)
        assert False, "should have raised"
    except ValueError:
        pass
