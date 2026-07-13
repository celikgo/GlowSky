"""Provider implementations behind a common Protocol.

- LiteLLMProvider: unified access to Anthropic/OpenAI/Groq/local via LiteLLM.
- MockProvider: deterministic, offline. Lets the entire agent loop run and be
  tested with zero API keys. It does NOT do chemistry — it only mimics the LLM's
  planning/synthesis role by reading structured hints from request.metadata.
"""
from __future__ import annotations

import json
import re
from typing import Protocol

from services.llm_gateway.keys import KeyStore
from services.llm_gateway.types import (
    CompletionRequest,
    CompletionResponse,
    ModelRoute,
    ToolCall,
)


class Provider(Protocol):
    async def complete(self, req: CompletionRequest, route: ModelRoute) -> CompletionResponse: ...


class LiteLLMProvider:
    """Real provider. Resolves the key at call time; never logs it."""

    def __init__(self, keys: KeyStore) -> None:
        self._keys = keys

    async def complete(self, req: CompletionRequest, route: ModelRoute) -> CompletionResponse:
        import litellm  # imported lazily so offline/mock runs need no provider stack

        # LiteLLM uses "<provider>/<model>" for most providers; "local" maps to an
        # OpenAI-compatible base_url.
        kwargs: dict = {
            "messages": req.messages,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        }
        # Function-calling: hand the tool schemas to the model so IT selects tools. LiteLLM
        # normalises this across Anthropic/OpenAI/Groq/local, so the agent loop is provider-agnostic.
        if req.tools:
            kwargs["tools"] = req.tools
            kwargs["tool_choice"] = req.tool_choice
        if route.provider == "local":
            kwargs["model"] = f"openai/{route.model}"
            kwargs["api_base"] = self._keys.base_url("local")
            kwargs["api_key"] = self._keys.api_key("local") or "not-needed"
        else:
            kwargs["model"] = f"{route.provider}/{route.model}"
            kwargs["api_key"] = self._keys.api_key(route.provider)

        resp = await litellm.acompletion(**kwargs)
        message = resp["choices"][0]["message"]
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        choice = content or ""
        usage = dict(resp.get("usage", {}) or {})
        return CompletionResponse(
            text=choice, model=f"{route.provider}/{route.model}",
            provider=route.provider, usage=usage,
            tool_calls=self._parse_tool_calls(message),
        )

    @staticmethod
    def _parse_tool_calls(message) -> list[ToolCall]:
        raw = message.get("tool_calls") if isinstance(message, dict) else getattr(message, "tool_calls", None)
        if not raw:
            return []
        calls: list[ToolCall] = []
        for tc in raw:
            fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
            name = (fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", None)) or ""
            raw_args = (fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", None)) or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except (json.JSONDecodeError, TypeError, ValueError):
                args = {}
            call_id = (tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)) or f"call_{name}"
            if name:
                calls.append(ToolCall(id=call_id, name=name, arguments=args))
        return calls


class MockProvider:
    """Offline stand-in. Behaviour is selected by request.metadata['mock_intent']."""

    # Cue -> tool the mock will pick when that word appears in an agent turn's goal. Deterministic
    # stand-in for what a real function-calling model does; lets the tool-calling loop (and every
    # otherwise-unreachable tool it can now select) be exercised offline with zero API keys.
    _AGENT_TOOL_CUES: tuple[tuple[str, str], ...] = (
        ("retro", "retrosynthesize"),
        ("disconnect", "retrosynthesize"),
        ("synthesi", "synthesizability"),
        ("admet", "predict_admet"),
        ("conformer", "generate_conformers"),
        ("3d", "generate_conformers"),
        ("descriptor", "compute_descriptors"),
        ("murcko", "murcko_scaffold"),
        ("fingerprint", "fingerprint"),
        ("alert", "structural_alerts"),
        ("pains", "structural_alerts"),
        ("medchem", "medchem_rules"),
        ("rule", "medchem_rules"),
        ("sa score", "sa_score"),
        ("accessib", "sa_score"),
        ("dock", "dock"),
        ("substructure", "substructure_search"),
    )

    async def complete(self, req: CompletionRequest, route: ModelRoute) -> CompletionResponse:
        intent = req.metadata.get("mock_intent", "echo")
        if intent == "agent":
            return self._agent_step(req)
        if intent == "design_plan":
            text = json.dumps(self._design_plan(req.metadata.get("goal", "")))
        elif intent == "synthesize":
            text = self._synthesize(req.metadata)
        elif intent == "chat":
            text = self._chat(req.metadata)
        else:
            text = req.messages[-1]["content"] if req.messages else ""
        return CompletionResponse(
            text=text, model="mock/mock", provider="mock",
            usage={"prompt_tokens": 0, "completion_tokens": 0},
        )

    def _agent_step(self, req: CompletionRequest) -> CompletionResponse:
        """One deterministic step of the offline tool-calling loop.

        Turn 1: if the goal names a capability we can serve and a seed molecule is available,
        emit a tool call for it (exactly what a real model does via function-calling). Later turns
        (tool results already gathered) return a final text answer. With no tool cue it degrades to
        the same offline conversational reply as the plain chat mock — so non-tool turns are a no-op.
        """
        meta = req.metadata
        tools_used = meta.get("tools_used", [])
        schemas = {
            t["function"]["name"]: t["function"].get("parameters", {})
            for t in req.tools if "function" in t
        }
        seed = meta.get("seed_smiles")
        if not tools_used and seed:
            selection = self._select_agent_tool(meta.get("user", ""), schemas)
            if selection is not None:
                name, schema = selection
                call = ToolCall(id="call_1", name=name, arguments=self._fill_args(schema, seed))
                return CompletionResponse(
                    text="", model="mock/mock", provider="mock",
                    usage={"prompt_tokens": 0, "completion_tokens": 0}, tool_calls=[call],
                )
        text = self._agent_summary(tools_used) if tools_used else self._chat(meta)
        return CompletionResponse(
            text=text, model="mock/mock", provider="mock",
            usage={"prompt_tokens": 0, "completion_tokens": 0},
        )

    @classmethod
    def _select_agent_tool(cls, goal: str, schemas: dict[str, dict]) -> tuple[str, dict] | None:
        g = goal.lower()
        for cue, tool in cls._AGENT_TOOL_CUES:
            if cue in g and tool in schemas:
                return tool, schemas[tool]
        return None

    @staticmethod
    def _fill_args(schema: dict, seed: str) -> dict:
        """Fill a tool's required params from a single seed SMILES (mock's best effort)."""
        props = schema.get("properties", {})
        required = schema.get("required", []) or list(props)
        args: dict = {}
        for key in required:
            spec = props.get(key, {})
            if spec.get("type") == "array":
                args[key] = [seed]
            elif "smarts" in key:
                args[key] = "c1ccccc1"
            else:
                args[key] = seed
        return args

    @staticmethod
    def _agent_summary(tools_used: list[str]) -> str:
        used = ", ".join(dict.fromkeys(tools_used)) or "no tools"
        return (
            f"Ran the requested chemistry tools ({used}) and summarised the results. "
            "[offline mock — connect a provider for a model-authored synthesis]"
        )

    @staticmethod
    def _design_plan(goal: str) -> dict:
        """Heuristically extract a structured design plan from the NL goal."""
        g = goal.lower()
        count = 20
        m = re.search(r"(\d+)\s*(analog|analogue|molecule|compound)", g)
        if m:
            count = min(int(m.group(1)), 50)

        constraints: dict = {}
        mw = re.search(r"mw\s*[<≤]\s*(\d+)", g)
        if mw:
            constraints["mw_max"] = float(mw.group(1))
        logp = re.search(r"logp\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*[-–to]+\s*(\d+(?:\.\d+)?)", g)
        if logp:
            constraints["logp_min"] = float(logp.group(1))
            constraints["logp_max"] = float(logp.group(2))
        elif "lower logp" in g or "reduce logp" in g:
            constraints["logp_max"] = 3.0
        if "pains" in g or "alert" in g:
            constraints["exclude_pains"] = True
        if "lipinski" in g or "drug-like" in g or "druglike" in g:
            constraints["require_lipinski"] = True

        return {
            "max_analogs": count,
            "constraints": constraints,
            "rationale": "Heuristic plan from goal (offline mock). A real model would "
            "reason about the target profile and propose richer constraints.",
        }

    @staticmethod
    def _chat(meta: dict) -> str:
        """A deterministic, honest stand-in for a conversational reply (offline mock)."""
        ctx = " I can see the molecule you attached." if meta.get("has_context") else ""
        return (
            "I'm running offline (no LLM connected), so I can't reason about chemistry in free "
            f"text.{ctx} I can still run the deterministic design loop: ask me to 'make N analogs' "
            "with constraints like 'MW<300, logP 1-3, no PAINS' and a seed molecule. "
            "[connect a provider in Settings for conversational answers]"
        )

    @staticmethod
    def _synthesize(meta: dict) -> str:
        n = meta.get("n_candidates", 0)
        kept = meta.get("n_kept", n)
        top = meta.get("top", [])
        lines = [
            f"Generated {n} validated analogs; {kept} passed the requested filters.",
        ]
        if top:
            lines.append("Top candidates by MPO desirability:")
            for c in top[:3]:
                p = c.get("properties", {})
                mpo = f", MPO {p.get('mpo')}" if p.get("mpo") is not None else ""
                lines.append(
                    f"  • {c.get('modification', '?')} — {c['smiles']} "
                    f"(MW {p.get('mw')}, logP {p.get('logp')}, QED {p.get('qed')}{mpo})"
                )
        lines.append(
            "[offline mock synthesis — connect a provider for real chemical reasoning]"
        )
        return "\n".join(lines)
