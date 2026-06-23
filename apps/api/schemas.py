from __future__ import annotations

from pydantic import BaseModel, Field


class ValidateRequest(BaseModel):
    smiles: str = Field(..., examples=["CC(=O)Oc1ccccc1C(=O)O"])


class ProfileRequest(BaseModel):
    smiles: str = Field(..., examples=["c1ccccc1"])


class ToolExecuteRequest(BaseModel):
    args: dict = Field(default_factory=dict, examples=[{"canonical_smiles": "c1ccccc1"}])
    seed: int | None = None


class JobSubmitRequest(BaseModel):
    tool: str = Field(..., examples=["generate_conformers"])
    args: dict = Field(default_factory=dict, examples=[{"canonical_smiles": "CCO", "n": 5}])
    seed: int | None = None


class BatchSubmitRequest(BaseModel):
    tool: str = Field(..., examples=["profile_molecule"])
    items: list[dict] = Field(
        ...,
        examples=[[{"canonical_smiles": "CCO"}, {"canonical_smiles": "c1ccccc1"}]],
    )


class DesignRequest(BaseModel):
    goal: str = Field(
        ...,
        examples=["Make 15 analogs with MW<300, logP 1-3, no PAINS, drug-like"],
    )
    seed_smiles: str = Field(..., examples=["c1ccccc1C(=O)O"])
    persist: bool = True
    project_id: str | None = Field(
        default=None, description="Scope the run + its molecules to this project."
    )


class ChatMessage(BaseModel):
    role: str = Field(..., examples=["user", "assistant"])
    content: str


class ChatContextMolecule(BaseModel):
    smiles: str = Field(..., examples=["c1ccccc1C(=O)O"])
    name: str | None = None


class ChatRequest(BaseModel):
    """One Composer turn. The client sends the full message history each turn (stateless
    server, mirroring /agent/design); `seed_smiles` carries the working molecule forward and
    `context_molecules` are the `@`-attached references."""

    messages: list[ChatMessage] = Field(
        ..., examples=[[{"role": "user", "content": "make 8 analogs, MW<300, no PAINS"}]]
    )
    seed_smiles: str | None = Field(default=None, examples=["c1ccccc1C(=O)O"])
    context_molecules: list[ChatContextMolecule] = Field(default_factory=list)
    persist: bool = True
    project_id: str | None = Field(
        default=None, description="Scope a resulting design run + its molecules to this project."
    )


# --- Auth & tenancy -----------------------------------------------------------


class LoginRequest(BaseModel):
    email: str = Field(..., examples=["chemist@lab.edu"])
    password: str = Field(..., description="Forwarded to carbon-auth; never stored by Glowsky.")


class RefreshRequest(BaseModel):
    refresh_token: str


class SelectTenantRequest(BaseModel):
    tenant_id: str = Field(..., description="The tenant to scope the session to.")


class TenantInfo(BaseModel):
    tenant_id: str
    name: str
    roles: list[str] = Field(default_factory=list)


class TokenResponse(BaseModel):
    """Relayed from carbon-auth. `tenant_scoped` is False when the user has 0 or 2+ tenants —
    the access token then carries no tenant and the caller must select one before using it."""

    access_token: str
    access_token_expires_in: int
    refresh_token: str | None = None
    refresh_token_expires_in: int | None = None
    tenant_scoped: bool


class PrincipalResponse(BaseModel):
    user_id: str
    org_id: str
    role: str
    email: str | None = None


class ProjectCreate(BaseModel):
    name: str = Field(..., examples=["Kinase inhibitor series"])
    description: str | None = None
    target_profile: dict = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    id: str
    org_id: str
    name: str
    description: str | None = None
    target_profile: dict = Field(default_factory=dict)
    created_by: str | None = None


# --- Libraries & molecule I/O -------------------------------------------------


class LibraryCreate(BaseModel):
    name: str = Field(..., examples=["Fragment hits"])
    description: str | None = None
    kind: str = Field("set", examples=["set", "series", "virtual_screen"])


class LibraryResponse(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None = None
    kind: str
    molecule_count: int = 0


class ImportRequest(BaseModel):
    format: str = Field(..., examples=["smiles", "csv", "sdf"])
    content: str = Field(..., description="Raw file content in the given format.")
    smiles_column: str = Field("smiles", description="CSV only: the SMILES column header.")
    name_column: str = Field("name", description="CSV only: the name column header.")


class DiffRequest(BaseModel):
    smiles_a: str = Field(..., examples=["c1ccccc1"])
    smiles_b: str = Field(..., examples=["Cc1ccccc1"])


# --- Settings: BYO-LLM credentials & model routing ----------------------------


class CredentialCreate(BaseModel):
    provider: str = Field(..., examples=["anthropic", "openai", "groq", "local"])
    api_key: str = Field(..., description="Plaintext key; encrypted at rest, never returned.")
    base_url: str | None = Field(default=None, description="For 'local' / OpenAI-compatible.")
    label: str | None = None


class CredentialResponse(BaseModel):
    id: str
    provider: str
    hint: str  # masked, e.g. "sk-…AB12"
    base_url: str | None = None
    label: str | None = None
    status: str
    created_at: str


class RouteUpsert(BaseModel):
    task_class: str = Field(..., examples=["reasoning", "fast_triage", "codegen"])
    provider: str = Field(..., examples=["anthropic"])
    model: str = Field(..., examples=["claude-opus-4-8"])


class RouteResponse(BaseModel):
    task_class: str
    provider: str
    model: str
    source: str  # "override" (per-org) | "default" (env)
