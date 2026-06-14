"""Glowsky Phase 0 API — the vertical slice surface.

Endpoints:
  GET  /health              liveness + resolved (secret-free) model routes
  GET  /tools               the typed tool registry (discovery: specs + compute class)
  POST /tools/{name}        execute any registered tool through the execution service
  POST /molecules/validate  validation firewall
  POST /molecules/profile   physchem descriptors, druglikeness, PAINS/BRENK
  POST /agent/design        the agentic design loop (plan -> tools -> synthesize)

Phase 1 adds auth, tenancy, WebSocket streaming, and the slow-path worker queue.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from apps.api.schemas import (
    BatchSubmitRequest,
    DesignRequest,
    JobSubmitRequest,
    ProfileRequest,
    ToolExecuteRequest,
    ValidateRequest,
)
from services.agent.orchestrator import DesignOrchestrator
from services.chemistry.adapters import BackendNotConfigured
from services.chemistry.properties import profile
from services.chemistry.validation import validate_and_canonicalize
from services.core.db import init_db, session_scope
from services.core.models import AgentRun, Molecule
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
async def design(req: DesignRequest) -> dict:
    orch: DesignOrchestrator = app.state.orchestrator
    try:
        result = await orch.run(req.goal, req.seed_smiles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if req.persist:
        result.run_id = _persist(result)
    return result.model_dump()


def _persist(result) -> str:
    """Store the run (provenance hub) and the molecules it produced, linked back to it."""
    with session_scope() as s:
        run = AgentRun(
            goal_text=result.goal,
            plan=result.plan.model_dump(),
            trace=[t.model_dump() for t in result.trace],
            models_used=result.models_used,
            explanation=result.explanation,
        )
        s.add(run)
        s.flush()  # assign run.id
        s.add(Molecule(
            canonical_smiles=result.parent_smiles, inchikey="", name="parent",
            source="user", origin_run_id=run.id,
        ))
        for c in result.candidates:
            if not c.passed_filters:
                continue
            s.add(Molecule(
                canonical_smiles=c.smiles, inchikey=c.inchikey, properties=c.properties,
                source="generated", origin_run_id=run.id,
            ))
        return run.id
