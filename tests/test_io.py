"""Molecule I/O: SMILES/CSV/SDF round-trips through the firewall, and diff."""
from __future__ import annotations

from services.chemistry import io as chem_io

# --- parsing (every structure passes the firewall) ----------------------------


def test_parse_smiles_with_optional_names():
    parsed = chem_io.parse_smiles("c1ccccc1 benzene\nCCO ethanol\n# comment\n\nCC")
    assert [p.valid for p in parsed] == [True, True, True]
    assert parsed[0].name == "benzene"
    assert parsed[0].canonical_smiles == "c1ccccc1"
    assert parsed[2].name is None  # bare SMILES, no name


def test_parse_smiles_flags_garbage_without_failing_the_batch():
    parsed = chem_io.parse_smiles("CCO\ngarbage((\nc1ccccc1")
    assert [p.valid for p in parsed] == [True, False, True]
    assert parsed[1].error  # human-readable reason, not an exception


def test_parse_csv_carries_extra_columns_as_properties():
    csv_text = "SMILES,Name,IC50\nCCO,ethanol,12.5\nc1ccccc1,benzene,3.1\n"
    parsed = chem_io.parse_csv(csv_text)
    assert len(parsed) == 2
    assert parsed[0].name == "ethanol"
    assert parsed[0].properties["IC50"] == "12.5"  # non-structural column preserved


def test_parse_csv_requires_a_smiles_column():
    import pytest
    with pytest.raises(ValueError):
        chem_io.parse_csv("name,value\nfoo,1\n")


def test_sdf_round_trip_preserves_structure_and_tags():
    rows = [chem_io.ExportRow(canonical_smiles="c1ccccc1", name="benzene",
                              properties={"batch": "A1"})]
    sdf = chem_io.to_sdf(rows)
    assert "benzene" in sdf and "batch" in sdf
    reparsed = chem_io.parse_sdf(sdf)
    assert reparsed[0].valid
    assert reparsed[0].canonical_smiles == "c1ccccc1"
    assert reparsed[0].properties.get("batch") == "A1"


def test_csv_export_has_stable_columns():
    rows = [
        chem_io.ExportRow("CCO", "ethanol", {"IC50": "12.5"}),
        chem_io.ExportRow("c1ccccc1", "benzene", {"logD": "2.1"}),
    ]
    csv_text = chem_io.to_csv(rows)
    header = csv_text.splitlines()[0]
    assert header == "smiles,name,IC50,logD"  # smiles,name, then sorted union of props


# --- diff ---------------------------------------------------------------------


def test_diff_reports_descriptor_deltas():
    d = chem_io.diff_molecules("c1ccccc1", "Cc1ccccc1")  # benzene vs toluene
    assert d["identical"] is False
    assert d["deltas"]["mw"] > 13 and d["deltas"]["mw"] < 15  # +CH2 ≈ +14
    assert "logp" in d["deltas"]


def test_diff_identical_molecules():
    d = chem_io.diff_molecules("c1ccccc1", "C1=CC=CC=C1")  # same molecule, different input
    assert d["identical"] is True
    assert d["deltas"]["mw"] == 0
