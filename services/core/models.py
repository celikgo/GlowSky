"""Domain models — Phase 0 subset of docs/06-data-models.md.

Only the entities needed for the vertical slice are persisted here:
Molecule (+ provenance back to the run that produced it) and AgentRun
(the provenance hub holding the full execution trace).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Molecule(Base):
    __tablename__ = "molecules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    # Phase 0 has no real auth/tenancy yet; org/project are placeholders so the
    # provenance + scoping seams already exist (see docs/06).
    org_id: Mapped[str] = mapped_column(String, default="local-org", index=True)
    project_id: Mapped[str | None] = mapped_column(String, default="local-project", index=True)

    name: Mapped[str | None] = mapped_column(String, default=None)
    canonical_smiles: Mapped[str] = mapped_column(String)
    inchikey: Mapped[str] = mapped_column(String, index=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String, default="user")  # user|import|generated
    origin_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"), default=None, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentRun(Base):
    """Provenance hub: every generated molecule links back here via origin_run_id."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(String, default="local-org", index=True)
    project_id: Mapped[str | None] = mapped_column(String, default="local-project")

    goal_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="done")  # planning|running|done|failed
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    trace: Mapped[list] = mapped_column(JSON, default=list)  # list of tool-call records
    models_used: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    molecules: Mapped[list[Molecule]] = relationship(
        "Molecule", primaryjoin="AgentRun.id == Molecule.origin_run_id", viewonly=True
    )
