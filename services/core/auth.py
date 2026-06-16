"""Tenancy primitives.

Identity is owned by **nakitte-carbon-auth** — Glowsky has no local credential store.
A request authenticates with a platform JWT (see ``services.core.nakitte_auth``), which
resolves to a `Principal` (user + org + role) that scopes every downstream query. This
module holds the role model, the audit trail, and the tenant-bootstrap helper that
nakitte-auth uses when JIT-provisioning a tenant's local mirror.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from services.core.models import (
    LOCAL_ORG_ID,
    LOCAL_USER_ID,
    AuditEvent,
    Organization,
    User,
)

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


# --- tenant bootstrap ---------------------------------------------------------


def seed_local_tenant(session: Session) -> None:
    """Idempotently ensure the built-in local org/user exist.

    These are FK targets for the local-tenant principal used by the test suite; in
    production they're a harmless empty org no token can authenticate into.
    """
    if session.get(Organization, LOCAL_ORG_ID) is None:
        session.add(Organization(id=LOCAL_ORG_ID, name="Local", plan="free"))
    if session.get(User, LOCAL_USER_ID) is None:
        session.add(User(id=LOCAL_USER_ID, email="dev@localhost", name="Local Dev"))
    session.flush()


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
