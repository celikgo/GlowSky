"""Shared test infrastructure for Glowsky's nakitte-JWT-only auth.

Glowsky authenticates every request with a nakitte-carbon-auth platform JWT — there is
no auth bypass and no local credential store. Tests don't run a real auth service, so:

  * the JWKS verifier is stubbed to a session-local RSA keypair (so tokens minted here
    validate), and
  * ordinary tests get `current_principal` overridden to a fixed local-tenant principal,
    so token-less happy-path requests work without ceremony.

Tests that exercise real auth/tenancy mark themselves ``@pytest.mark.real_auth``: the
override is lifted and they must present a real minted JWT (e.g. via ``auth_header()`` /
``tenant()``). The JWKS stub stays active so those minted tokens verify for real.
"""
from __future__ import annotations

import os

# The application now defaults GLOWSKY_ENVIRONMENT to "production" (fail-safe, GS-H1), which
# would require a real GLOWSKY_SECRET_KEY. Opt the test session in to the dev-tier key BEFORE
# any module imports and caches Settings (apps.api.main reads get_settings() at import time).
os.environ.setdefault("GLOWSKY_ENVIRONMENT", "test")

import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import services.core.nakitte_auth as na
from apps.api import main
from apps.api.deps import current_principal
from services.core.auth import Principal
from services.core.models import LOCAL_ORG_ID, LOCAL_USER_ID

# One keypair for the whole test session; the JWKS client is stubbed to its public key.
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

TEST_PRINCIPAL = Principal(
    user_id=LOCAL_USER_ID, org_id=LOCAL_ORG_ID, role="owner", email="dev@localhost"
)


class _FakeSigningKey:
    def __init__(self, public_key) -> None:
        self.key = public_key


class _FakeJWKClient:
    def __init__(self, public_key) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_key)


def make_token(*, key=None, **overrides) -> str:
    """Mint an RS256 token shaped like a nakitte-carbon-auth access token.

    Pass claim overrides (e.g. ``tenant_id=...``, ``roles=[...]``, ``aud=...``,
    ``exp=...``); set a claim to ``None`` to drop it. ``key`` signs with a different
    (untrusted) key to simulate a bad signature.
    """
    now = int(time.time())
    uid = str(uuid.uuid4())
    claims = {
        "iss": "https://auth.nakitte.test",
        "sub": uid,
        "aud": "carbon-platform",
        "iat": now,
        "exp": now + 900,
        "tenant_id": str(uuid.uuid4()),
        "roles": ["owner"],
        "email": f"u-{uid[:8]}@lab.edu",
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key or _KEY, algorithm="RS256")


def auth_header(**overrides) -> dict:
    return {"Authorization": f"Bearer {make_token(**overrides)}"}


def tenant(roles=("owner",)) -> dict:
    """A fresh tenant identity: its org_id plus an auth header that resolves to it."""
    tid = str(uuid.uuid4())
    return {"org_id": tid, "headers": auth_header(tenant_id=tid, roles=list(roles))}


@pytest.fixture(autouse=True)
def _auth(request, monkeypatch):
    # Always stub JWKS so minted tokens validate (real_auth tests rely on real validation).
    monkeypatch.setattr(na, "_jwk_client", lambda url: _FakeJWKClient(_KEY.public_key()))
    if "real_auth" in request.keywords:
        yield
        return
    # Ordinary tests: resolve every request to the local-tenant principal (no token needed).
    main.app.dependency_overrides[current_principal] = lambda: TEST_PRINCIPAL
    monkeypatch.setattr(main, "_ws_principal", lambda token=None: TEST_PRINCIPAL)
    try:
        yield
    finally:
        main.app.dependency_overrides.pop(current_principal, None)
