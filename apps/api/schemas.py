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


# --- Auth & tenancy -----------------------------------------------------------


class SignupRequest(BaseModel):
    email: str = Field(..., examples=["maya@lab.edu"])
    org_name: str = Field("Personal", examples=["Maya's Lab"])


class SignupResponse(BaseModel):
    org_id: str
    user_id: str
    email: str
    # Plaintext API key — returned exactly once. Send as `Authorization: Bearer <key>`.
    api_key: str


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
