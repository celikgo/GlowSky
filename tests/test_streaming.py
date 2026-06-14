"""WebSocket streaming of job progress, end-to-end through the API."""
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from apps.api.main import app


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
    with TestClient(app) as client:
        with client.websocket_connect("/jobs/does-not-exist/stream") as ws:
            events = _drain(ws)
    assert events and events[-1]["type"] == "failed"
