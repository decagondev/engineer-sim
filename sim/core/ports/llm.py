from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class LLMMessage:
    """A single turn handed to an LLM. `role` is 'user' or 'assistant'."""

    role: str
    content: str


@runtime_checkable
class LLMClient(Protocol):
    """Port: turns a system prompt + history into a reply.

    Fake / Ollama / Anthropic implementations are fully substitutable (LSP).
    The core depends ONLY on this abstraction (DIP) — never on an SDK.
    """

    def complete(self, *, system: str, messages: Sequence[LLMMessage]) -> str:
        ...


DeltaSink = Callable[[str], None]


@runtime_checkable
class StreamingLLMClient(Protocol):
    """Optional extension: the same reply, delivered as it is generated.
    `on_delta` receives each new fragment; the full text is still returned so
    callers that store the reply do not change."""

    def stream(self, *, system: str, messages: Sequence[LLMMessage],
               on_delta: DeltaSink) -> str:
        ...


def complete_with_deltas(llm: LLMClient, *, system: str, messages: Sequence[LLMMessage],
                         on_delta: Optional[DeltaSink] = None) -> str:
    """Use `stream` when the client has it and a sink was given; otherwise a
    plain completion, handed to the sink in one piece so the caller sees the
    same shape either way."""
    if on_delta is None:
        return llm.complete(system=system, messages=messages)
    stream = getattr(llm, "stream", None)
    if callable(stream):
        return stream(system=system, messages=messages, on_delta=on_delta)
    text = llm.complete(system=system, messages=messages)
    if text:
        on_delta(text)
    return text
