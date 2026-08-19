"""WebSocket streaming of job progress, end-to-end through the API."""
import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from apps.api.main import app
from tests.conftest import tenant


def _drain(ws) -> list[dict]:
    events: list[dict] = []
    try:
        while True:
            events.append(ws.receive_json())
    except WebSocketDisconnect:
        pass
    return events


def test_stream_single_job_over_websocket():
    with TestClient(app) as client:
        job_id = client.post(
            "/jobs", json={"tool": "generate_conformers",
                           "args": {"canonical_smiles": "CCO", "n": 3}, "seed": 1}
        ).json()["job_id"]

        with client.websocket_connect(f"/jobs/{job_id}/stream") as ws:
            events = _drain(ws)

    types = [e["type"] for e in events]
    assert types[0] == "queued"
    assert "running" in types
    assert types[-1] == "completed"
    assert events[-1]["result"]["output"]["n_generated"] >= 1


def test_stream_batch_job_emits_item_events():
    with TestClient(app) as client:
        job_id = client.post(
            "/jobs/batch",
            json={"tool": "sa_score",
                  "items": [{"canonical_smiles": "CCO"}, {"canonical_smiles": "c1ccccc1"}]},
        ).json()["job_id"]

        with client.websocket_connect(f"/jobs/{job_id}/stream") as ws:
            events = _drain(ws)

    item_events = [e for e in events if e["type"] == "item"]
    assert len(item_events) == 2
    assert item_events[-1]["done"] == 2 and item_events[-1]["total"] == 2
    assert events[-1]["type"] == "completed"


def test_unknown_job_stream_reports_failure():
    with TestClient(app) as client, client.websocket_connect("/jobs/does-not-exist/stream") as ws:
        events = _drain(ws)
    assert events and events[-1]["type"] == "failed"


# --- tenant isolation (real JWTs) ---------------------------------------------


@pytest.mark.real_auth
def test_jobs_are_isolated_between_tenants():
    """Tenant B can neither read nor stream tenant A's job — the payload carries
    docking poses / screening output that must never cross an org boundary.

    Denial is 404 / 'unknown job' (never 403) so a job's existence is not an oracle,
    mirroring load_project/load_library/load_run. Fails without the org check on
    GET /jobs/{id} and WS /jobs/{id}/stream (the read side used to have none)."""
    a, b = tenant(), tenant()
    ha, hb = a["headers"], b["headers"]
    tok_a = ha["Authorization"].split(" ", 1)[1]
    tok_b = hb["Authorization"].split(" ", 1)[1]

    with TestClient(app) as client:
        job_id = client.post(
            "/jobs",
            json={"tool": "generate_conformers",
                  "args": {"canonical_smiles": "CCO", "n": 3}, "seed": 1},
            headers=ha,
        ).json()["job_id"]

        # Owner reads its own job, and org_id is not leaked back to the client.
        owned = client.get(f"/jobs/{job_id}", headers=ha)
        assert owned.status_code == 200
        assert "org_id" not in owned.json()

        # Tenant B: 404 over REST, 'unknown job' over WS — and NO event of A's leaks.
        assert client.get(f"/jobs/{job_id}", headers=hb).status_code == 404
        with client.websocket_connect(f"/jobs/{job_id}/stream?token={tok_b}") as ws:
            leaked = _drain(ws)
        assert leaked == [{"type": "failed", "error": f"unknown job: {job_id}"}]

        # A can still stream its own job to completion (guard doesn't over-block).
        with client.websocket_connect(f"/jobs/{job_id}/stream?token={tok_a}") as ws:
            mine = _drain(ws)
        assert mine[-1]["type"] == "completed"


@pytest.mark.real_auth
def test_batch_jobs_are_isolated_between_tenants():
    """The batch surface leaks an entire screening library if unscoped — assert it
    too returns 'unknown job' to a foreign tenant."""
    a, b = tenant(), tenant()
    with TestClient(app) as client:
        job_id = client.post(
            "/jobs/batch",
            json={"tool": "sa_score",
                  "items": [{"canonical_smiles": "CCO"}, {"canonical_smiles": "c1ccccc1"}]},
            headers=a["headers"],
        ).json()["job_id"]

        assert client.get(f"/jobs/{job_id}", headers=b["headers"]).status_code == 404
        tok_b = b["headers"]["Authorization"].split(" ", 1)[1]
        with client.websocket_connect(f"/jobs/{job_id}/stream?token={tok_b}") as ws:
            leaked = _drain(ws)
        assert leaked == [{"type": "failed", "error": f"unknown job: {job_id}"}]
