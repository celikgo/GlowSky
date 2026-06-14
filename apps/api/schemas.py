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
