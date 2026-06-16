"""BYO-LLM key management: encryption at rest, masking, routing, tenant isolation,
and the gateway actually using stored credentials/routes.

Credential/route endpoints are tenant-scoped, so these run under real nakitte JWTs
(``@pytest.mark.real_auth``) — each ``tenant()`` is a fresh isolated org.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from services.core.crypto import decrypt, encrypt, mask
from services.llm_gateway.credentials import CredentialResolver
from services.llm_gateway.gateway import LLMGateway
from services.llm_gateway.types import TaskClass
from tests.conftest import tenant


# --- crypto -------------------------------------------------------------------


def test_encryption_round_trip_and_mask():
    secret = "sk-ant-abc123XYZ789"
    token = encrypt(secret)
    assert token != secret and secret not in token  # ciphertext, not plaintext
    assert decrypt(token) == secret
    m = mask(secret)
    assert m.startswith("sk-") and m.endswith("789") and secret not in m


# --- credentials API ----------------------------------------------------------


@pytest.mark.real_auth
def test_add_credential_never_returns_or_stores_plaintext():
    with TestClient(app) as client:
        acct = tenant()
        h = acct["headers"]
        key = "sk-secret-PLAINTEXT-9999"
        r = client.post("/settings/credentials", headers=h,
                        json={"provider": "anthropic", "api_key": key})
        assert r.status_code == 201
        assert key not in r.text  # the secret is never echoed back
        body = r.json()
        assert body["hint"].endswith("9999") and "api_key" not in body

        # Listing shows only the masked hint, never the key.
        lst = client.get("/settings/credentials", headers=h)
        assert key not in lst.text
        assert lst.json()[0]["provider"] == "anthropic"

    # And the gateway can decrypt it for real use.
    assert CredentialResolver(acct["org_id"]).api_key("anthropic") == key


@pytest.mark.real_auth
def test_credential_upsert_keeps_one_per_provider():
    with TestClient(app) as client:
        h = tenant()["headers"]
        client.post("/settings/credentials", headers=h,
                    json={"provider": "openai", "api_key": "sk-one-1111"})
        client.post("/settings/credentials", headers=h,
                    json={"provider": "openai", "api_key": "sk-two-2222"})
        creds = client.get("/settings/credentials", headers=h).json()
        openai = [c for c in creds if c["provider"] == "openai"]
        assert len(openai) == 1 and openai[0]["hint"].endswith("2222")  # replaced


@pytest.mark.real_auth
def test_unsupported_provider_rejected():
    with TestClient(app) as client:
        r = client.post("/settings/credentials", headers=tenant()["headers"],
                        json={"provider": "skynet", "api_key": "x"})
        assert r.status_code == 422


@pytest.mark.real_auth
def test_credentials_are_tenant_isolated():
    with TestClient(app) as client:
        ha = tenant()["headers"]
        hb = tenant()["headers"]
        cid = client.post("/settings/credentials", headers=ha,
                          json={"provider": "groq", "api_key": "gsk-aaaa"}).json()["id"]
        # B sees none of A's credentials and can't delete them.
        assert client.get("/settings/credentials", headers=hb).json() == []
        assert client.delete(f"/settings/credentials/{cid}", headers=hb).status_code == 404
        assert client.delete(f"/settings/credentials/{cid}", headers=ha).json()["deleted"] == cid


# --- routes -------------------------------------------------------------------


@pytest.mark.real_auth
def test_routes_default_then_override_then_revert():
    with TestClient(app) as client:
        h = tenant()["headers"]
        # Default (env) routes report source=default.
        routes = {r["task_class"]: r for r in client.get("/settings/routes", headers=h).json()}
        assert routes["reasoning"]["source"] == "default"

        # Set an override.
        put = client.put("/settings/routes", headers=h, json={
            "task_class": "reasoning", "provider": "anthropic", "model": "claude-opus-4-8"})
        assert put.status_code == 200 and put.json()["source"] == "override"
        routes = {r["task_class"]: r for r in client.get("/settings/routes", headers=h).json()}
        assert routes["reasoning"] == {
            "task_class": "reasoning", "provider": "anthropic",
            "model": "claude-opus-4-8", "source": "override"}

        # Clear -> back to default.
        client.delete("/settings/routes/reasoning", headers=h)
        routes = {r["task_class"]: r for r in client.get("/settings/routes", headers=h).json()}
        assert routes["reasoning"]["source"] == "default"


# --- gateway integration ------------------------------------------------------


@pytest.mark.real_auth
def test_gateway_uses_stored_credentials_and_route():
    with TestClient(app) as client:
        acct = tenant()
        org = acct["org_id"]
        h = acct["headers"]
        client.post("/settings/credentials", headers=h,
                    json={"provider": "anthropic", "api_key": "sk-live-key"})
        client.put("/settings/routes", headers=h, json={
            "task_class": "reasoning", "provider": "anthropic", "model": "claude-opus-4-8"})

        # Org-scoped gateway resolves the stored route (it has a key, so no mock fallback).
        gw = LLMGateway(org_id=org)
        assert gw.route_for(TaskClass.REASONING) == "anthropic/claude-opus-4-8"
        # A different org with nothing stored still falls back to the offline mock.
        assert LLMGateway(org_id="local-org").route_for(TaskClass.REASONING) == "mock/mock"
