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
from services.llm_gateway.types import CompletionRequest, CompletionResponse, ModelRoute


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
        if route.provider == "local":
            kwargs["model"] = f"openai/{route.model}"
            kwargs["api_base"] = self._keys.base_url("local")
            kwargs["api_key"] = self._keys.api_key("local") or "not-needed"
        else:
            kwargs["model"] = f"{route.provider}/{route.model}"
            kwargs["api_key"] = self._keys.api_key(route.provider)

        resp = await litellm.acompletion(**kwargs)
        choice = resp["choices"][0]["message"]["content"] or ""
        usage = dict(resp.get("usage", {}) or {})
        return CompletionResponse(
            text=choice, model=f"{route.provider}/{route.model}",
            provider=route.provider, usage=usage,
        )


class MockProvider:
    """Offline stand-in. Behaviour is selected by request.metadata['mock_intent']."""

    async def complete(self, req: CompletionRequest, route: ModelRoute) -> CompletionResponse:
        intent = req.metadata.get("mock_intent", "echo")
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
            lines.append("Top candidates by QED:")
            for c in top[:3]:
                p = c.get("properties", {})
                lines.append(
                    f"  • {c.get('modification', '?')} — {c['smiles']} "
                    f"(MW {p.get('mw')}, logP {p.get('logp')}, QED {p.get('qed')})"
                )
        lines.append(
            "[offline mock synthesis — connect a provider for real chemical reasoning]"
        )
        return "\n".join(lines)
