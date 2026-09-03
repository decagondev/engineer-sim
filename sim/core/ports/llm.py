from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable


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
