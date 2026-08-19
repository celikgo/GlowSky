"""Domain models — Phase 0 + Phase 1 (auth/tenancy) subset of docs/06-data-models.md.

Phase 0 persisted only Molecule (+ provenance) and AgentRun (the provenance hub).
Phase 1 adds the identity & tenancy spine — Organization, User, Membership, Project,
ApiKey, AuditEvent — and scopes every domain row to its org. Personal accounts are a
single-member org (docs/06). Bearer API keys store only a hash; plaintext is shown once.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Built-in single-tenant identifiers, used as the seed org/user for local development
# fixtures. They are NOT an auth bypass: every request still resolves a principal from
# a nakitte JWT (apps/api/deps.py).
LOCAL_ORG_ID = "local-org"
LOCAL_USER_ID = "local-user"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


# --- Identity & tenancy -------------------------------------------------------


class Organization(Base):
    """Tenant boundary. Personal accounts are modeled as a single-member org."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    plan: Mapped[str] = mapped_column(String, default="free")  # free|pro|team|enterprise
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Membership(Base):
    """Join of User <-> Organization carrying the user's role in that org."""

    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String, default="owner")  # owner|admin|editor|viewer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ApiKey(Base):
    """Bearer credential. Only the SHA-256 hash is stored; plaintext is shown once."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Project(Base):
    """Container for molecules/runs within an org; carries the target design profile."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    target_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Library(Base):
    """A named, ordered collection of molecules within a project (docs/06)."""

    __tablename__ = "libraries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    kind: Mapped[str] = mapped_column(String, default="set")  # set|series|virtual_screen
    columns_config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LibraryMembership(Base):
    """Join of Library <-> Molecule. A molecule can belong to many libraries."""

    __tablename__ = "library_memberships"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    library_id: Mapped[str] = mapped_column(ForeignKey("libraries.id"), index=True)
    molecule_id: Mapped[str] = mapped_column(ForeignKey("molecules.id"), index=True)
    added_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LLMProviderCredential(Base):
    """A BYO-LLM provider key, encrypted at rest (docs/06). One row per (org, provider);
    the row stores only ciphertext + a masked hint — plaintext is never persisted."""

    __tablename__ = "llm_provider_credentials"
    __table_args__ = (UniqueConstraint("org_id", "provider", name="uq_org_provider"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    provider: Mapped[str] = mapped_column(String)  # anthropic|openai|groq|local|...
    encrypted_secret: Mapped[str] = mapped_column(Text)  # Fernet ciphertext
    hint: Mapped[str] = mapped_column(String)  # masked, safe to show (e.g. "sk-…AB12")
    base_url: Mapped[str | None] = mapped_column(String, default=None)  # for local/compatible
    label: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, default="active")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ModelRouteOverride(Base):
    """Per-org task-class -> 'provider/model' override (docs/06 ModelRoute). One per
    (org, task_class); absence means fall back to the env-configured default."""

    __tablename__ = "model_route_overrides"
    __table_args__ = (UniqueConstraint("org_id", "task_class", name="uq_org_taskclass"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    task_class: Mapped[str] = mapped_column(String)  # reasoning|fast_triage|codegen
    provider: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditEvent(Base):
    """Security/compliance trail — one row per consequential action (docs/07 §10)."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, index=True)
    actor_id: Mapped[str | None] = mapped_column(String, default=None)
    action: Mapped[str] = mapped_column(String)  # e.g. org.signup, project.create, run.design
    entity_type: Mapped[str | None] = mapped_column(String, default=None)
    entity_id: Mapped[str | None] = mapped_column(String, default=None)
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Molecule(Base):
    __tablename__ = "molecules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # Every domain row is scoped to its org (tenant boundary). project_id is optional:
    # ad-hoc molecules may exist outside a project.
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), default=LOCAL_ORG_ID, index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), default=None, index=True
    )

    name: Mapped[str | None] = mapped_column(String, default=None)
    canonical_smiles: Mapped[str] = mapped_column(String)
    inchikey: Mapped[str] = mapped_column(String, index=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String, default="user")  # user|import|generated
    origin_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"), default=None, index=True
    )
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentRun(Base):
    """Provenance hub: every generated molecule links back here via origin_run_id."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), default=LOCAL_ORG_ID, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), default=None, index=True)

    goal_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="done")  # planning|running|done|failed
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    trace: Mapped[list] = mapped_column(JSON, default=list)  # list of tool-call records
    models_used: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    molecules: Mapped[list[Molecule]] = relationship(
        "Molecule", primaryjoin="AgentRun.id == Molecule.origin_run_id", viewonly=True
    )
