from __future__ import annotations

import os
from typing import Sequence

import httpx

from sim.core.ports.llm import LLMMessage

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqClient:
    """LLMClient backed by Groq's OpenAI-compatible chat API.

    Uses httpx (already a project dependency) so LLM_PROVIDER=groq works
    without the optional `groq` SDK. Set GROQ_API_KEY (https://console.groq.com/keys).
    Model IDs change — override with GROQ_MODEL; see
    https://console.groq.com/docs/models.
    """

    def __init__(self, model: str = "llama-3.3-70b-versatile",
                 max_tokens: int = 1024, timeout: float = 60.0,
                 api_key: str | None = None) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._api_key = api_key

    def _key(self) -> str:
        key = self._api_key if self._api_key is not None else os.environ.get("GROQ_API_KEY", "")
        if not str(key).strip():
            raise RuntimeError(
                "No Groq API key available. Add yours in Settings "
                "(https://console.groq.com/keys) or set GROQ_API_KEY on the server."
            )
        return str(key)

    def complete(self, *, system: str, messages: Sequence[LLMMessage]) -> str:
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
        }
        try:
            resp = httpx.post(
                _GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {self._key()}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Groq request failed: {exc}") from exc
        if resp.status_code != 200:
            raise RuntimeError(_groq_http_error(resp, self._model, byok=bool(self._api_key)))
        body = resp.json()
        choices = body.get("choices") or [{}]
        return (choices[0].get("message") or {}).get("content") or ""


def validate_groq_key(api_key: str) -> None:
    """One cheap authenticated call so a bad key fails in Settings, not mid-chat."""
    key = (api_key or "").strip()
    if not key:
        raise RuntimeError("Paste a Groq API key.")
    try:
        resp = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not reach Groq: {exc}") from exc
    if resp.status_code in (401, 403):
        raise RuntimeError("Groq rejected that key. Copy a new one from console.groq.com/keys.")
    if resp.status_code != 200:
        raise RuntimeError(f"Groq returned {resp.status_code} while checking the key.")


def _groq_http_error(resp: httpx.Response, model: str, *, byok: bool = False) -> str:
    detail = resp.text[:400]
    try:
        err = (resp.json().get("error") or {})
        if isinstance(err, dict) and err.get("message"):
            detail = err["message"]
    except Exception:
        pass
    if resp.status_code in (401, 403) and byok:
        return ("Your Groq API key was rejected. Open Settings and paste a valid "
                "key from console.groq.com/keys.")
    if resp.status_code == 429:
        return ("Your Groq key is rate-limited. Wait a minute or check your "
                "quota at console.groq.com.")
    hint = ""
    if resp.status_code in (400, 404):
        hint = (
            f" If the model id is stale, set GROQ_MODEL to a current one from "
            f"https://console.groq.com/docs/models (tried {model!r})."
        )
    return f"Groq returned {resp.status_code}: {detail}.{hint}"
