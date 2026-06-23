"""Bioisosteric replacement + scaffold hopping.

Deterministic, knowledge-based transforms — so these assert real chemistry: a carboxylic acid
yields its classic bioisosteres, an aromatic ring yields its aza-analogs, and every product is a
valid, distinct structure (the firewall holds). Offline, no key.
"""
import pytest

from services.chemistry.bioisosteres import bioisosteric_analogs
from services.chemistry.validation import validate_and_canonicalize
from services.tools.catalog import build_default_registry

IBUPROFEN = "CC(C)Cc1ccc(C(C)C(=O)O)cc1"  # carboxylic acid + aromatic ring
ANISOLE = "COc1ccccc1"  # aryl ether
ETHANE = "CC"  # nothing to transform


def _mods(analogs):
    return {a["modification"] for a in analogs}


def test_carboxylic_acid_bioisosteres_are_generated():
    analogs = bioisosteric_analogs(IBUPROFEN, max_results=50)
    mods = _mods(analogs)
    # The classic acid bioisosteres all fire on ibuprofen's -COOH.
    assert {"acid->tetrazole", "acid->acylsulfonamide", "acid->hydroxamic", "acid->amide"} <= mods


def test_tetrazole_product_is_the_known_bioisostere():
    analogs = bioisosteric_analogs(IBUPROFEN, max_results=50)
    tet = next(a for a in analogs if a["modification"] == "acid->tetrazole")
    # Ibuprofen's acid → the 5-substituted tetrazole (CN4 ring), a real isostere.
    assert "n" in tet["smiles"] and tet["smiles"] != IBUPROFEN
    assert validate_and_canonicalize(tet["smiles"]).valid


def test_scaffold_hop_aza_walk_on_aromatic_ring():
    analogs = bioisosteric_analogs(IBUPROFEN, max_results=50)
    aza = [a for a in analogs if a["modification"] == "aza-walk"]
    assert aza  # benzene ring -> pyridine-type analogs
    for a in aza:
        assert "n" in a["smiles"]  # a ring nitrogen appeared


def test_ether_to_thioether():
    analogs = bioisosteric_analogs(ANISOLE)
    thio = next(a for a in analogs if a["modification"] == "ether->thioether")
    assert "S" in thio["smiles"]  # thioanisole


def test_all_products_valid_unique_and_exclude_parent():
    analogs = bioisosteric_analogs(IBUPROFEN, max_results=50)
    parent_key = validate_and_canonicalize(IBUPROFEN).inchikey
    keys = [a["inchikey"] for a in analogs]
    assert len(keys) == len(set(keys))  # de-duplicated
    assert parent_key not in keys  # parent excluded
    for a in analogs:
        assert validate_and_canonicalize(a["smiles"]).valid  # firewall held


def test_cap_is_respected():
    assert len(bioisosteric_analogs(IBUPROFEN, max_results=3)) == 3


def test_no_applicable_transform_returns_empty():
    assert bioisosteric_analogs(ETHANE) == []


def test_invalid_parent_raises():
    with pytest.raises(ValueError):
        bioisosteric_analogs("not-a-molecule((")


def test_tool_registered():
    names = {t.name for t in build_default_registry().list()}
    assert "bioisosteric_replacement" in names
