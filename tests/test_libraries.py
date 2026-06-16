"""Library API: create, import (SMILES/CSV/SDF), export, dedup, and tenant isolation."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from tests.conftest import tenant


# --- happy path (default principal): no token needed ---------------------------


def test_create_import_export_round_trip():
    with TestClient(app) as client:
        pid = client.post("/projects", json={"name": "IO project"}).json()["id"]
        lib = client.post(f"/projects/{pid}/libraries", json={"name": "Hits"})
        assert lib.status_code == 201
        lid = lib.json()["id"]

        imp = client.post(f"/libraries/{lid}/import", json={
            "format": "smiles", "content": "c1ccccc1 benzene\nCCO ethanol\ngarbage((",
        })
        assert imp.status_code == 201
        body = imp.json()
        assert body["imported"] == 2
        assert body["invalid_count"] == 1  # the garbage line, reported not fatal

        got = client.get(f"/libraries/{lid}")
        assert got.json()["library"]["molecule_count"] == 2

        smi = client.get(f"/libraries/{lid}/export", params={"format": "smiles"})
        assert smi.status_code == 200
        assert "benzene" in smi.text
        assert "attachment" in smi.headers["content-disposition"]

        csv_out = client.get(f"/libraries/{lid}/export", params={"format": "csv"})
        assert csv_out.text.splitlines()[0].startswith("smiles,name")

        sdf_out = client.get(f"/libraries/{lid}/export", params={"format": "sdf"})
        assert "$$$$" in sdf_out.text  # SDF record terminator


def test_import_csv_with_properties_and_dedup():
    with TestClient(app) as client:
        pid = client.post("/projects", json={"name": "CSV project"}).json()["id"]
        lid = client.post(f"/projects/{pid}/libraries", json={"name": "Assay"}).json()["id"]

        csv_text = "smiles,name,IC50\nCCO,ethanol,12.5\nc1ccccc1,benzene,3.1\n"
        first = client.post(f"/libraries/{lid}/import", json={"format": "csv", "content": csv_text})
        assert first.json()["imported"] == 2

        # Re-importing the same molecules adds no new members (dedup by InChIKey).
        again = client.post(f"/libraries/{lid}/import", json={"format": "csv", "content": csv_text})
        assert again.json()["imported"] == 0 and again.json()["duplicates"] == 2

        mols = client.get(f"/libraries/{lid}").json()["molecules"]
        assert any(m["properties"].get("IC50") == "12.5" for m in mols)


def test_reimport_fills_empty_fields_but_never_overwrites():
    with TestClient(app) as client:
        pid = client.post("/projects", json={"name": "Merge project"}).json()["id"]
        lid = client.post(f"/projects/{pid}/libraries", json={"name": "Merge"}).json()["id"]

        # First import: bare SMILES, no properties.
        first = client.post(f"/libraries/{lid}/import",
                            json={"format": "smiles", "content": "CCO ethanol"})
        assert first.json()["imported"] == 1

        # Second import: same molecule with an assay column -> empty field is filled.
        second = client.post(f"/libraries/{lid}/import", json={
            "format": "csv", "content": "smiles,name,IC50\nCCO,ethanol,12.5"})
        body = second.json()
        assert body["imported"] == 0 and body["duplicates"] == 1
        assert body["updated"] == 1  # existing row gained the IC50 column

        mols = client.get(f"/libraries/{lid}").json()["molecules"]
        assert mols[0]["properties"]["IC50"] == "12.5"

        # Re-import with a CONFLICTING value -> existing value is preserved, not overwritten.
        conflict = client.post(f"/libraries/{lid}/import", json={
            "format": "csv", "content": "smiles,name,IC50\nCCO,ethanol,999"})
        assert conflict.json()["updated"] == 0
        mols = client.get(f"/libraries/{lid}").json()["molecules"]
        assert mols[0]["properties"]["IC50"] == "12.5"  # unchanged

        # A new, still-empty column IS filled while the existing one stays put.
        more = client.post(f"/libraries/{lid}/import", json={
            "format": "csv", "content": "smiles,name,IC50,logD\nCCO,ethanol,999,1.2"})
        assert more.json()["updated"] == 1
        props = client.get(f"/libraries/{lid}").json()["molecules"][0]["properties"]
        assert props["IC50"] == "12.5" and props["logD"] == "1.2"


def test_molecule_diff_endpoint():
    with TestClient(app) as client:
        r = client.post("/molecules/diff", json={"smiles_a": "c1ccccc1", "smiles_b": "Cc1ccccc1"})
        assert r.status_code == 200
        assert r.json()["identical"] is False
        assert r.json()["deltas"]["mw"] > 0

        bad = client.post("/molecules/diff", json={"smiles_a": "c1ccccc1", "smiles_b": "junk(("})
        assert bad.status_code == 422


# --- tenant isolation (real JWTs) ---------------------------------------------


@pytest.mark.real_auth
def test_libraries_are_isolated_between_tenants():
    with TestClient(app) as client:
        ha = tenant()["headers"]
        hb = tenant()["headers"]
        pid = client.post("/projects", json={"name": "A proj"}, headers=ha).json()["id"]
        lid = client.post(f"/projects/{pid}/libraries", json={"name": "A lib"},
                          headers=ha).json()["id"]

        # Org B cannot read or export org A's library.
        assert client.get(f"/libraries/{lid}", headers=hb).status_code == 404
        assert client.get(f"/libraries/{lid}/export", headers=hb).status_code == 404
        assert client.get(f"/libraries/{lid}", headers=ha).status_code == 200
