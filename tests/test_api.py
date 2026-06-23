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


def test_assess_endpoint_bundles_the_expert_layer():
    with TestClient(app) as client:
        r = client.post("/molecules/assess", json={"smiles": "CC(=O)Oc1ccccc1C(=O)O"})  # aspirin
        assert r.status_code == 200
        body = r.json()
        # The four expert sections are present and shaped.
        assert 0.0 <= body["mpo"]["score"] <= 1.0 and body["mpo"]["limiting"]
        assert "lipinski" in body["rules"]["rules"]
        assert body["synthesizability"]["best_disconnection"]["reaction"] == "esterification"
        assert "pains" in body["alerts"]

        bad = client.post("/molecules/assess", json={"smiles": "garbage(("})
        assert bad.status_code == 422


def test_login_proxies_to_carbon_auth(monkeypatch):
    """POST /auth/login forwards credentials to carbon-auth and relays the token, flagging
    whether it's already tenant-scoped. carbon-auth is mocked — Glowsky never stores the password."""
    import httpx as _httpx

    import apps.api.main as main_mod
    from tests.conftest import make_token

    captured = {}
    scoped = make_token(tenant_id="local-org")  # carbon-auth scopes single-tenant logins

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "accessToken": scoped,
                "accessTokenExpiresIn": 900,
                "refreshToken": "refresh-abc",
                "refreshTokenExpiresIn": 1209600,
            }

    def _fake_post(url, json, timeout):  # noqa: A002 - mirrors httpx.post signature
        captured["url"] = url
        captured["body"] = json
        return _Resp()

    monkeypatch.setattr(main_mod.httpx, "post", _fake_post)

    with TestClient(main_mod.app) as client:
        r = client.post("/auth/login", json={"email": "a@lab.edu", "password": "secret123"})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] == scoped
    assert body["refresh_token"] == "refresh-abc"
    assert body["tenant_scoped"] is True
    # Credentials were forwarded to carbon-auth's /auth/login, not stored.
    assert captured["url"].endswith("/auth/login")
    assert captured["body"] == {"email": "a@lab.edu", "password": "secret123"}


def test_login_maps_invalid_credentials_to_401(monkeypatch):
    import apps.api.main as main_mod

    class _Resp:
        status_code = 401

        @staticmethod
        def json():
            return {"error": "invalid_credentials"}

    monkeypatch.setattr(main_mod.httpx, "post", lambda url, json, timeout: _Resp())
    with TestClient(main_mod.app) as client:
        r = client.post("/auth/login", json={"email": "a@lab.edu", "password": "wrongpass"})
    assert r.status_code == 401


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
        # validate -> generate_analogs -> bioisosteric_replacement -> profile
        assert len(body["trace"]) == 4
        assert body["models_used"]["reasoning"] == "mock/mock"
