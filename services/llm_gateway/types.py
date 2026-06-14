from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskClass(str, Enum):
    """What kind of work an LLM call is doing. Drives model routing."""

    REASONING = "reasoning"      # deep planning / synthesis
    FAST_TRIAGE = "fast_triage"  # cheap, high-volume classification
    CODEGEN = "codegen"          # notebook / code generation


@dataclass(frozen=True)
class ModelRoute:
    provider: str  # anthropic | openai | groq | local | mock
    model: str
    task_class: TaskClass


@dataclass
class CompletionRequest:
    messages: list[dict]                 # [{"role": "user"|"system"|"assistant", "content": str}]
    task_class: TaskClass = TaskClass.REASONING
    temperature: float = 0.2
    max_tokens: int = 1024
    # Hints used ONLY by the offline mock provider to pick a canned behaviour.
    metadata: dict = field(default_factory=dict)


@dataclass
class CompletionResponse:
    text: str
    model: str        # "provider/model" actually used
    provider: str
    usage: dict = field(default_factory=dict)  # token counts when the provider reports them
