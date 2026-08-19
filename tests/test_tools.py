"""Tool subsystem: registry, executor (cache + firewall + provenance), and the
new chemistry tools."""
import pytest

from services.chemistry.adapters import BackendNotConfigured
from services.tools.catalog import build_default_registry
from services.tools.executor import ToolExecutionError, ToolExecutionService
from services.tools.spec import ComputeClass


@pytest.fixture
def svc():
    return ToolExecutionService(build_default_registry())


def test_registry_lists_tools_with_compute_class():
    specs = build_default_registry().specs()
    names = {s["name"] for s in specs}
    # cheminformatics + property + generative + slow-path adapters all present
    assert {"fingerprint", "tanimoto_similarity", "murcko_scaffold", "sa_score",
            "generate_analogs", "predict_admet", "dock"} <= names
    docking = next(s for s in specs if s["name"] == "dock")
    assert docking["compute_class"] in {c.value for c in ComputeClass}


def test_executor_records_provenance(svc):
    res = svc.execute("compute_descriptors", {"canonical_smiles": "c1ccccc1"})
    assert "mw" in res.output
    rec = res.record
    assert rec.tool == "compute_descriptors" and rec.version == "0.1.0"
    assert rec.compute_class == "cpu_light"
    assert rec.cache_hit is False and rec.input_hash


def test_executor_caches_deterministic_results(svc):
    first = svc.execute("compute_descriptors", {"canonical_smiles": "CCO"})
    second = svc.execute("compute_descriptors", {"canonical_smiles": "CCO"})
    assert first.record.cache_hit is False
    assert second.record.cache_hit is True
    assert first.output == second.output


def test_firewall_runs_on_structure_emitting_tools(svc):
    res = svc.execute("generate_analogs", {"canonical_smiles": "c1ccccc1C(=O)O", "max_analogs": 5})
    assert len(res.output) > 0  # every emitted structure already passed the firewall


def test_fingerprint_and_similarity(svc):
    fp = svc.execute("fingerprint", {"canonical_smiles": "c1ccccc1"}).output
    assert fp["n_bits"] == 2048 and fp["count"] > 0
    sim = svc.execute("tanimoto_similarity", {"smiles_a": "c1ccccc1", "smiles_b": "c1ccccc1"}).output
    assert sim["similarity"] == 1.0


def test_bulk_similarity_ranks(svc):
    out = svc.execute("bulk_similarity", {
        "query_smiles": "c1ccccc1C(=O)O",
        "smiles_list": ["c1ccccc1C(=O)O", "CCO", "c1ccccc1C"],
    }).output
    sims = [r["similarity"] for r in out["results"]]
    assert sims == sorted(sims, reverse=True)
    assert out["results"][0]["similarity"] == 1.0  # identical query ranks first


def test_substructure_search(svc):
    out = svc.execute("substructure_search", {
        "query_smarts": "c1ccccc1", "smiles_list": ["c1ccccc1C(=O)O", "CCO", "c1ccncc1"],
    }).output
    assert "c1ccccc1C(=O)O" in out["matched"] and "CCO" not in out["matched"]


def test_scaffold_and_sa_score(svc):
    scaf = svc.execute("murcko_scaffold", {"canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O"}).output
    assert scaf["scaffold"]
    sa = svc.execute("sa_score", {"canonical_smiles": "c1ccccc1"}).output
    assert 1.0 <= sa["sa_score"] <= 10.0 and isinstance(sa["synthesizable"], bool)


def test_conformers_are_seeded_and_reproducible(svc):
    a = svc.execute("generate_conformers", {"canonical_smiles": "CCO", "n": 3}, seed=42).output
    b = svc.execute("generate_conformers", {"canonical_smiles": "CCO", "n": 3}, seed=42).output
    assert a["n_generated"] >= 1
    assert a["energies_kcal_mol"] == b["energies_kcal_mol"]  # same seed -> same result


def test_structural_alerts_include_brenk(svc):
    out = svc.execute("structural_alerts", {"canonical_smiles": "c1ccccc1C(=O)O"}).output
    assert "has_pains" in out and "has_brenk" in out


def test_adapter_gated_tools_report_not_configured(svc):
    with pytest.raises(ToolExecutionError) as ei:
        svc.execute("predict_admet", {"canonical_smiles": "c1ccccc1"})
    assert isinstance(ei.value.__cause__, BackendNotConfigured)

    with pytest.raises(ToolExecutionError) as ei2:
        svc.execute("dock", {"ligand_smiles": "c1ccccc1", "receptor_ref": "x",
                             "center": [0, 0, 0], "size": [20, 20, 20]})
    assert isinstance(ei2.value.__cause__, BackendNotConfigured)


def test_unknown_tool_raises_keyerror(svc):
    with pytest.raises(KeyError):
        svc.execute("nonexistent_tool", {})
