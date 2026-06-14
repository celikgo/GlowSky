from __future__ import annotations

from pydantic import BaseModel, Field


class DesignConstraints(BaseModel):
    mw_max: float | None = None
    logp_min: float | None = None
    logp_max: float | None = None
    exclude_pains: bool = False
    require_lipinski: bool = False


class DesignPlan(BaseModel):
    max_analogs: int = 20
    constraints: DesignConstraints = Field(default_factory=DesignConstraints)
    rationale: str = ""


class ToolCallRecord(BaseModel):
    """One entry in the execution trace — powers transparency UI + notebook export."""

    step: int
    tool: str
    tool_version: str
    compute_class: str
    input: dict
    summary: str  # short human-readable result summary (full outputs live in candidates)
    duration_ms: float = 0.0
    cache_hit: bool = False
    calls: int = 1  # number of underlying tool executions this record aggregates


class Candidate(BaseModel):
    smiles: str
    inchikey: str
    modification: str
    properties: dict
    passed_filters: bool
    score: float


class DesignRunResult(BaseModel):
    run_id: str | None = None
    goal: str
    parent_smiles: str
    plan: DesignPlan
    candidates: list[Candidate]
    trace: list[ToolCallRecord]
    explanation: str
    models_used: dict
