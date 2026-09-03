from __future__ import annotations

import json
import urllib.request
from typing import Sequence

from sim.core.ports.llm import LLMMessage


class OllamaClient:
    """LLMClient backed by a local Ollama server (free local dev).

    Requires `ollama serve` running and the model pulled
    (e.g. `ollama pull llama3.1`). Uses stdlib only — no extra dependency.
    """

    def __init__(
        self,
        model: str = "llama3.1",
        host: str = "http://localhost:11434",
        timeout: float = 120.0,
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._timeout = timeout

    def complete(self, *, system: str, messages: Sequence[LLMMessage]) -> str:
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
        }
        req = urllib.request.Request(
            f"{self._host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["message"]["content"]
