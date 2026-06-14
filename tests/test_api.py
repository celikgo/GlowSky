"""API surface smoke tests against the running app (TestClient)."""
from fastapi.testclient import TestClient

from apps.api.main import app


def test_health_exposes_routes_not_keys():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "reasoning" in body["routes"]
        # No secret material anywhere in the response.
        assert "key" not in r.text.lower()


def test_validate_and_profile_endpoints():
    with TestClient(app) as client:
        v = client.post("/molecules/validate", json={"smiles": "c1ccccc1C(=O)O"})
        assert v.status_code == 200 and v.json()["valid"] is True

        p = client.post("/molecules/profile", json={"smiles": "CC(=O)Oc1ccccc1C(=O)O"})
        assert p.status_code == 200
        assert "mw" in p.json()["properties"]

        bad = client.post("/molecules/profile", json={"smiles": "garbage(("})
        assert bad.status_code == 422


def test_conformer_endpoint_returns_3d_molblock():
    with TestClient(app) as client:
        r = client.post("/molecules/conformer", json={"smiles": "CC(=O)Oc1ccccc1C(=O)O"})
        assert r.status_code == 200
        body = r.json()
        molblock = body["molblock"]
        assert "V2000" in molblock
        assert isinstance(body["energy_kcal_mol"], float)
        # The conformer must carry real 3D coords — at least one non-zero z column.
        atom_lines = [
            ln.split() for ln in molblock.splitlines()
            if len(ln.split()) > 3 and ln.split()[3].isalpha()
        ]
        assert any(abs(float(cols[2])) > 1e-6 for cols in atom_lines)

        bad = client.post("/molecules/conformer", json={"smiles": "garbage(("})
        assert bad.status_code == 422


def test_docking_sample_returns_receptor_and_ligand():
    with TestClient(app) as client:
        r = client.get("/examples/docking/sample")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == "1hsg"
        # Real experimental coordinates: protein ATOM records + a ligand block.
        assert "ATOM" in body["receptor_pdb"]
        assert "HETATM" in body["ligand_pdb"]
        # Honest provenance — this is sample data, not a computed docking result.
        assert "1HSG" in body["source"]


def test_design_endpoint_persists_and_returns_provenance():
    with TestClient(app) as client:
        r = client.post(
            "/agent/design",
            json={
                "goal": "make 8 analogs with MW<300, no PAINS",
                "seed_smiles": "c1ccccc1C(=O)O",
                "persist": True,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["run_id"]  # persisted -> provenance hub created
        assert len(body["candidates"]) > 0
        assert len(body["trace"]) == 3
        assert body["models_used"]["reasoning"] == "mock/mock"
