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
  POST /projects/{id}/libraries create a library; GET lists them
  GET  /libraries/{id}          a library + its molecules
  POST /libraries/{id}/import   import SMILES/CSV/SDF (firewalled + InChIKey-deduped)
  GET  /libraries/{id}/export   export SMILES/CSV/SDF (?format=)
  POST /molecules/diff          two molecules + per-descriptor deltas
  GET  /tools                   the typed tool registry (specs + compute class)
  POST /tools/{name}            execute any registered tool through the execution service
  POST /molecules/validate      validation firewall
  POST /molecules/profile       physchem descriptors, druglikeness, PAINS/BRENK
  POST /agent/design            the agentic design loop (plan -> tools -> synthesize)

Auth is gated by GLOWSKY_AUTH_ENABLED (default off -> single-tenant dev mode).
ADMET/docking backends are adapter-gated (GLOWSKY_ADMET_BACKEND / _DOCKING_BACKEND).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select

from apps.api.deps import (
    current_principal,
    load_library,
    load_project,
    load_run,
    require_write,
)
from apps.api.schemas import (
    BatchSubmitRequest,
    CredentialCreate,
    CredentialResponse,
    DesignRequest,
    DiffRequest,
    ImportRequest,
    JobSubmitRequest,
    LibraryCreate,
    LibraryResponse,
    PrincipalResponse,
    ProfileRequest,
    ProjectCreate,
    ProjectResponse,
    RouteResponse,
    RouteUpsert,
    SignupRequest,
    SignupResponse,
    ToolExecuteRequest,
    ValidateRequest,
)
from services.agent.orchestrator import DesignOrchestrator
from services.chemistry.adapters import BackendNotConfigured
from services.chemistry.adapters.wiring import configure_backends
from services.chemistry import io as chem_io
from services.chemistry.conformers import conformer_molblock
from services.chemistry.properties import profile
from services.chemistry.validation import validate_and_canonicalize
from services.reporting import build_markdown, notebook_json
from services.core.auth import Principal, audit, signup
from services.core.config import get_settings
from services.core.crypto import encrypt, mask
from services.core.db import init_db, session_scope
from services.core.models import (
    AgentRun,
    Library,
    LibraryMembership,
    LLMProviderCredential,
    ModelRouteOverride,
    Molecule,
    Project,
)
from services.llm_gateway.gateway import LLMGateway
from services.llm_gateway.types import TaskClass
from services.tools.catalog import build_registry
from services.tools.context import ExecutionContext
from services.tools.executor import ToolExecutionError, ToolExecutionService
from services.tools.store import get_store, is_terminal


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Select adapter-gated backends (ADMET/docking) per config. In eager mode this also
    # configures the in-process slow path; distributed workers self-configure on boot.
    app.state.backends = configure_backends()
    app.state.gateway = LLMGateway()
    app.state.registry = build_registry()  # built-ins + container tools (GLOWSKY_TOOLS_DIR)
    app.state.executor = ToolExecutionService(app.state.registry)
    app.state.orchestrator = DesignOrchestrator(app.state.gateway, app.state.executor)
    yield


app = FastAPI(title="Glowsky API", version="0.0.1", lifespan=lifespan)

# The desktop webview and the dev server are cross-origin to this API; without these
# headers the browser blocks every request (the app shows "Backend offline").
_cors = get_settings().cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_origin_regex=None if "*" not in _cors else ".*",
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        "backends": app.state.backends,
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


# --- Libraries & molecule I/O --------------------------------------------------

def _library_response(s, lib: Library) -> LibraryResponse:
    count = s.scalar(
        select(func.count()).select_from(LibraryMembership)
        .where(LibraryMembership.library_id == lib.id)
    ) or 0
    return LibraryResponse(
        id=lib.id, project_id=lib.project_id, name=lib.name,
        description=lib.description, kind=lib.kind, molecule_count=count,
    )


@app.post("/projects/{project_id}/libraries", response_model=LibraryResponse, status_code=201)
def create_library(
    project_id: str, req: LibraryCreate, principal: Principal = Depends(require_write)
) -> LibraryResponse:
    with session_scope() as s:
        load_project(s, project_id, principal)  # tenant check
        lib = Library(
            org_id=principal.org_id, project_id=project_id, name=req.name,
            description=req.description, kind=req.kind, created_by=principal.user_id,
        )
        s.add(lib)
        s.flush()
        audit(s, principal, "library.create", "library", lib.id, {"name": lib.name})
        return _library_response(s, lib)


@app.get("/projects/{project_id}/libraries", response_model=list[LibraryResponse])
def list_libraries(
    project_id: str, principal: Principal = Depends(current_principal)
) -> list[LibraryResponse]:
    with session_scope() as s:
        load_project(s, project_id, principal)
        rows = s.scalars(
            select(Library).where(Library.project_id == project_id)
            .order_by(Library.created_at.desc())
        ).all()
        return [_library_response(s, lib) for lib in rows]


@app.get("/libraries/{library_id}")
def get_library(library_id: str, principal: Principal = Depends(current_principal)) -> dict:
    with session_scope() as s:
        lib = load_library(s, library_id, principal)
        mols = _library_molecules(s, library_id)
        return {
            "library": _library_response(s, lib).model_dump(),
            "molecules": [
                {"id": m.id, "name": m.name, "canonical_smiles": m.canonical_smiles,
                 "inchikey": m.inchikey, "properties": m.properties, "source": m.source}
                for m in mols
            ],
        }


@app.post("/libraries/{library_id}/import", status_code=201)
def import_molecules(
    library_id: str, req: ImportRequest, principal: Principal = Depends(require_write)
) -> dict:
    """Parse SMILES/CSV/SDF, firewall every structure, dedup by InChIKey within the
    project, and add the molecules to the library. Bad rows are reported, not fatal."""
    try:
        parsed = chem_io.parse(
            req.content, req.format,
            **({"smiles_column": req.smiles_column, "name_column": req.name_column}
               if req.format.lower() == "csv" else {}),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    imported, duplicates, updated, invalid = 0, 0, 0, []
    with session_scope() as s:
        lib = load_library(s, library_id, principal)
        for pm in parsed:
            if not pm.valid:
                invalid.append({"input": pm.input, "error": pm.error})
                continue
            # Dedup molecules by (project, inchikey); reuse the existing row if present.
            mol = s.scalar(
                select(Molecule).where(
                    Molecule.org_id == principal.org_id,
                    Molecule.project_id == lib.project_id,
                    Molecule.inchikey == pm.inchikey,
                )
            )
            if mol is None:
                mol = Molecule(
                    org_id=principal.org_id, project_id=lib.project_id,
                    name=pm.name, canonical_smiles=pm.canonical_smiles,
                    inchikey=pm.inchikey, properties=pm.properties, source="import",
                    created_by=principal.user_id,
                )
                s.add(mol)
                s.flush()
            elif _merge_into(mol, pm):
                # Existing molecule: fold in any new properties / backfill the name.
                updated += 1
            # Add to the library if not already a member.
            exists = s.scalar(
                select(LibraryMembership).where(
                    LibraryMembership.library_id == library_id,
                    LibraryMembership.molecule_id == mol.id,
                )
            )
            if exists is None:
                s.add(LibraryMembership(
                    library_id=library_id, molecule_id=mol.id, added_by=principal.user_id))
                imported += 1
            else:
                duplicates += 1
        audit(s, principal, "library.import", "library", library_id,
              {"format": req.format, "imported": imported, "updated": updated,
               "invalid": len(invalid)})

    return {"imported": imported, "duplicates": duplicates, "updated": updated,
            "invalid": invalid, "invalid_count": len(invalid)}


def _is_empty(v) -> bool:
    return v is None or v == ""


def _merge_into(mol: Molecule, pm) -> bool:
    """Fill empty/missing fields on an existing molecule from an imported record.

    Fill-only, never overwrite: an imported value is applied only where the molecule
    has no value (key absent or empty) for that key; existing non-empty values and a
    non-empty name are left untouched. Reassigns `properties` (rather than mutating in
    place) so SQLAlchemy detects the JSON change. Returns True if anything changed.
    """
    changed = False
    if pm.properties:
        merged = dict(mol.properties or {})
        for key, value in pm.properties.items():
            if not _is_empty(value) and _is_empty(merged.get(key)):
                merged[key] = value
                changed = True
        if changed:
            mol.properties = merged
    if pm.name and not mol.name:
        mol.name = pm.name
        changed = True
    return changed


@app.get("/libraries/{library_id}/export")
def export_library(
    library_id: str, format: str = "smiles", principal: Principal = Depends(current_principal)
) -> PlainTextResponse:
    if format.lower() not in chem_io.SUPPORTED_FORMATS:
        raise HTTPException(status_code=422,
                            detail=f"unsupported format; use one of {chem_io.SUPPORTED_FORMATS}")
    with session_scope() as s:
        load_library(s, library_id, principal)
        mols = _library_molecules(s, library_id)
        rows = [chem_io.ExportRow(canonical_smiles=m.canonical_smiles, name=m.name,
                                  properties=m.properties or {}) for m in mols]
    body = chem_io.serialize(rows, format)
    ext = {"smiles": "smi", "csv": "csv", "sdf": "sdf"}[format.lower()]
    return PlainTextResponse(
        body, media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="library-{library_id}.{ext}"'},
    )


def _library_molecules(s, library_id: str) -> list[Molecule]:
    return s.scalars(
        select(Molecule).join(LibraryMembership, LibraryMembership.molecule_id == Molecule.id)
        .where(LibraryMembership.library_id == library_id)
        .order_by(LibraryMembership.added_at)
    ).all()


@app.post("/molecules/diff")
def molecule_diff(req: DiffRequest) -> dict:
    """Compare two molecules: identity + per-descriptor deltas (B − A)."""
    try:
        return chem_io.diff_molecules(req.smiles_a, req.smiles_b)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# --- Run export: reproducible notebook / Markdown report -----------------------

def _run_dict(run: AgentRun) -> dict:
    return {
        "id": run.id, "goal_text": run.goal_text, "status": run.status,
        "plan": run.plan, "trace": run.trace, "models_used": run.models_used,
        "explanation": run.explanation,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _run_molecule_dicts(s, run_id: str) -> list[dict]:
    rows = s.scalars(
        select(Molecule).where(Molecule.origin_run_id == run_id)
        .order_by(Molecule.created_at)
    ).all()
    return [
        {"name": m.name, "canonical_smiles": m.canonical_smiles, "inchikey": m.inchikey,
         "properties": m.properties or {}, "source": m.source}
        for m in rows
    ]


@app.get("/runs/{run_id}")
def get_run(run_id: str, principal: Principal = Depends(current_principal)) -> dict:
    with session_scope() as s:
        run = load_run(s, run_id, principal)
        return {"run": _run_dict(run), "molecules": _run_molecule_dicts(s, run_id)}


@app.get("/runs/{run_id}/export")
def export_run(
    run_id: str, format: str = "ipynb", principal: Principal = Depends(current_principal)
) -> PlainTextResponse:
    """Export a run as a reproducible Jupyter notebook (ipynb) or a Markdown report (md)."""
    fmt = format.lower()
    if fmt not in {"ipynb", "md"}:
        raise HTTPException(status_code=422, detail="format must be 'ipynb' or 'md'")
    with session_scope() as s:
        run = load_run(s, run_id, principal)
        run_d = _run_dict(run)
        mols = _run_molecule_dicts(s, run_id)

    if fmt == "ipynb":
        body = notebook_json(run_d, mols)
        media, ext = "application/x-ipynb+json", "ipynb"
    else:
        body = build_markdown(run_d, mols)
        media, ext = "text/markdown", "md"
    return PlainTextResponse(
        body, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="run-{run_id}.{ext}"'},
    )


# --- Settings: BYO-LLM credentials & model routing -----------------------------

SUPPORTED_PROVIDERS = [
    {"id": "anthropic", "label": "Anthropic", "needs_base_url": False},
    {"id": "openai", "label": "OpenAI", "needs_base_url": False},
    {"id": "groq", "label": "Groq", "needs_base_url": False},
    {"id": "local", "label": "Local / OpenAI-compatible", "needs_base_url": True},
]
_PROVIDER_IDS = {p["id"] for p in SUPPORTED_PROVIDERS}
_TASK_CLASSES = ("reasoning", "fast_triage", "codegen")


def _cred_response(c: LLMProviderCredential) -> CredentialResponse:
    return CredentialResponse(
        id=c.id, provider=c.provider, hint=c.hint, base_url=c.base_url,
        label=c.label, status=c.status, created_at=c.created_at.isoformat(),
    )


@app.get("/settings/providers")
def settings_providers() -> dict:
    """The providers the UI can offer to connect (static catalog)."""
    return {"providers": SUPPORTED_PROVIDERS}


@app.get("/settings/credentials", response_model=list[CredentialResponse])
def list_credentials(
    principal: Principal = Depends(current_principal),
) -> list[CredentialResponse]:
    """List the org's stored provider credentials — metadata + masked hint only."""
    with session_scope() as s:
        rows = s.scalars(
            select(LLMProviderCredential)
            .where(LLMProviderCredential.org_id == principal.org_id)
            .order_by(LLMProviderCredential.provider)
        ).all()
        return [_cred_response(c) for c in rows]


@app.post("/settings/credentials", response_model=CredentialResponse, status_code=201)
def add_credential(
    req: CredentialCreate, principal: Principal = Depends(require_write)
) -> CredentialResponse:
    """Store (or replace) a provider key. The key is encrypted at rest; only a masked
    hint is ever returned. One credential per (org, provider)."""
    provider = req.provider.strip().lower()
    if provider not in _PROVIDER_IDS:
        raise HTTPException(status_code=422,
                            detail=f"unsupported provider; one of {sorted(_PROVIDER_IDS)}")
    key = req.api_key.strip()
    if not key:
        raise HTTPException(status_code=422, detail="api_key is required")
    with session_scope() as s:
        existing = s.scalar(
            select(LLMProviderCredential).where(
                LLMProviderCredential.org_id == principal.org_id,
                LLMProviderCredential.provider == provider,
            )
        )
        if existing is not None:
            s.delete(existing)
            s.flush()
        cred = LLMProviderCredential(
            org_id=principal.org_id, provider=provider,
            encrypted_secret=encrypt(key), hint=mask(key),
            base_url=(req.base_url or None), label=req.label, created_by=principal.user_id,
        )
        s.add(cred)
        s.flush()
        audit(s, principal, "credential.add", "llm_credential", cred.id, {"provider": provider})
        return _cred_response(cred)


@app.delete("/settings/credentials/{credential_id}")
def delete_credential(
    credential_id: str, principal: Principal = Depends(require_write)
) -> dict:
    with session_scope() as s:
        cred = s.get(LLMProviderCredential, credential_id)
        if cred is None or cred.org_id != principal.org_id:
            raise HTTPException(status_code=404, detail="unknown credential")
        s.delete(cred)
        audit(s, principal, "credential.delete", "llm_credential", credential_id,
              {"provider": cred.provider})
    return {"deleted": credential_id}


@app.get("/settings/routes", response_model=list[RouteResponse])
def get_routes(principal: Principal = Depends(current_principal)) -> list[RouteResponse]:
    """Effective task-class routes: a per-org override if set, else the env default."""
    settings = get_settings()
    defaults = {
        "reasoning": settings.route_reasoning,
        "fast_triage": settings.route_fast_triage,
        "codegen": settings.route_codegen,
    }
    with session_scope() as s:
        overrides = {
            r.task_class: (r.provider, r.model)
            for r in s.scalars(
                select(ModelRouteOverride).where(ModelRouteOverride.org_id == principal.org_id)
            ).all()
        }
    out = []
    for tc in _TASK_CLASSES:
        if tc in overrides:
            provider, model = overrides[tc]
            source = "override"
        else:
            provider, _, model = defaults[tc].partition("/")
            source = "default"
        out.append(RouteResponse(task_class=tc, provider=provider, model=model, source=source))
    return out


@app.put("/settings/routes", response_model=RouteResponse)
def set_route(req: RouteUpsert, principal: Principal = Depends(require_write)) -> RouteResponse:
    tc = req.task_class.strip().lower()
    if tc not in _TASK_CLASSES:
        raise HTTPException(status_code=422, detail=f"task_class must be one of {_TASK_CLASSES}")
    provider, model = req.provider.strip(), req.model.strip()
    if not provider or not model:
        raise HTTPException(status_code=422, detail="provider and model are required")
    with session_scope() as s:
        row = s.scalar(
            select(ModelRouteOverride).where(
                ModelRouteOverride.org_id == principal.org_id,
                ModelRouteOverride.task_class == tc,
            )
        )
        if row is None:
            row = ModelRouteOverride(
                org_id=principal.org_id, task_class=tc, provider=provider, model=model,
                created_by=principal.user_id,
            )
            s.add(row)
        else:
            row.provider, row.model = provider, model
        s.flush()
        audit(s, principal, "route.set", "model_route", row.id, {"task_class": tc})
        return RouteResponse(task_class=tc, provider=provider, model=model, source="override")


@app.delete("/settings/routes/{task_class}")
def clear_route(task_class: str, principal: Principal = Depends(require_write)) -> dict:
    """Remove an override so the task class reverts to the env default."""
    with session_scope() as s:
        row = s.scalar(
            select(ModelRouteOverride).where(
                ModelRouteOverride.org_id == principal.org_id,
                ModelRouteOverride.task_class == task_class,
            )
        )
        if row is not None:
            s.delete(row)
            audit(s, principal, "route.clear", "model_route", row.id, {"task_class": task_class})
    return {"cleared": task_class}


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


@app.post("/molecules/conformer")
def molecule_conformer(req: ProfileRequest) -> dict:
    """Embed a single low-energy 3D conformer for the desktop 3D viewer.

    Firewalls the SMILES first (same path as profile), then returns an MDL MOL block
    with 3D coordinates plus its MMFF energy.
    """
    result = validate_and_canonicalize(req.smiles)
    if not result.valid:
        raise HTTPException(status_code=422, detail=f"invalid molecule: {result.error}")
    try:
        conformer = conformer_molblock(result.canonical_smiles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "canonical_smiles": result.canonical_smiles,
        "inchikey": result.inchikey,
        **conformer,
    }


@app.get("/examples/docking/sample")
def docking_sample() -> dict:
    """A real protein–ligand complex (RCSB 1HSG) for demoing the pose viewer.

    This is experimental crystallographic data shipped as a sample so the receptor +
    ligand-pose overlay is demonstrable without a configured docking engine — it is NOT
    a Glowsky-computed docking result. Live docking goes through the adapter-gated
    `dock` tool, which surfaces real Vina pose geometry when a backend is configured.
    """
    sample_dir = _REPO_ROOT / "examples" / "docking"
    return {
        "id": "1hsg",
        "name": "HIV-1 protease + indinavir (RCSB 1HSG)",
        "source": "RCSB PDB 1HSG — experimental structure, sample data (not computed)",
        "receptor_pdb": (sample_dir / "1hsg_receptor.pdb").read_text(),
        "ligand_pdb": (sample_dir / "1hsg_ligand.pdb").read_text(),
    }


@app.post("/agent/design")
async def design(
    req: DesignRequest, principal: Principal = Depends(current_principal)
) -> dict:
    # Scope the gateway to the caller's org so its stored BYO-LLM keys/routes apply
    # (falling back to env defaults, then the offline mock).
    orch = DesignOrchestrator(LLMGateway(org_id=principal.org_id), app.state.executor)

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
