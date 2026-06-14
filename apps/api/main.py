"""Glowsky API — the vertical slice surface (Phase 0 + Phase 1 auth/tenancy).

Endpoints:
  GET  /health                  liveness + resolved (secret-free) model routes
  POST /auth/signup             create an org + user, mint a bearer API key (once)
  GET  /auth/me                 the resolved principal for the request
  POST /projects                create a project (tenant-scoped)
  GET  /projects                list projects in the caller's org
  GET  /projects/{id}           a project (404 across tenants)
  GET  /projects/{id}/molecules molecules in a project
  GET  /projects/{id}/runs      agent runs in a project
  GET  /tools                   the typed tool registry (specs + compute class)
  POST /tools/{name}            execute any registered tool through the execution service
  POST /molecules/validate      validation firewall
  POST /molecules/profile       physchem descriptors, druglikeness, PAINS/BRENK
  POST /agent/design            the agentic design loop (plan -> tools -> synthesize)

Auth is gated by GLOWSKY_AUTH_ENABLED (default off -> single-tenant dev mode).
Phase 1 next adds WebSocket streaming polish and the slow-path worker queue.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from apps.api.deps import current_principal, load_project, require_write
from apps.api.schemas import (
    BatchSubmitRequest,
    DesignRequest,
    JobSubmitRequest,
    PrincipalResponse,
    ProfileRequest,
    ProjectCreate,
    ProjectResponse,
    SignupRequest,
    SignupResponse,
    ToolExecuteRequest,
    ValidateRequest,
)
from services.agent.orchestrator import DesignOrchestrator
from services.chemistry.adapters import BackendNotConfigured
from services.chemistry.properties import profile
from services.chemistry.validation import validate_and_canonicalize
from services.core.auth import Principal, audit, signup
from services.core.db import init_db, session_scope
from services.core.models import AgentRun, Molecule, Project
from services.llm_gateway.gateway import LLMGateway
from services.llm_gateway.types import TaskClass
from services.tools.catalog import build_registry
from services.tools.context import ExecutionContext
from services.tools.executor import ToolExecutionError, ToolExecutionService
from services.tools.store import get_store, is_terminal


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.gateway = LLMGateway()
    app.state.registry = build_registry()  # built-ins + container tools (GLOWSKY_TOOLS_DIR)
    app.state.executor = ToolExecutionService(app.state.registry)
    app.state.orchestrator = DesignOrchestrator(app.state.gateway, app.state.executor)
    yield


app = FastAPI(title="Glowsky API", version="0.0.1", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    gw: LLMGateway = app.state.gateway
    return {
        "status": "ok",
        "routes": {
            "reasoning": gw.route_for(TaskClass.REASONING),
            "fast_triage": gw.route_for(TaskClass.FAST_TRIAGE),
            "codegen": gw.route_for(TaskClass.CODEGEN),
        },
        "tools": len(app.state.registry.list()),
    }


# --- Auth & tenancy ------------------------------------------------------------

@app.post("/auth/signup", response_model=SignupResponse, status_code=201)
def auth_signup(req: SignupRequest) -> SignupResponse:
    """Create an org + user and mint a bearer API key. Open even when auth is enabled —
    it's how a new tenant obtains its first credential. The key is returned exactly once."""
    with session_scope() as s:
        try:
            principal, token = signup(s, req.email.strip().lower(), req.org_name.strip())
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return SignupResponse(
            org_id=principal.org_id, user_id=principal.user_id,
            email=principal.email or req.email, api_key=token,
        )


@app.get("/auth/me", response_model=PrincipalResponse)
def auth_me(principal: Principal = Depends(current_principal)) -> PrincipalResponse:
    return PrincipalResponse(
        user_id=principal.user_id, org_id=principal.org_id,
        role=principal.role, email=principal.email,
    )


@app.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(
    req: ProjectCreate, principal: Principal = Depends(require_write)
) -> ProjectResponse:
    with session_scope() as s:
        proj = Project(
            org_id=principal.org_id, name=req.name, description=req.description,
            target_profile=req.target_profile, created_by=principal.user_id,
        )
        s.add(proj)
        s.flush()
        audit(s, principal, "project.create", "project", proj.id, {"name": proj.name})
        return _project_response(proj)


@app.get("/projects", response_model=list[ProjectResponse])
def list_projects(principal: Principal = Depends(current_principal)) -> list[ProjectResponse]:
    with session_scope() as s:
        rows = s.scalars(
            select(Project).where(Project.org_id == principal.org_id)
            .order_by(Project.created_at.desc())
        ).all()
        return [_project_response(p) for p in rows]


@app.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str, principal: Principal = Depends(current_principal)
) -> ProjectResponse:
    with session_scope() as s:
        return _project_response(load_project(s, project_id, principal))


@app.get("/projects/{project_id}/molecules")
def project_molecules(
    project_id: str, principal: Principal = Depends(current_principal)
) -> dict:
    with session_scope() as s:
        load_project(s, project_id, principal)  # enforce tenant isolation
        rows = s.scalars(
            select(Molecule).where(
                Molecule.org_id == principal.org_id, Molecule.project_id == project_id
            ).order_by(Molecule.created_at.desc())
        ).all()
        return {"molecules": [
            {"id": m.id, "name": m.name, "canonical_smiles": m.canonical_smiles,
             "inchikey": m.inchikey, "properties": m.properties, "source": m.source,
             "origin_run_id": m.origin_run_id}
            for m in rows
        ]}


@app.get("/projects/{project_id}/runs")
def project_runs(
    project_id: str, principal: Principal = Depends(current_principal)
) -> dict:
    with session_scope() as s:
        load_project(s, project_id, principal)
        rows = s.scalars(
            select(AgentRun).where(
                AgentRun.org_id == principal.org_id, AgentRun.project_id == project_id
            ).order_by(AgentRun.created_at.desc())
        ).all()
        return {"runs": [
            {"id": r.id, "goal_text": r.goal_text, "status": r.status,
             "created_by": r.created_by, "created_at": r.created_at.isoformat()}
            for r in rows
        ]}


def _project_response(p: Project) -> ProjectResponse:
    return ProjectResponse(
        id=p.id, org_id=p.org_id, name=p.name, description=p.description,
        target_profile=p.target_profile, created_by=p.created_by,
    )


@app.get("/tools")
def tools() -> dict:
    return {"tools": app.state.registry.specs()}


@app.post("/tools/{name}")
def execute_tool(name: str, req: ToolExecuteRequest) -> dict:
    """Run any registered tool through the execution service (cache + firewall + provenance)."""
    executor: ToolExecutionService = app.state.executor
    try:
        result = executor.execute(name, req.args, ExecutionContext(), seed=req.seed)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolExecutionError as exc:
        # Adapter-gated tools (ADMET/docking) report a clear 'not configured' error.
        status = 501 if isinstance(exc.__cause__, BackendNotConfigured) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"output": result.output, "provenance": result.record.as_dict()}


# --- Slow path: submit jobs, stream/poll results -------------------------------

@app.post("/jobs")
def submit_job(req: JobSubmitRequest) -> dict:
    """Submit a slow-path tool call (e.g. conformers, docking). Returns a job_id to
    stream over WS /jobs/{id}/stream or poll via GET /jobs/{id}."""
    executor: ToolExecutionService = app.state.executor
    try:
        job_id = executor.submit(req.tool, req.args, ExecutionContext(), seed=req.seed)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"job_id": job_id}


@app.post("/jobs/batch")
def submit_batch(req: BatchSubmitRequest) -> dict:
    """Submit a tool over many inputs (library-scale). Per-item results stream live."""
    executor: ToolExecutionService = app.state.executor
    try:
        job_id = executor.submit_batch(req.tool, req.items, ExecutionContext())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = get_store().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    return job


@app.websocket("/jobs/{job_id}/stream")
async def stream_job(ws: WebSocket, job_id: str) -> None:
    """Relay the job's event stream live, then close on the terminal event.

    Streams by reading the append-only event log incrementally — identical behaviour
    whether the job ran on a Celery worker (Redis) or eagerly in-process."""
    await ws.accept()
    store = get_store()
    sent = 0
    waited = 0.0
    TIMEOUT_S = 120.0
    try:
        while True:
            events = store.events(job_id)
            for ev in events[sent:]:
                await ws.send_json(ev)
                sent += 1
            job = store.get(job_id)
            if is_terminal(job) and sent >= len(store.events(job_id)):
                break
            if job is None and waited > 1.0:
                await ws.send_json({"type": "failed", "error": f"unknown job: {job_id}"})
                break
            await asyncio.sleep(0.05)
            waited += 0.05
            if waited > TIMEOUT_S:
                await ws.send_json({"type": "failed", "error": "stream timed out"})
                break
    except WebSocketDisconnect:
        return
    await ws.close()


@app.post("/molecules/validate")
def validate(req: ValidateRequest) -> dict:
    return validate_and_canonicalize(req.smiles).as_dict()


@app.post("/molecules/profile")
def profile_molecule(req: ProfileRequest) -> dict:
    result = validate_and_canonicalize(req.smiles)
    if not result.valid:
        raise HTTPException(status_code=422, detail=f"invalid molecule: {result.error}")
    return {
        "canonical_smiles": result.canonical_smiles,
        "inchikey": result.inchikey,
        "properties": profile(result.canonical_smiles),
    }


@app.post("/agent/design")
async def design(
    req: DesignRequest, principal: Principal = Depends(current_principal)
) -> dict:
    orch: DesignOrchestrator = app.state.orchestrator

    # Validate project ownership up front (tenant isolation) before any compute.
    if req.project_id is not None:
        with session_scope() as s:
            load_project(s, req.project_id, principal)

    ctx = ExecutionContext(org_id=principal.org_id, project_id=req.project_id)
    try:
        result = await orch.run(req.goal, req.seed_smiles, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if req.persist:
        result.run_id = _persist(result, principal, req.project_id)
    return result.model_dump()


def _persist(result, principal: Principal, project_id: str | None) -> str:
    """Store the run (provenance hub) and the molecules it produced, linked back to it.

    Everything is scoped to the principal's org and (optionally) project, and stamped
    with created_by for audit/provenance.
    """
    with session_scope() as s:
        run = AgentRun(
            org_id=principal.org_id, project_id=project_id, created_by=principal.user_id,
            goal_text=result.goal,
            plan=result.plan.model_dump(),
            trace=[t.model_dump() for t in result.trace],
            models_used=result.models_used,
            explanation=result.explanation,
        )
        s.add(run)
        s.flush()  # assign run.id
        s.add(Molecule(
            org_id=principal.org_id, project_id=project_id, created_by=principal.user_id,
            canonical_smiles=result.parent_smiles, inchikey="", name="parent",
            source="user", origin_run_id=run.id,
        ))
        for c in result.candidates:
            if not c.passed_filters:
                continue
            s.add(Molecule(
                org_id=principal.org_id, project_id=project_id, created_by=principal.user_id,
                canonical_smiles=c.smiles, inchikey=c.inchikey, properties=c.properties,
                source="generated", origin_run_id=run.id,
            ))
        audit(s, principal, "run.design", "agent_run", run.id,
              {"project_id": project_id, "n_candidates": len(result.candidates)})
        return run.id
