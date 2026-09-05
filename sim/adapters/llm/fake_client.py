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
        if "JSON object of the form" in (system or "") and '"scores"' in (system or ""):
            return (
                '{"scores":['
                '{"key":"discovery","score":0.7,"evidence":"asked clarifying questions"},'
                '{"key":"scoping","score":0.7,"evidence":"wrote a design document"},'
                '{"key":"stakeholders","score":0.6,"evidence":"covered system-design basics"},'
                '{"key":"communication","score":0.6,"evidence":"defended decisions"},'
                '{"key":"tickets","score":0.5,"evidence":"tickets present"}'
                '],"summary":"Directional fake grade."}'
            )
        if "mermaid" in (system or "").lower() or "flowchart" in (system or "").lower():
            return "```mermaid\nflowchart TB\n  Client --> Service\n  Service --> Store\n```"
        return self._default
