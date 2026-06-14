"""Authentication & tenancy primitives.

Phase 1 uses **bearer API keys** as the auth primitive — the simplest credential that
is fully testable headlessly (OAuth/email flows arrive with the frontend). A key is
minted once at signup, returned in plaintext exactly once, and stored only as a
SHA-256 hash. Resolving a key yields a `Principal` (user + org + role) that scopes
every downstream query.

When auth is disabled (`GLOWSKY_AUTH_ENABLED=False`, the default), the API resolves
every request to `DEV_PRINCIPAL` — a built-in owner of the seeded `local-org`. This
keeps Phase 0's zero-setup, offline ergonomics intact while the tenancy spine exists.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.core.models import (
    LOCAL_ORG_ID,
    LOCAL_USER_ID,
    ApiKey,
    AuditEvent,
    Membership,
    Organization,
    User,
)

_TOKEN_PREFIX = "glw_"
_WRITE_ROLES = frozenset({"owner", "admin", "editor"})


@dataclass(frozen=True)
class Principal:
    """The authenticated actor for a request: who they are and what org they act in."""

    user_id: str
    org_id: str
    role: str = "owner"  # owner|admin|editor|viewer
    email: str | None = None

    @property
    def can_write(self) -> bool:
        return self.role in _WRITE_ROLES


# Resolved for every request when auth is disabled (single-tenant dev mode).
DEV_PRINCIPAL = Principal(
    user_id=LOCAL_USER_ID, org_id=LOCAL_ORG_ID, role="owner", email="dev@localhost"
)


# --- token helpers ------------------------------------------------------------


def mint_token() -> str:
    """A fresh opaque bearer token. Shown to the user once; never persisted in plaintext."""
    return _TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- tenant bootstrap ---------------------------------------------------------


def seed_local_tenant(session: Session) -> None:
    """Idempotently ensure the built-in local org/user exist (dev mode FK targets)."""
    if session.get(Organization, LOCAL_ORG_ID) is None:
        session.add(Organization(id=LOCAL_ORG_ID, name="Local", plan="free"))
    if session.get(User, LOCAL_USER_ID) is None:
        session.add(User(id=LOCAL_USER_ID, email="dev@localhost", name="Local Dev"))
    session.flush()


# --- signup & resolution ------------------------------------------------------


def signup(session: Session, email: str, org_name: str) -> tuple[Principal, str]:
    """Create a single-member org + user + owner membership, mint an API key.

    Returns the new principal and the **plaintext token** (the only time it's available).
    Raises ValueError if the email is already registered.
    """
    existing = session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ValueError(f"email already registered: {email}")

    org = Organization(name=org_name)
    user = User(email=email, name=email.split("@")[0])
    session.add_all([org, user])
    session.flush()  # assign ids
    session.add(Membership(org_id=org.id, user_id=user.id, role="owner"))

    token = mint_token()
    session.add(ApiKey(org_id=org.id, user_id=user.id, token_hash=hash_token(token), label="default"))

    principal = Principal(user_id=user.id, org_id=org.id, role="owner", email=email)
    audit(session, principal, "org.signup", "organization", org.id, {"email": email})
    return principal, token


def resolve_token(session: Session, token: str) -> Principal | None:
    """Look up a bearer token and return its Principal, or None if unknown."""
    if not token:
        return None
    key = session.scalar(select(ApiKey).where(ApiKey.token_hash == hash_token(token)))
    if key is None:
        return None
    membership = session.scalar(
        select(Membership).where(
            Membership.org_id == key.org_id, Membership.user_id == key.user_id
        )
    )
    role = membership.role if membership else "viewer"
    user = session.get(User, key.user_id)
    return Principal(user_id=key.user_id, org_id=key.org_id, role=role,
                     email=user.email if user else None)


# --- audit --------------------------------------------------------------------


def audit(
    session: Session,
    principal: Principal,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Append a security/compliance audit row. Best-effort, never blocks the caller."""
    session.add(AuditEvent(
        org_id=principal.org_id, actor_id=principal.user_id, action=action,
        entity_type=entity_type, entity_id=entity_id, event_metadata=metadata or {},
    ))
