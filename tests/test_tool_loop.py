"""The tool-calling agent — the model selects tools, we execute them, repeat.

This is the capability the product thesis promises ("a chemistry-aware agent plans and orchestrates
validated tools") and that the fixed design pipeline did NOT provide: it only ever touched four
tools. These tests prove the whole registry is now reachable from the agent and that a genuine
call -> observe -> answer loop runs offline via the deterministic mock.
"""
from fastapi.testclient import TestClient

from apps.api.main import app
from services.agent.tool_loop import ToolCallingAgent, registry_to_tool_schemas
from services.llm_gateway.types import CompletionRequest, CompletionResponse, ToolCall
from services.tools.catalog import build_default_registry
from services.tools.executor import ToolExecutionService

_SEED = "CC(=O)Nc1ccccc1"  # acetanilide — a real retrosynthetic disconnection


class _MessagesOnlyGateway:
    """A provider stub modelling the REAL BYO-LLM path: it reads ONLY ``req.messages`` (never
    ``req.metadata``, which only the offline mock consults). It scans the model-visible messages
    for a SMILES and, on the first turn, emits a tool call using it — exactly what a function-
    calling model does. If the SMILES never reached the messages, no tool call can be made.
    """

    def __init__(self, tool: str, arg: str = "canonical_smiles") -> None:
        self._tool, self._arg = tool, arg
        self.seen_messages: list[list[dict]] = []

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        self.seen_messages.append(req.messages)
        already_called = any(m.get("role") == "tool" for m in req.messages)
        smiles = _smiles_from_messages(req.messages)
        if not already_called and smiles and req.tools:
            return CompletionResponse(
                text="", model="stub/stub", provider="stub",
                tool_calls=[ToolCall(id="call_1", name=self._tool, arguments={self._arg: smiles})],
            )
        return CompletionResponse(text="done", model="stub/stub", provider="stub")


def _smiles_from_messages(messages: list[dict]) -> str | None:
    """Pull the seed SMILES out of the message content the model can actually see."""
    for m in messages:
        content = m.get("content") or ""
        if _SEED in content:
            return _SEED
    return None


def test_agent_exposes_every_registered_tool():
    reg = build_default_registry()
    schemas = registry_to_tool_schemas(reg)
    names = {t["function"]["name"] for t in schemas}
    # The four the old pipeline used PLUS the ones it could never reach from the agent.
    assert {
        "validate_molecule", "generate_analogs", "bioisosteric_replacement", "profile_molecule",
        "retrosynthesize", "dock", "predict_admet", "matched_pairs", "sar_transforms",
        "generate_conformers", "substructure_search", "bulk_similarity", "murcko_scaffold",
    } <= names
    assert len(schemas) == len(reg.list())
    # Every schema is a well-formed OpenAI/LiteLLM function tool.
    for t in schemas:
        assert t["type"] == "function"
        assert t["function"]["name"] and "parameters" in t["function"]


async def test_agent_selects_and_runs_a_previously_unreachable_tool():
    executor = ToolExecutionService(build_default_registry())
    agent = ToolCallingAgent(executor=executor)  # offline mock gateway

    result = await agent.run(
        "run a retrosynthesis to disconnect this molecule", seed_smiles=_SEED,
    )

    # The model selected retrosynthesize — a tool the fixed pipeline can never reach — and it ran.
    assert "retrosynthesize" in result.tools_used
    assert all(c.ok for c in result.trace)
    assert result.trace[0].arguments == {"canonical_smiles": _SEED}
    # The loop closed with a final prose answer rather than looping forever.
    assert result.text and result.steps == 1


async def test_seed_reaches_tool_args_via_messages_not_metadata():
    """Regression guard: the seed SMILES must ride in the *model-visible messages*, not only in
    metadata. Drive the loop with a gateway stub that reads ONLY messages (the real BYO-LLM path).
    If the seed leaks only through metadata, this stub can never form the tool call.
    """
    executor = ToolExecutionService(build_default_registry())
    gw = _MessagesOnlyGateway("retrosynthesize")
    agent = ToolCallingAgent(gateway=gw, executor=executor)

    result = await agent.run("disconnect this molecule", seed_smiles=_SEED)

    # The stub only ever saw the SMILES because run() embedded it into messages.
    assert any(_SEED in (m.get("content") or "") for m in gw.seen_messages[0])
    assert "retrosynthesize" in result.tools_used
    assert result.trace[0].arguments == {"canonical_smiles": _SEED}


async def test_context_molecule_smiles_reaches_messages():
    """An @-attached molecule (no explicit seed) must also become model-visible so a real
    provider can feed it to a tool."""
    executor = ToolExecutionService(build_default_registry())
    gw = _MessagesOnlyGateway("murcko_scaffold")
    agent = ToolCallingAgent(gateway=gw, executor=executor)

    await agent.run(
        "what is the scaffold?",
        seed_smiles=None,
        context_molecules=[{"name": "cpd-1", "smiles": _SEED}],
    )

    assert any(_SEED in (m.get("content") or "") for m in gw.seen_messages[0])


async def test_prior_history_is_threaded_into_messages():
    """Multi-turn history must reach the model, not just the last user string."""
    executor = ToolExecutionService(build_default_registry())
    gw = _MessagesOnlyGateway("retrosynthesize")
    agent = ToolCallingAgent(gateway=gw, executor=executor)

    history = [
        {"role": "user", "content": "earlier: I care about acetanilide"},
        {"role": "assistant", "content": "noted"},
        {"role": "user", "content": "now disconnect this molecule"},
    ]
    await agent.run("now disconnect this molecule", seed_smiles=_SEED, history=history)

    contents = [m.get("content") or "" for m in gw.seen_messages[0]]
    assert any("earlier: I care about acetanilide" in c for c in contents)
    assert any("now disconnect this molecule" in c for c in contents)


async def test_agent_answers_without_tools_when_none_apply():
    agent = ToolCallingAgent(executor=ToolExecutionService(build_default_registry()))
    result = await agent.run("what does QED measure?", seed_smiles=None)
    assert result.tools_used == []
    assert "offline" in result.text.lower()  # deterministic mock conversational reply


async def test_agent_survives_a_bad_tool_call_without_crashing():
    executor = ToolExecutionService(build_default_registry())
    agent = ToolCallingAgent(executor=executor)
    # ADMET is adapter-gated ("none" backend) — the tool exists but raises; the loop must record
    # the failure and still return an answer, never propagate the exception.
    result = await agent.run("predict ADMET properties for this", seed_smiles=_SEED)
    assert "predict_admet" in result.tools_used
    assert result.text


def test_conversational_chat_turn_can_now_reach_a_tool():
    """End-to-end through /agent/chat: a non-design request that names a tool actually runs it."""
    with TestClient(app) as client:
        r = client.post(
            "/agent/chat",
            json={
                "messages": [{"role": "user", "content": "run a retrosynthesis on this"}],
                "seed_smiles": _SEED,
                "persist": False,
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "chat"
    assert body["tools"] and any(t["tool"] == "retrosynthesize" for t in body["tools"])
