from __future__ import annotations

from typing import Sequence

from sim.core.ports.llm import LLMMessage


class AnthropicClient:
    """LLMClient backed by the Anthropic API (quality passes / real sessions).

    The SDK is imported lazily so the rest of the app runs without it installed.
    Set ANTHROPIC_API_KEY in the environment. NOTE: model strings change over
    time — set ANTHROPIC_MODEL to a current one (see docs.claude.com).
    """

    def __init__(self, model: str = "claude-sonnet-4-5", max_tokens: int = 1024) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import anthropic  # lazy import
            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, *, system: str, messages: Sequence[LLMMessage]) -> str:
        client = self._ensure_client()
        resp = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
