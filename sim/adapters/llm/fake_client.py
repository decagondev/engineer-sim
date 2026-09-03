from __future__ import annotations

from typing import Sequence

from sim.core.ports.llm import LLMMessage


class FakeLLMClient:
    """Deterministic LLM stand-in for smoke/regression tests and local demos.

    Satisfies the LLMClient port structurally. Returns scripted replies in
    order, then falls back to `default`. Records every call for assertions.
    This is the seam that lets us test an LLM-driven system deterministically.
    """

    def __init__(
        self,
        responses: Sequence[str] | None = None,
        default: str = "Sure — tell me a bit more about what you're after.",
    ) -> None:
        self._responses = list(responses or [])
        self._default = default
        self.calls: list[dict] = []

    def complete(self, *, system: str, messages: Sequence[LLMMessage]) -> str:
        self.calls.append({"system": system, "messages": list(messages)})
        if self._responses:
            return self._responses.pop(0)
        return self._default
