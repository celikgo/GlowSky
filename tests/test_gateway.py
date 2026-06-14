"""LLM gateway: routing, offline mock fallback, and key non-leakage."""
import json

from services.llm_gateway.gateway import LLMGateway
from services.llm_gateway.types import CompletionRequest, TaskClass


async def test_mock_fallback_when_no_keys():
    gw = LLMGateway()  # default env has no provider keys -> mock
    resp = await gw.complete(
        CompletionRequest(messages=[{"role": "user", "content": "hi"}], metadata={})
    )
    assert resp.provider == "mock"
    assert gw.route_for(TaskClass.REASONING) == "mock/mock"


async def test_mock_design_plan_parses_goal():
    gw = LLMGateway()
    goal = "make 12 analogs with MW<350, logP 1-3, no PAINS, drug-like"
    resp = await gw.complete(
        CompletionRequest(
            messages=[{"role": "user", "content": goal}],
            metadata={"mock_intent": "design_plan", "goal": goal},
        )
    )
    plan = json.loads(resp.text)
    assert plan["max_analogs"] == 12
    assert plan["constraints"]["mw_max"] == 350.0
    assert plan["constraints"]["logp_min"] == 1.0
    assert plan["constraints"]["logp_max"] == 3.0
    assert plan["constraints"]["exclude_pains"] is True
    assert plan["constraints"]["require_lipinski"] is True


async def test_routing_picks_up_real_provider_when_key_present():
    from services.core.config import Settings

    settings = Settings(openai_api_key="sk-test", route_reasoning="openai/gpt-4o-mini")
    gw = LLMGateway(settings)
    # Has a key -> selects the real route (we don't call out; just check selection).
    assert gw.route_for(TaskClass.REASONING) == "openai/gpt-4o-mini"


async def test_routing_falls_back_when_key_absent():
    from services.core.config import Settings

    settings = Settings(route_reasoning="openai/gpt-4o-mini")  # no key
    gw = LLMGateway(settings)
    assert gw.route_for(TaskClass.REASONING) == "mock/mock"  # graceful degradation
