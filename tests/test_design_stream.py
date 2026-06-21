"""The live design-streaming WebSocket (`/agent/design/stream`), end-to-end.

Covers the path the Composer subscribes to: the orchestrator's milestones are relayed
as they happen, then a terminal `complete` (or `error`) frame closes the socket. The
synchronous `/agent/design` POST is covered in test_api; the orchestrator emit contract
in test_agent — this exercises the WS endpoint that stitches the two together.
"""
import pytest
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


def test_design_stream_relays_milestones_then_completes():
    with TestClient(app) as client:
        with client.websocket_connect("/agent/design/stream") as ws:
            ws.send_json({
                "goal": "make 8 analogs with MW<300, no PAINS, drug-like",
                "seed_smiles": "c1ccccc1C(=O)O",
                "persist": True,
            })
            events = _drain(ws)

    types = [e["type"] for e in events]
    # The full milestone sequence streams, in order, before the terminal frame.
    assert types[0] == "started"
    assert "plan" in types and "candidate" in types and "ranked" in types
    assert "explanation" in types
    assert types.index("plan") < types.index("candidate") < types.index("ranked")
    assert types[-1] == "complete"

    # A candidate streamed mid-loop carries real profiled structure.
    first_candidate = next(e for e in events if e["type"] == "candidate")
    assert "mw" in first_candidate["candidate"]["properties"]

    # `ranked` lists every streamed candidate (the UI reorders cards by this).
    streamed = {e["candidate"]["inchikey"] for e in events if e["type"] == "candidate"}
    ranked = next(e for e in events if e["type"] == "ranked")
    assert set(ranked["order"]) == streamed

    # The terminal frame carries the fully assembled, persisted result.
    result = events[-1]["result"]
    assert result["run_id"]  # persist=True -> provenance hub created
    assert len(result["candidates"]) == len(streamed)
    assert result["models_used"]["reasoning"] == "mock/mock"


def test_design_stream_reports_invalid_seed_as_error_frame():
    with TestClient(app) as client:
        with client.websocket_connect("/agent/design/stream") as ws:
            ws.send_json({"goal": "make analogs", "seed_smiles": "not-a-molecule(("})
            events = _drain(ws)

    assert events and events[-1]["type"] == "error"
    assert "invalid" in events[-1]["error"].lower()


def test_design_stream_requires_goal_and_seed():
    with TestClient(app) as client:
        with client.websocket_connect("/agent/design/stream") as ws:
            ws.send_json({"goal": "", "seed_smiles": ""})
            events = _drain(ws)

    assert events == [{"type": "error", "error": "goal and seed_smiles are required"}]


@pytest.mark.real_auth
def test_design_stream_rejects_missing_or_bad_token():
    # real_auth lifts the conftest principal override, so the WS runs real token auth.
    with TestClient(app) as client:
        with client.websocket_connect("/agent/design/stream") as ws:
            ws.send_json({"goal": "make analogs", "seed_smiles": "c1ccccc1C(=O)O"})
            events = _drain(ws)
        assert events == [{"type": "error", "error": "missing token"}]

        with client.websocket_connect("/agent/design/stream") as ws:
            ws.send_json({
                "goal": "make analogs",
                "seed_smiles": "c1ccccc1C(=O)O",
                "token": "not-a-real-jwt",
            })
            events = _drain(ws)
        assert events == [{"type": "error", "error": "invalid token"}]
