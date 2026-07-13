"""A real tool-calling agent loop — the model plans and *selects* tools; we execute them.

Where `orchestrator.py` runs a fixed 6-step pipeline that only ever touches four tools, this loop
exposes the *entire* registry to the model and lets it choose: on each turn the model may request
one or more tool calls, we run them through the ToolExecutionService (cache, firewall, provenance —
docs/13), feed the results back, and repeat until it answers in prose or the step cap is hit.

With a real provider LiteLLM function-calling drives the selection for every routed model; offline,
the MockProvider selects deterministically so the whole loop is testable with zero API keys. Either
way, docking, retrosynthesis, ADMET, matched-pairs, scaffolds, similarity, conformers and every
registered container tool are now reachable from the agent — not just the four the pipeline hard-codes.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from services.llm_gateway.gateway import LLMGateway
from services.llm_gateway.types import CompletionRequest, TaskClass, ToolCall
from services.tools.context import ExecutionContext
from services.tools.executor import ToolExecutionError, ToolExecutionService
from services.tools.registry import ToolRegistry

_AGENT_SYSTEM = (
    "You are Glowsky, a chemistry-aware design agent. You plan and orchestrate validated "
    "deterministic chemistry tools to serve the user's intent; the tools compute, you reason and "
    "explain. Select tools when they help answer the request, then summarise the results for a "
    "medicinal chemist. Never invent chemical values — always obtain them from a tool. When you "
    "have enough to answer, reply in prose without further tool calls."
)


@dataclass
class AgentToolCall:
    """One executed tool call in the agent's trace (provenance-friendly, JSON-able)."""

    step: int
    tool: str
    arguments: dict
    ok: bool
    summary: str
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "step": self.step, "tool": self.tool, "arguments": self.arguments,
            "ok": self.ok, "summary": self.summary, "error": self.error,
        }


@dataclass
class AgentResult:
    """The outcome of an agent run: the final prose answer plus the tool-call trace."""

    text: str
    trace: list[AgentToolCall] = field(default_factory=list)
    steps: int = 0

    @property
    def tools_used(self) -> list[str]:
        return [c.tool for c in self.trace]


def registry_to_tool_schemas(registry: ToolRegistry) -> list[dict]:
    """Every registered tool as an OpenAI/LiteLLM function-tool schema (name+description+params)."""
    out: list[dict] = []
    for spec in registry.list():
        d = spec.discovery_dict()
        out.append({
            "type": "function",
            "function": {
                "name": d["name"],
                "description": d["description"],
                "parameters": d.get("parameters") or {"type": "object", "properties": {}},
            },
        })
    return out


class ToolCallingAgent:
    """Drives a genuine plan -> call -> observe -> repeat loop over the whole tool registry."""

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        executor: ToolExecutionService | None = None,
        *,
        max_steps: int = 6,
    ) -> None:
        self._gw = gateway or LLMGateway()
        if executor is None:
            from services.tools.catalog import build_default_registry

            executor = ToolExecutionService(build_default_registry())
        self._exec = executor
        self._max_steps = max(1, max_steps)

    async def run(
        self,
        user_message: str,
        ctx: ExecutionContext | None = None,
        *,
        seed_smiles: str | None = None,
        has_context: bool = False,
        history: list[dict] | None = None,
        context_molecules: list[dict] | None = None,
        emit: Callable[[dict], Awaitable[None]] | None = None,
    ) -> AgentResult:
        ctx = ctx or ExecutionContext()
        tools = registry_to_tool_schemas(self._exec.registry)

        async def _emit(event: dict) -> None:
            if emit is not None:
                await emit(event)

        # Build the *model-visible* conversation. A real provider (LiteLLM) only ever sees
        # ``messages`` + ``tools`` — the seed/context molecules and prior turns that used to live
        # ONLY in ``metadata`` never reached it, so every chemistry tool (all of which need a
        # canonical_smiles) was starved of its input off the mock. Embed them into messages.
        messages: list[dict] = [{"role": "system", "content": _AGENT_SYSTEM}]
        context_note = _context_note(seed_smiles, context_molecules)
        if context_note:
            messages.append({"role": "system", "content": context_note})
        messages.extend(_conversation_messages(history, user_message))
        trace: list[AgentToolCall] = []

        for _ in range(self._max_steps):
            req = CompletionRequest(
                messages=messages,
                task_class=TaskClass.REASONING,
                tools=tools,
                tool_choice="auto",
                metadata={
                    "mock_intent": "agent",
                    "user": user_message,
                    "seed_smiles": seed_smiles,
                    "has_context": has_context,
                    "tools_used": [c.tool for c in trace],
                },
            )
            resp = await self._gw.complete(req)

            if not resp.tool_calls:
                await _emit({"type": "assistant_message", "text": resp.text})
                return AgentResult(text=resp.text, trace=trace, steps=len(trace))

            messages.append(_assistant_tool_message(resp.text, resp.tool_calls))
            for call in resp.tool_calls:
                executed, output = self._execute(call, ctx, step=len(trace) + 1)
                trace.append(executed)
                await _emit({"type": "tool_call", "record": executed.as_dict()})
                content = (
                    json.dumps(output, default=str)[:8000] if executed.ok else executed.summary
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": content,
                })

        # Step cap reached with tools still pending — ask for a final synthesis, no more tools.
        final = await self._gw.complete(CompletionRequest(
            messages=messages, task_class=TaskClass.FAST_TRIAGE, tool_choice="none",
            metadata={"mock_intent": "agent", "user": user_message,
                      "seed_smiles": seed_smiles, "has_context": has_context,
                      "tools_used": [c.tool for c in trace]},
        ))
        await _emit({"type": "assistant_message", "text": final.text})
        return AgentResult(text=final.text, trace=trace, steps=len(trace))

    def _execute(
        self, call: ToolCall, ctx: ExecutionContext, *, step: int
    ) -> tuple[AgentToolCall, object]:
        try:
            result = self._exec.execute(call.name, call.arguments, ctx)
        except KeyError:
            return (AgentToolCall(step=step, tool=call.name, arguments=call.arguments,
                                  ok=False, summary=f"unknown tool {call.name!r}",
                                  error="unknown_tool"), None)
        except ToolExecutionError as exc:
            return (AgentToolCall(step=step, tool=call.name, arguments=call.arguments,
                                  ok=False, summary=str(exc), error=str(exc)), None)
        except Exception as exc:  # a bad-arg call must not kill the loop
            return (AgentToolCall(step=step, tool=call.name, arguments=call.arguments,
                                  ok=False, summary=f"{call.name} failed: {exc}",
                                  error=str(exc)), None)
        return (AgentToolCall(
            step=step, tool=call.name, arguments=call.arguments, ok=True,
            summary=_summarise(call.name, result.output),
        ), result.output)


def _context_note(seed_smiles: str | None, context_molecules: list[dict] | None) -> str:
    """A model-visible note carrying the seed + attached-molecule SMILES.

    Chemistry tools all require a ``canonical_smiles`` (or list of them); with a real provider the
    only channel the model reads is ``messages``, so the seed/context must be spelled out here — not
    left in ``metadata`` (which only the offline mock consults).
    """
    lines: list[str] = []
    if seed_smiles:
        lines.append(f"Context molecule (SMILES): {seed_smiles}")
    for m in context_molecules or []:
        smi = (m.get("smiles") or "").strip()
        if not smi or smi == seed_smiles:
            continue
        name = (m.get("name") or "").strip()
        lines.append(f"Attached molecule ({name}, SMILES): {smi}" if name
                     else f"Attached molecule (SMILES): {smi}")
    if not lines:
        return ""
    return (
        "The user is working with the following molecule(s). When a chemistry tool needs a "
        "SMILES/structure, use one of these unless the user gives another:\n" + "\n".join(lines)
    )


def _conversation_messages(history: list[dict] | None, fallback_user: str) -> list[dict]:
    """Prior user/assistant turns as model-visible messages, else the single current user turn.

    Threads multi-turn history (previously dropped — only the last user string was forwarded) so a
    real provider sees the whole conversation. Only user/assistant text is kept; system prompts and
    tool scaffolding are re-synthesised by the agent, not replayed from the client.
    """
    convo = [
        {"role": m["role"], "content": (m.get("content") or "").strip()}
        for m in (history or [])
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
    ]
    return convo or [{"role": "user", "content": fallback_user}]


def _assistant_tool_message(text: str, calls: list[ToolCall]) -> dict:
    return {
        "role": "assistant",
        "content": text or None,
        "tool_calls": [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
            }
            for c in calls
        ],
    }


def _summarise(tool: str, output: object) -> str:
    if isinstance(output, dict):
        keys = ", ".join(list(output)[:6])
        return f"{tool}: {{{keys}}}"
    if isinstance(output, list):
        return f"{tool}: {len(output)} result(s)"
    return f"{tool}: {str(output)[:120]}"
