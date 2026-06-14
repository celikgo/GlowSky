"""Request dependencies: principal resolution and tenant-scoped access helpers."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from services.core.auth import DEV_PRINCIPAL, Principal, resolve_token
from services.core.config import get_settings
from services.core.db import session_scope
from services.core.models import AgentRun, Library, Project


def current_principal(authorization: str | None = Header(default=None)) -> Principal:
    """Resolve the request's principal.

    Auth disabled -> the built-in local owner (single-tenant dev mode).
    Auth enabled  -> require `Authorization: Bearer <api-key>`; 401 otherwise.
    """
    if not get_settings().auth_enabled:
        return DEV_PRINCIPAL

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[len("bearer "):].strip()
    with session_scope() as session:
        principal = resolve_token(session, token)
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return principal


def require_write(principal: Principal = Depends(current_principal)) -> Principal:
    """Principal that may mutate (owner/admin/editor); 403 for viewers."""
    if not principal.can_write:
        raise HTTPException(status_code=403, detail="insufficient role (read-only)")
    return principal


def load_project(session, project_id: str, principal: Principal) -> Project:
    """Fetch a project enforcing tenant isolation.

    Returns 404 (not 403) for projects outside the principal's org so existence
    never leaks across tenants.
    """
    project = session.get(Project, project_id)
    if project is None or project.org_id != principal.org_id:
        raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
    return project


def load_library(session, library_id: str, principal: Principal) -> Library:
    """Fetch a library enforcing tenant isolation (404 across orgs)."""
    library = session.get(Library, library_id)
    if library is None or library.org_id != principal.org_id:
        raise HTTPException(status_code=404, detail=f"unknown library: {library_id}")
    return library


def load_run(session, run_id: str, principal: Principal) -> AgentRun:
    """Fetch an agent run enforcing tenant isolation (404 across orgs)."""
    run = session.get(AgentRun, run_id)
    if run is None or run.org_id != principal.org_id:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    return run
