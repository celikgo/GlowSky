"""Nakitte platform auth — validate carbon-auth JWTs inside Glowsky.

Glowsky is one product in the nakitte-carbon platform. Rather than run its own
identity store, it accepts the platform's access tokens: short-lived **RS256 JWTs**
issued by `nakitte-carbon-auth` and verified statelessly against that service's
**JWKS endpoint** (`/.well-known/jwks.json`). The token carries the identity —
`sub` (user id), `tenant_id`, `roles[]`, `email` — and Glowsky **JIT-provisions** a
local org+user mirror so its tenant-scoped tables and foreign keys resolve, without
ever holding a password or minting its own platform identity.

Token shape (see nakitte-carbon-auth `JwtIssuer`):
    iss=<configured>  sub=<user uuid>  aud="carbon-platform"
    tenant_id=<uuid>  roles=[...]  email=<str>  exp/iat/jti

Role mapping → Glowsky's owner|admin|editor|viewer (only write-vs-read matters here):
    "owner"                              -> owner    (write)
    only read-only platform roles        -> viewer   (read)
    any other business/ops role present  -> editor   (write)
    no roles                             -> viewer   (safe default)

This is Glowsky's only credential type — there is no local API-key store.
"""
from __future__ import annotations

from functools import lru_cache

import jwt
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.core.auth import Principal
from services.core.config import get_settings
from services.core.models import Membership, Organization, User

# Platform roles that grant no write capability in Glowsky.
_READ_ONLY_ROLES = frozenset({"viewer", "auditor"})


@lru_cache(maxsize=8)
def _jwk_client(jwks_url: str) -> PyJWKClient:
    """One cached JWKS client per URL (it caches signing keys by `kid` internally)."""
    return PyJWKClient(jwks_url, cache_keys=True)


def glowsky_role(roles: set[str]) -> str:
    """Collapse the platform's role set to Glowsky's owner|editor|viewer."""
    if "owner" in roles:
        return "owner"
    if roles and roles <= _READ_ONLY_ROLES:
        return "viewer"
    if roles:
        return "editor"
    return "viewer"


def verify_nakitte_jwt(token: str) -> dict | None:
    """Validate an RS256 carbon-auth JWT against the JWKS. Returns claims or None.

    Never raises — any failure (bad signature, expired, wrong audience/issuer,
    unreachable JWKS, malformed token) resolves to None so callers map it to a 401.
    """
    settings = get_settings()
    try:
        signing_key = _jwk_client(settings.nakitte_jwks_url).get_signing_key_from_jwt(token)
        decode_kwargs: dict = {
            "algorithms": ["RS256"],
            "audience": settings.nakitte_jwt_audience,
            "leeway": 30,  # tolerate small clock skew across services
            "options": {"require": ["exp", "sub"]},
        }
        if settings.nakitte_jwt_issuer:
            decode_kwargs["issuer"] = settings.nakitte_jwt_issuer
        return jwt.decode(token, signing_key.key, **decode_kwargs)
    except Exception:
        return None


def _provision(session: Session, *, org_id: str, user_id: str, email: str, role: str) -> None:
    """Idempotently mirror the token's tenant+user into Glowsky so FKs resolve.

    Creates the Organization/User/Membership on first sight of a platform identity and
    keeps the membership role in sync with the token on subsequent requests.
    """
    if session.get(Organization, org_id) is None:
        session.add(Organization(id=org_id, name=f"tenant-{org_id[:8]}", plan="free"))
    if session.get(User, user_id) is None:
        # The platform's `sub` is the stable identity key here; email is secondary. Glowsky's
        # users.email is globally unique, so if some other id already holds this email (upstream
        # email reuse / data skew) we store a namespaced address rather than fail the request —
        # the real email still travels on the Principal.
        taken = session.scalar(select(User).where(User.email == email)) is not None
        stored_email = email if not taken else f"{user_id}@{org_id}.carbon-platform.local"
        session.add(User(id=user_id, email=stored_email))
    membership = session.scalar(
        select(Membership).where(Membership.org_id == org_id, Membership.user_id == user_id)
    )
    if membership is None:
        session.add(Membership(org_id=org_id, user_id=user_id, role=role))
    elif membership.role != role:
        membership.role = role
    session.flush()


def resolve_nakitte_token(session: Session, token: str) -> Principal | None:
    """Verify a platform JWT and return its Glowsky Principal (JIT-provisioned), or None."""
    claims = verify_nakitte_jwt(token)
    if claims is None:
        return None
    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    if not user_id or not tenant_id:
        # Glowsky data is tenant-scoped; a token without a tenant can't own anything here.
        return None
    email = claims.get("email") or f"{user_id}@carbon-platform.local"
    role = glowsky_role(set(claims.get("roles") or []))
    _provision(session, org_id=tenant_id, user_id=user_id, email=email, role=role)
    return Principal(user_id=user_id, org_id=tenant_id, role=role, email=email)
