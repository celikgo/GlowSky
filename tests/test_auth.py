"""Tenancy: principal resolution, project CRUD, and cross-tenant isolation.

Auth is nakitte-JWT-only. Ordinary tests run under the default local-tenant principal
(see conftest); the `real_auth` tests present real minted JWTs to prove isolation.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from tests.conftest import tenant


def test_auth_me_returns_the_resolved_principal():
    with TestClient(app) as client:
        me = client.get("/auth/me")
        assert me.status_code == 200
        body = me.json()
        assert body["org_id"] == "local-org" and body["role"] == "owner"


def test_project_crud_under_resolved_principal():
    with TestClient(app) as client:
        pid = client.post("/projects", json={"name": "Series"}).json()["id"]
        assert any(p["id"] == pid for p in client.get("/projects").json())
        assert client.get(f"/projects/{pid}").status_code == 200


# --- real nakitte-JWT auth -----------------------------------------------------


@pytest.mark.real_auth
def test_missing_or_invalid_token_is_401():
    with TestClient(app) as client:
        assert client.get("/auth/me").status_code == 401  # no token
        assert client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


@pytest.mark.real_auth
def test_auth_me_reflects_token_tenant_and_role():
    with TestClient(app) as client:
        t = tenant(roles=("sustainability_reviewer",))  # a non-owner write role -> editor
        me = client.get("/auth/me", headers=t["headers"]).json()
        assert me["org_id"] == t["org_id"] and me["role"] == "editor"


@pytest.mark.real_auth
def test_projects_are_isolated_between_tenants():
    with TestClient(app) as client:
        a, b = tenant(), tenant()
        proj = client.post("/projects", json={"name": "A's secret series"}, headers=a["headers"])
        assert proj.status_code == 201
        pid = proj.json()["id"]

        # Owner sees it...
        assert any(p["id"] == pid for p in client.get("/projects", headers=a["headers"]).json())
        # ...the other tenant cannot list or fetch it (404, not 403 — no existence leak).
        assert all(p["id"] != pid for p in client.get("/projects", headers=b["headers"]).json())
        assert client.get(f"/projects/{pid}", headers=b["headers"]).status_code == 404
        assert client.get(f"/projects/{pid}", headers=a["headers"]).status_code == 200


@pytest.mark.real_auth
def test_design_scoped_to_project_is_listed_under_it():
    with TestClient(app) as client:
        h = tenant()["headers"]
        pid = client.post("/projects", json={"name": "Series C"}, headers=h).json()["id"]
        r = client.post("/agent/design", headers=h, json={
            "goal": "make 5 analogs, MW<300", "seed_smiles": "c1ccccc1C(=O)O", "project_id": pid,
        })
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        runs = client.get(f"/projects/{pid}/runs", headers=h).json()["runs"]
        assert any(run["id"] == run_id for run in runs)
        assert len(client.get(f"/projects/{pid}/molecules", headers=h).json()["molecules"]) > 0


@pytest.mark.real_auth
def test_design_into_foreign_project_is_rejected():
    with TestClient(app) as client:
        a, b = tenant(), tenant()
        pid = client.post("/projects", json={"name": "A only"}, headers=a["headers"]).json()["id"]
        r = client.post("/agent/design", headers=b["headers"],
                        json={"goal": "x", "seed_smiles": "c1ccccc1", "project_id": pid})
        assert r.status_code == 404
