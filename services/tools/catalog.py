"""The default tool catalog — every built-in tool registered with its ToolSpec.

Adding a tool is declarative: write the handler, register a ToolSpec here, and it
inherits routing, caching, the firewall, provenance, and discovery for free
(docs/13 §10/§11). Compute/latency classes determine fast-path vs slow-path.
"""
from __future__ import annotations

from services.chemistry.adapters.admet import predict_admet
from services.chemistry.adapters.docking import dock
from services.chemistry.conformers import generate_conformers
from services.chemistry.fingerprints import fingerprint
from services.chemistry.generative import generate_analogs
from services.chemistry.properties import compute_descriptors, druglikeness, profile, structural_alerts
from services.chemistry.scaffolds import murcko_scaffold
from services.chemistry.search import substructure_search
from services.chemistry.similarity import bulk_similarity, tanimoto
from services.chemistry.synthesizability import sa_score
from services.chemistry.validation import validate_and_canonicalize
from services.tools.registry import ToolRegistry
from services.tools.spec import (
    ComputeClass,
    Determinism,
    LatencyClass,
    Resources,
    ToolCategory,
    ToolSpec,
)

V = "0.1.0"


def _obj(**props) -> dict:
    required = [k for k in props]
    return {"type": "object", "properties": props, "required": required}


_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}
_NUM_LIST = {"type": "array", "items": {"type": "number"}}


def build_default_registry() -> ToolRegistry:
    reg = ToolRegistry()

    def add(spec: ToolSpec) -> None:
        reg.register(spec)

    # --- Cheminformatics / IO (fast path) -------------------------------
    add(ToolSpec(
        name="validate_molecule", version=V, category=ToolCategory.IO,
        summary="Validate, standardize, and canonicalize a SMILES string.",
        handler=lambda smiles: validate_and_canonicalize(smiles).as_dict(),
        input_schema=_obj(smiles=_STR),
    ))
    add(ToolSpec(
        name="compute_descriptors", version=V, category=ToolCategory.PROPERTY,
        summary="Physicochemical descriptors (MW, logP, TPSA, HBD/HBA, QED, ...).",
        handler=compute_descriptors, input_schema=_obj(canonical_smiles=_STR),
    ))
    add(ToolSpec(
        name="profile_molecule", version=V, category=ToolCategory.PROPERTY,
        summary="Descriptors + druglikeness + PAINS/BRENK alerts in one call.",
        handler=profile, input_schema=_obj(canonical_smiles=_STR),
    ))
    add(ToolSpec(
        name="druglikeness", version=V, category=ToolCategory.FILTERING,
        summary="Lipinski Ro5 and Veber rule checks.",
        handler=lambda canonical_smiles: druglikeness(compute_descriptors(canonical_smiles)),
        input_schema=_obj(canonical_smiles=_STR),
    ))
    add(ToolSpec(
        name="structural_alerts", version=V, category=ToolCategory.FILTERING,
        summary="Flag PAINS and BRENK problematic substructures.",
        handler=structural_alerts, input_schema=_obj(canonical_smiles=_STR),
    ))
    add(ToolSpec(
        name="fingerprint", version=V, category=ToolCategory.CHEMINFORMATICS,
        summary="Morgan (ECFP4) or MACCS fingerprint bit summary.",
        handler=fingerprint,
        input_schema={"type": "object", "properties": {"canonical_smiles": _STR, "kind": _STR},
                      "required": ["canonical_smiles"]},
    ))
    add(ToolSpec(
        name="tanimoto_similarity", version=V, category=ToolCategory.CHEMINFORMATICS,
        summary="Tanimoto similarity (Morgan) between two molecules.",
        handler=tanimoto, input_schema=_obj(smiles_a=_STR, smiles_b=_STR),
    ))
    add(ToolSpec(
        name="bulk_similarity", version=V, category=ToolCategory.SEARCH,
        summary="Rank a set of molecules by similarity to a query.",
        handler=bulk_similarity, batchable=True,
        input_schema={"type": "object",
                      "properties": {"query_smiles": _STR, "smiles_list": _STR_LIST,
                                     "top_k": {"type": "integer"}},
                      "required": ["query_smiles", "smiles_list"]},
    ))
    add(ToolSpec(
        name="substructure_search", version=V, category=ToolCategory.SEARCH,
        summary="Find molecules matching a SMARTS pattern.",
        handler=substructure_search, batchable=True,
        input_schema=_obj(query_smarts=_STR, smiles_list=_STR_LIST),
    ))
    add(ToolSpec(
        name="murcko_scaffold", version=V, category=ToolCategory.CHEMINFORMATICS,
        summary="Bemis–Murcko scaffold (and generic scaffold).",
        handler=murcko_scaffold, input_schema=_obj(canonical_smiles=_STR),
    ))
    add(ToolSpec(
        name="sa_score", version=V, category=ToolCategory.PROPERTY,
        summary="Synthetic accessibility (Ertl & Schuffenhauer), 1=easy..10=hard.",
        handler=sa_score, input_schema=_obj(canonical_smiles=_STR),
    ))

    # --- Generative (CPU-heavy, emits structures -> firewall) -----------
    add(ToolSpec(
        name="generate_analogs", version=V, category=ToolCategory.GENERATIVE,
        summary="Enumerate validated R-group analogs of a parent molecule.",
        handler=generate_analogs, emits_structures=True,
        compute_class=ComputeClass.CPU_HEAVY, latency_class=LatencyClass.SHORT,
        input_schema={"type": "object",
                      "properties": {"canonical_smiles": _STR,
                                     "max_analogs": {"type": "integer"}},
                      "required": ["canonical_smiles"]},
    ))

    # --- 3D / conformers (CPU-heavy, seeded) ----------------------------
    add(ToolSpec(
        name="generate_conformers", version=V, category=ToolCategory.CHEMINFORMATICS,
        summary="ETKDG 3D conformer generation + MMFF energies.",
        handler=generate_conformers,
        compute_class=ComputeClass.CPU_HEAVY, latency_class=LatencyClass.SHORT,
        determinism=Determinism.SEEDED,
        resources=Resources(cpu=2, mem_mb=1024, timeout_s=120),
        input_schema={"type": "object",
                      "properties": {"canonical_smiles": _STR, "n": {"type": "integer"}},
                      "required": ["canonical_smiles"]},
    ))

    # --- Heavy predictors / engines (slow path; adapter-gated) ----------
    add(ToolSpec(
        name="predict_admet", version=V, category=ToolCategory.PROPERTY,
        summary="ADMET prediction via a pluggable model backend (adapter-gated).",
        handler=predict_admet,
        compute_class=ComputeClass.GPU, latency_class=LatencyClass.LONG,
        resources=Resources(cpu=2, mem_mb=4096, gpu=1, timeout_s=120),
        input_schema={"type": "object",
                      "properties": {"canonical_smiles": _STR, "endpoints": _STR_LIST},
                      "required": ["canonical_smiles"]},
    ))
    add(ToolSpec(
        name="dock", version=V, category=ToolCategory.STRUCTURE_BASED,
        summary="Dock a ligand into a receptor pocket via a pluggable engine (adapter-gated).",
        handler=dock,
        compute_class=ComputeClass.CPU_HEAVY, latency_class=LatencyClass.LONG,
        resources=Resources(cpu=4, mem_mb=4096, timeout_s=600),
        input_schema=_obj(ligand_smiles=_STR, receptor_ref=_STR, center=_NUM_LIST, size=_NUM_LIST),
    ))

    return reg


def build_registry(settings=None) -> ToolRegistry:
    """Full registry = built-in catalog + any container tools under GLOWSKY_TOOLS_DIR.

    Used by the API and Celery workers (both must see the same tools). Kept separate
    from build_default_registry() so the built-in catalog stays pure for unit tests.
    """
    from services.core.config import get_settings
    from services.tools.manifest import load_container_tools

    settings = settings or get_settings()
    reg = build_default_registry()
    if settings.tools_dir:
        load_container_tools(reg, settings.tools_dir)
    return reg
