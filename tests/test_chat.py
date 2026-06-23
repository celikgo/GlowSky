"""The conversational Composer turn (`/agent/chat` + `/agent/chat/stream`).

Covers the multi-turn layer over the design loop: design vs. conversational routing, `@`-context
seed resolution, incremental constraints from natural language, the need-a-seed ask, and the
streaming protocol the Composer UI subscribes to. Deterministic via the offline mock — no key.
"""
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from apps.api.main import app
from services.agent.chat import looks_like_design


def _drain(ws) -> list[dict]:
    events: list[dict] = []
    try:
        while True:
            events.append(ws.receive_json())
    except WebSocketDisconnect:
        pass
    return events


# --- the design/chat split (pure unit) ---------------------------------------


def test_looks_like_design_splits_intent():
    assert looks_like_design("make 8 analogs with MW<300")
    assert looks_like_design("now lower logP and drop the PAINS ones")
    assert looks_like_design("optimise this scaffold")
    assert not looks_like_design("what does QED measure?")
    assert not looks_like_design("hello, who are you?")


# --- POST /agent/chat --------------------------------------------------------


def test_chat_design_turn_runs_the_loop():
    with TestClient(app) as client:
        r = client.post(
            "/agent/chat",
            json={
                "messages": [{"role": "user", "content": "make 8 analogs, MW<300, no PAINS, drug-like"}],
                "seed_smiles": "c1ccccc1C(=O)O",
                "persist": False,
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "design"
    assert body["design"] is not None
    # The NL constraints reached the plan (mock goal parser).
    c = body["design"]["plan"]["constraints"]
    assert c["mw_max"] == 300.0 and c["exclude_pains"] and c["require_lipinski"]
    assert len(body["design"]["candidates"]) > 0
    # The effective seed is carried forward (canonicalised) for the next turn.
    assert body["seed"]


def test_chat_uses_at_context_molecule_as_seed():
    """A design request with no explicit seed falls back to the first @-attached molecule."""
    with TestClient(app) as client:
        r = client.post(
            "/agent/chat",
            json={
                "messages": [{"role": "user", "content": "make 6 analogs"}],
                "context_molecules": [{"smiles": "c1ccccc1C(=O)O", "name": "benzoic acid"}],
                "persist": False,
            },
        )
    body = r.json()
    assert body["kind"] == "design"
    assert body["design"] is not None
    assert body["seed"]  # resolved from the attached molecule


def test_chat_incremental_constraints_from_language():
    """A follow-up phrased as 'lower logP, no PAINS' lands as structured constraints."""
    with TestClient(app) as client:
        r = client.post(
            "/agent/chat",
            json={
                "messages": [{"role": "user", "content": "make 8 analogs, lower logP, no PAINS"}],
                "seed_smiles": "c1ccccc1C(=O)O",
                "persist": False,
            },
        )
    c = r.json()["design"]["plan"]["constraints"]
    assert c["logp_max"] == 3.0 and c["exclude_pains"]


def test_chat_conversational_turn_does_not_design():
    with TestClient(app) as client:
        r = client.post(
            "/agent/chat",
            json={"messages": [{"role": "user", "content": "what does QED measure?"}]},
        )
    body = r.json()
    assert body["kind"] == "chat"
    assert body["design"] is None
    assert "offline" in body["text"].lower()  # the deterministic mock reply


def test_chat_design_without_seed_asks_for_one():
    with TestClient(app) as client:
        r = client.post(
            "/agent/chat",
            json={"messages": [{"role": "user", "content": "make 10 analogs"}]},
        )
    body = r.json()
    assert body["kind"] == "need_seed"
    assert body["design"] is None
    assert body["seed"] is None


# --- WS /agent/chat/stream ---------------------------------------------------


def test_chat_stream_design_turn_relays_milestones():
    with TestClient(app) as client:
        with client.websocket_connect("/agent/chat/stream") as ws:
            ws.send_json({
                "messages": [{"role": "user", "content": "make 8 analogs, MW<300, no PAINS"}],
                "seed_smiles": "c1ccccc1C(=O)O",
                "persist": True,
            })
            events = _drain(ws)

    types = [e["type"] for e in events]
    assert types[0] == "started"
    assert "plan" in types and "candidate" in types and "ranked" in types
    assert types[-1] == "complete"
    final = events[-1]
    assert final["kind"] == "design"
    assert final["design"]["run_id"]  # persisted
    assert final["seed"]


def test_chat_stream_conversational_turn_sends_assistant_message():
    with TestClient(app) as client:
        with client.websocket_connect("/agent/chat/stream") as ws:
            ws.send_json({
                "messages": [{"role": "user", "content": "hello, what can you help with?"}],
            })
            events = _drain(ws)

    types = [e["type"] for e in events]
    assert "assistant_message" in types
    assert types[-1] == "complete"
    assert events[-1]["kind"] == "chat"
    assert events[-1]["design"] is None
