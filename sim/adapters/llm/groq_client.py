from __future__ import annotations

from typing import Sequence

from sim.core.ports.llm import LLMMessage


class GroqClient:
    """LLMClient backed by the Groq API — fast, low-cost inference for open
    models (Llama, Mixtral, Gemma, ...). OpenAI-compatible chat completions.

    The SDK is imported lazily so the rest of the app runs without it installed.
    Set GROQ_API_KEY in the environment (get one at https://console.groq.com/keys).
    NOTE: model IDs change over time — set GROQ_MODEL; if the default 404s, pick a
    current one from https://console.groq.com/docs/models.
    """

    def __init__(self, model: str = "llama-3.3-70b-versatile",
                 max_tokens: int = 1024) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from groq import Groq  # lazy import
            self._client = Groq()   # reads GROQ_API_KEY from the environment
        return self._client

    def complete(self, *, system: str, messages: Sequence[LLMMessage]) -> str:
        client = self._ensure_client()
        resp = client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
        )
        return resp.choices[0].message.content or ""
