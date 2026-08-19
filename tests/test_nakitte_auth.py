"""Nakitte platform auth — the sole credential — plus the H1 gating of the tool/job
/molecule surface.

Covers: the execution endpoints require a token (401 without one); a valid RS256
carbon-auth JWT resolves to a principal and JIT-provisions its tenant; tampered /
expired / wrong-audience / wrong-key / tenant-less tokens are rejected; and the
platform-role -> Glowsky-role mapping.
"""
from __future__ import annotations

import time
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from apps.api.main import app
from services.core import nakitte_auth
from services.core.db import session_scope
from services.core.models import Organization
from tests.conftest import auth_header, make_token

# --- H1: every execution endpoint requires a token ----------------------------


@pytest.mark.real_auth
def test_execution_surface_requires_a_token():
    with TestClient(app) as client:
        assert client.post("/tools/validate_molecule", json={"args": {"smiles": "CCO"}}).status_code == 401
        job = {"tool": "sa_score", "args": {"canonical_smiles": "CCO"}}
        assert client.post("/jobs", json=job).status_code == 401
        batch = {"tool": "sa_score", "items": [{"canonical_smiles": "CCO"}]}
        assert client.post("/jobs/batch", json=batch).status_code == 401
        assert client.post("/molecules/validate", json={"smiles": "CCO"}).status_code == 401


@pytest.mark.real_auth
def test_valid_token_is_accepted_and_provisions_tenant():
    tenant_id = str(uuid.uuid4())
    with TestClient(app) as client:
        r = client.post(
            "/tools/validate_molecule",
            headers=auth_header(tenant_id=tenant_id),
            json={"args": {"smiles": "CCO"}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["output"]["canonical_smiles"] == "CCO"
    with session_scope() as s:  # tenant JIT-provisioned so tenant-scoped FKs resolve
        assert s.get(Organization, tenant_id) is not None


@pytest.mark.real_auth
def test_invalid_tokens_are_rejected():
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad = {
        "expired": make_token(exp=int(time.time()) - 3600),     # past the 30s leeway
        "wrong_aud": make_token(aud="someone-else"),
        "wrong_key": make_token(key=other_key),                 # signed by an untrusted key
        "tampered": make_token() + "x",
    }
    with TestClient(app) as client:
        for label, token in bad.items():
            r = client.post(
                "/tools/validate_molecule",
                headers={"Authorization": f"Bearer {token}"},
                json={"args": {"smiles": "CCO"}},
            )
            assert r.status_code == 401, f"{label} should be rejected"


def test_token_without_tenant_is_rejected():
    # Glowsky is tenant-scoped; a token carrying no tenant can't own data here.
    with session_scope() as s:
        assert nakitte_auth.resolve_nakitte_token(s, make_token(tenant_id=None)) is None


def test_token_with_tenant_resolves_role_from_claims():
    with session_scope() as s:
        p = nakitte_auth.resolve_nakitte_token(s, make_token(roles=["viewer"]))
        assert p is not None and p.role == "viewer" and not p.can_write


@pytest.mark.parametrize(
    "roles,expected",
    [
        ({"owner"}, "owner"),
        ({"owner", "viewer"}, "owner"),
        ({"viewer"}, "viewer"),
        ({"auditor"}, "viewer"),
        ({"accountant"}, "editor"),
        ({"station_operator"}, "editor"),
        (set(), "viewer"),
    ],
)
def test_role_mapping(roles, expected):
    assert nakitte_auth.glowsky_role(roles) == expected
