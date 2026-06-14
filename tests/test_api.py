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
