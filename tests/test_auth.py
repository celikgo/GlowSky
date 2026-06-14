"""Auth & tenancy: dev-mode fallback, bearer auth, project CRUD, tenant isolation."""
from __future__ import annotations

import contextlib
import uuid

from fastapi.testclient import TestClient

from apps.api.main import app
from services.core.config import get_settings


def _email() -> str:
    """Unique per run — tests share the dev DB, so fixed emails would collide on re-run."""
    return f"user-{uuid.uuid4().hex[:12]}@lab.edu"


@contextlib.contextmanager
def auth_enabled(flag: bool):
    """Toggle GLOWSKY_AUTH_ENABLED for a test, restoring the cached settings after."""
    settings = get_settings()
    original = settings.auth_enabled
    object.__setattr__(settings, "auth_enabled", flag)
    try:
        yield
    finally:
        object.__setattr__(settings, "auth_enabled", original)


# --- Dev mode (auth disabled): Phase 0 ergonomics preserved -------------------


def test_dev_mode_resolves_local_principal_without_a_token():
    with TestClient(app) as client:
        r = client.get("/auth/me")
        assert r.status_code == 200
        me = r.json()
        assert me["org_id"] == "local-org"
        assert me["role"] == "owner"


def test_dev_mode_design_persists_under_local_org():
    with TestClient(app) as client:
        r = client.post("/agent/design", json={
            "goal": "make 6 analogs, MW<300, no PAINS", "seed_smiles": "c1ccccc1C(=O)O",
        })
        assert r.status_code == 200 and r.json()["run_id"]


# --- Auth enabled: signup mints a usable key ----------------------------------


def test_signup_then_authenticate_with_bearer_key():
    with TestClient(app) as client:
        s = client.post("/auth/signup", json={"email": _email(), "org_name": "Maya Lab"})
        assert s.status_code == 201
        body = s.json()
        key = body["api_key"]
        assert key.startswith("glw_")

        with auth_enabled(True):
            # No token -> 401.
            assert client.get("/auth/me").status_code == 401
            # Valid token -> resolves to the new org.
            me = client.get("/auth/me", headers={"Authorization": f"Bearer {key}"})
            assert me.status_code == 200
            assert me.json()["org_id"] == body["org_id"]
            # Garbage token -> 401.
            bad = client.get("/auth/me", headers={"Authorization": "Bearer glw_nope"})
            assert bad.status_code == 401


def test_signup_rejects_duplicate_email():
    with TestClient(app) as client:
        client.post("/auth/signup", json={"email": "dup@lab.edu", "org_name": "A"})
        again = client.post("/auth/signup", json={"email": "dup@lab.edu", "org_name": "B"})
        assert again.status_code == 409


# --- Projects + tenant isolation ----------------------------------------------


def test_projects_are_isolated_between_tenants():
    with TestClient(app) as client:
        a = client.post("/auth/signup", json={"email": _email(), "org_name": "Org A"}).json()
        b = client.post("/auth/signup", json={"email": _email(), "org_name": "Org B"}).json()
        ha = {"Authorization": f"Bearer {a['api_key']}"}
        hb = {"Authorization": f"Bearer {b['api_key']}"}

        with auth_enabled(True):
            proj = client.post("/projects", json={"name": "A's secret series"}, headers=ha)
            assert proj.status_code == 201
            pid = proj.json()["id"]

            # Owner sees it in their list...
            mine = client.get("/projects", headers=ha).json()
            assert any(p["id"] == pid for p in mine)

            # ...the other tenant cannot list or fetch it (404, not 403 — no existence leak).
            assert all(p["id"] != pid for p in client.get("/projects", headers=hb).json())
            assert client.get(f"/projects/{pid}", headers=hb).status_code == 404
            assert client.get(f"/projects/{pid}", headers=ha).status_code == 200


def test_design_scoped_to_project_is_listed_under_it():
    with TestClient(app) as client:
        acct = client.post("/auth/signup", json={"email": _email(), "org_name": "Org C"}).json()
        h = {"Authorization": f"Bearer {acct['api_key']}"}
        with auth_enabled(True):
            pid = client.post("/projects", json={"name": "Series C"}, headers=h).json()["id"]
            r = client.post("/agent/design", headers=h, json={
                "goal": "make 5 analogs, MW<300", "seed_smiles": "c1ccccc1C(=O)O",
                "project_id": pid,
            })
            assert r.status_code == 200
            run_id = r.json()["run_id"]

            runs = client.get(f"/projects/{pid}/runs", headers=h).json()["runs"]
            assert any(run["id"] == run_id for run in runs)
            mols = client.get(f"/projects/{pid}/molecules", headers=h).json()["molecules"]
            assert len(mols) > 0


def test_design_into_foreign_project_is_rejected():
    with TestClient(app) as client:
        a = client.post("/auth/signup", json={"email": _email(), "org_name": "Org D"}).json()
        b = client.post("/auth/signup", json={"email": _email(), "org_name": "Org E"}).json()
        with auth_enabled(True):
            pid = client.post("/projects", json={"name": "D only"},
                              headers={"Authorization": f"Bearer {a['api_key']}"}).json()["id"]
            # Org E tries to run a design into Org D's project.
            r = client.post("/agent/design",
                            headers={"Authorization": f"Bearer {b['api_key']}"},
                            json={"goal": "x", "seed_smiles": "c1ccccc1", "project_id": pid})
            assert r.status_code == 404
