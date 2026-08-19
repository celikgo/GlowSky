"""Conversational Composer turns — the multi-turn layer over the one-shot design loop.

The design loop (`orchestrator.py`) answers a single goal+seed. The Composer wraps it in a
conversation: a chemist types intent in natural language, optionally `@`-attaches molecules
as context, and iterates ("now make them more polar", "drop the PAINS ones"). Each turn is
routed deterministically:

  * **design turn** — the message reads like a design/optimuse request *and* a seed is
    available (explicit, `@`-context, or carried from a prior turn). We run the full design
    loop and stream its milestones; the synthesis explanation becomes the assistant's reply.
  * **chat turn** — anything else. We answer conversationally through the LLM gateway, with
    the attached molecules summarised into the system prompt (offline mock stays deterministic).
  * **need-seed** — a design request with no molecule to start from. We ask for one instead of
    guessing.

This split is intentionally a cheap heuristic, not an LLM classifier: it keeps the offline mock
fully deterministic (so the whole Composer is testable with no API key) and leaves a clean seam
for a real tool-calling agent to replace `looks_like_design` later.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from services.agent.orchestrator import DesignOrchestrator
from services.agent.schemas import DesignRunResult
from services.agent.tool_loop import ToolCallingAgent
from services.llm_gateway.gateway import LLMGateway
from services.tools.context import ExecutionContext
from services.tools.executor import ToolExecutionService

# Cues that mark a message as a design/optimisation request. Lowercased substring match —
# deliberately broad on the "make analogs / change a property" intent the loop can actually serve.
_DESIGN_CUES: tuple[str, ...] = (
    "analog",
    "analogue",
    "generate",
    "design",
    "make ",
    "optimi",  # optimise / optimize / optimization
    "scaffold",
    "derivativ",
    "modify",
    "more polar",
    "less polar",
    "lower logp",
    "reduce logp",
    "raise logp",
    "increase",
    "decrease",
    "drug-like",
    "druglike",
    "no pains",
    "without pains",
    "fewer",
    "variant",
    "mw<",
    "mw <",
)

def looks_like_design(message: str) -> bool:
    """True when a message reads like a request to generate/optimise molecules."""
    m = message.lower()
    return any(cue in m for cue in _DESIGN_CUES)


def _last_user_message(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return (msg.get("content") or "").strip()
    return ""


@dataclass
class ChatTurnResult:
    """The outcome of one Composer turn, shaped for the API response + the next turn's state."""

    kind: str  # "design" | "chat" | "need_seed"
    text: str  # the assistant's reply (design synthesis, conversational answer, or the ask)
    seed: str | None  # the effective seed to carry into the next turn (None until one exists)
    design: DesignRunResult | None  # the full run when kind == "design", else None
    tools: list[dict] | None = None  # tool-call trace when a conversational turn used the agent


async def run_chat_turn(
    *,
    messages: list[dict],
    seed_smiles: str | None,
    context_molecules: list[dict] | None,
    gateway: LLMGateway,
    executor: ToolExecutionService,
    ctx: ExecutionContext | None = None,
    emit: Callable[[dict], Awaitable[None]] | None = None,
) -> ChatTurnResult:
    """Run one conversational turn. If ``emit`` is given, stream events as they happen
    (the design milestones for a design turn, then/or an ``assistant_message``); the assembled
    result is always returned for non-streaming callers."""
    context_molecules = context_molecules or []
    ctx = ctx or ExecutionContext()

    async def _emit(event: dict) -> None:
        if emit is not None:
            await emit(event)

    user = _last_user_message(messages)
    # Effective seed: an explicit one wins, else the first attached context molecule.
    seed = (seed_smiles or "").strip() or next(
        (m["smiles"] for m in context_molecules if m.get("smiles")), ""
    )

    if looks_like_design(user):
        if not seed:
            text = (
                "Which molecule should I start from? Attach one with @, draw it, or paste a "
                "SMILES, and I'll generate analogs toward your goal."
            )
            await _emit({"type": "assistant_message", "text": text})
            return ChatTurnResult(kind="need_seed", text=text, seed=None, design=None)

        orchestrator = DesignOrchestrator(gateway, executor)
        result = await orchestrator.run(user, seed, ctx, emit=emit)
        # The synthesis explanation is the assistant's reply for a design turn; the cards/plan
        # already streamed via the orchestrator's events.
        return ChatTurnResult(
            kind="design", text=result.explanation, seed=result.parent_smiles, design=result
        )

    # Conversational / tool-using turn — a real tool-calling agent over the FULL registry. A
    # request like "run a retrosynthesis on this", "profile ADMET", or "dock it" now reaches the
    # right tool (the model selects it), not just the four the design pipeline hard-codes. With no
    # tool needed it degrades to a plain conversational reply (offline mock stays deterministic).
    agent = ToolCallingAgent(gateway, executor)
    # A distinct name from the design branch's `result`: that one is a DesignRunResult,
    # this one an AgentResult, and they share no attributes.
    agent_result = await agent.run(
        user,
        ctx,
        seed_smiles=seed or None,
        has_context=bool(context_molecules),
        history=messages,
        context_molecules=context_molecules,
        emit=emit,
    )
    return ChatTurnResult(
        kind="chat",
        text=agent_result.text,
        seed=seed or None,
        design=None,
        tools=[c.as_dict() for c in agent_result.trace] or None,
    )
