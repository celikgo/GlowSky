"""Slow-path execution + streaming.

Runs in Celery EAGER mode (no Redis) so the full submit -> run -> stream path is
exercised in-process. With GLOWSKY_REDIS_URL set, the same code runs on real workers.
"""
from services.tools.catalog import build_default_registry
from services.tools.executor import ToolExecutionService
from services.tools.store import get_store


def _svc():
    return ToolExecutionService(build_default_registry())


def test_submit_single_job_completes_with_result():
    svc = _svc()
    job_id = svc.submit("sa_score", {"canonical_smiles": "c1ccccc1"})
    job = get_store().get(job_id)
    assert job["status"] == "completed"
    assert job["result"]["output"]["sa_score"] > 0
    types = [e["type"] for e in job["events"]]
    assert types[0] == "queued" and "running" in types and types[-1] == "completed"


def test_submit_seeded_job_is_reproducible():
    svc = _svc()
    j1 = svc.submit("generate_conformers", {"canonical_smiles": "CCO", "n": 3}, seed=7)
    j2 = svc.submit("generate_conformers", {"canonical_smiles": "CCO", "n": 3}, seed=7)
    r1 = get_store().get(j1)["result"]["output"]
    r2 = get_store().get(j2)["result"]["output"]
    assert r1["energies_kcal_mol"] == r2["energies_kcal_mol"]


def test_failed_tool_is_captured_not_raised():
    svc = _svc()
    job_id = svc.submit("predict_admet", {"canonical_smiles": "c1ccccc1"})
    job = get_store().get(job_id)
    assert job["status"] == "failed"
    assert "not configured" in job["error"]
    assert job["events"][-1]["type"] == "failed"


def test_batch_job_streams_per_item_results():
    svc = _svc()
    items = [{"canonical_smiles": s} for s in ["CCO", "c1ccccc1", "CC(=O)O", "garbage(("]]
    job_id = svc.submit_batch("profile_molecule", items)
    job = get_store().get(job_id)
    assert job["status"] == "completed"
    summary = job["result"]
    assert summary["total"] == 4 and summary["succeeded"] == 3 and summary["failed"] == 1
    # one ITEM event per input (no silent drops), plus queued/running/completed
    item_events = [e for e in job["events"] if e["type"] == "item"]
    assert len(item_events) == 4
    assert any("error" in e["item"] for e in item_events)  # the bad SMILES reported
