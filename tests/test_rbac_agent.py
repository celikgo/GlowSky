"""RBAC on the agent endpoints: the design loop + chat are WRITE paths.

Both /agent/design and /agent/chat (and their streaming WS variants) execute tools through
the orchestrator and persist AgentRun/Molecule rows, so a read-only viewer must be refused
(403 on REST, a `read-only` error frame on the WS) exactly like /tools/{name}, /jobs, and the
credential/route writes. A writer (owner/editor) succeeds. These run under real nakitte JWTs
(`@pytest.mark.real_auth`) so the role from the token actually drives the gate.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from tests.conftest import make_token, tenant

_DESIGN_BODY = {
    "goal": "make 4 analogs with MW<300, no PAINS, drug-like",
    "seed_smiles": "c1ccccc1C(=O)O",
    "persist": True,
}
_CHAT_BODY = {
    "messages": [{"role": "user", "content": "make 4 analogs, MW<300, no PAINS, drug-like"}],
    "seed_smiles": "c1ccccc1C(=O)O",
    "persist": True,
}


def _drain_ws(ws) -> list[dict]:
    from fastapi import WebSocketDisconnect

    events: list[dict] = []
    try:
        while True:
            events.append(ws.receive_json())
    except WebSocketDisconnect:
        pass
    return events


# --- REST: POST /agent/design + /agent/chat ----------------------------------


@pytest.mark.real_auth
def test_viewer_cannot_run_design():
    with TestClient(app) as client:
        h = tenant(roles=("viewer",))["headers"]
        r = client.post("/agent/design", headers=h, json=_DESIGN_BODY)
        assert r.status_code == 403, r.text


@pytest.mark.real_auth
def test_viewer_cannot_run_chat():
    with TestClient(app) as client:
        h = tenant(roles=("viewer",))["headers"]
        r = client.post("/agent/chat", headers=h, json=_CHAT_BODY)
        assert r.status_code == 403, r.text


@pytest.mark.real_auth
def test_writer_can_run_design_and_chat():
    with TestClient(app) as client:
        h = tenant(roles=("owner",))["headers"]
        rd = client.post("/agent/design", headers=h, json=_DESIGN_BODY)
        assert rd.status_code == 200, rd.text
        assert rd.json()["run_id"]  # persist=True created the provenance hub

        rc = client.post("/agent/chat", headers=h, json=_CHAT_BODY)
        assert rc.status_code == 200, rc.text
        assert rc.json()["kind"] == "design"


# --- WS: /agent/design/stream + /agent/chat/stream ---------------------------


@pytest.mark.real_auth
def test_viewer_cannot_stream_design():
    token = make_token(roles=["viewer"])
    with TestClient(app) as client:
        with client.websocket_connect("/agent/design/stream") as ws:
            ws.send_json({**_DESIGN_BODY, "token": token})
            events = _drain_ws(ws)
    assert events == [{"type": "error", "error": "insufficient role (read-only)"}]


@pytest.mark.real_auth
def test_viewer_cannot_stream_chat():
    token = make_token(roles=["viewer"])
    with TestClient(app) as client:
        with client.websocket_connect("/agent/chat/stream") as ws:
            ws.send_json({**_CHAT_BODY, "token": token})
            events = _drain_ws(ws)
    assert events == [{"type": "error", "error": "insufficient role (read-only)"}]


@pytest.mark.real_auth
def test_writer_can_stream_design():
    token = make_token(roles=["owner"])
    with TestClient(app) as client:
        with client.websocket_connect("/agent/design/stream") as ws:
            ws.send_json({**_DESIGN_BODY, "token": token})
            events = _drain_ws(ws)
    types = [e["type"] for e in events]
    assert types[0] == "started" and types[-1] == "complete"
