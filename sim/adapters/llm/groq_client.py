from __future__ import annotations

import json
import os
from typing import Callable, Optional, Sequence

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

    def __init__(self, model: str = "openai/gpt-oss-120b",
                 max_tokens: int = 1024, timeout: float = 60.0,
                 api_key: str | None = None,
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._api_key = api_key
        self._transport = transport          # tests inject httpx.MockTransport

    def _payload(self, system: str, messages: Sequence[LLMMessage]) -> dict:
        return {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
        }

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key()}", "Content-Type": "application/json"}

    def stream(self, *, system: str, messages: Sequence[LLMMessage],
               on_delta: Callable[[str], None]) -> str:
        """Same reply as `complete`, delivered fragment by fragment over Groq's
        server-sent events; the full text is returned at the end."""
        payload = dict(self._payload(system, messages), stream=True)
        parts: list[str] = []
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                with client.stream("POST", _GROQ_CHAT_URL, headers=self._headers(),
                                   json=payload) as resp:
                    if resp.status_code != 200:
                        resp.read()
                        raise RuntimeError(_groq_http_error(resp, self._model, byok=bool(self._api_key)))
                    for line in resp.iter_lines():
                        piece = _sse_delta(line)
                        if piece is None:
                            continue
                        if piece:
                            parts.append(piece)
                            on_delta(piece)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Groq request failed: {exc}") from exc
        return "".join(parts)

    def _key(self) -> str:
        key = self._api_key if self._api_key is not None else os.environ.get("GROQ_API_KEY", "")
        if not str(key).strip():
            raise RuntimeError(
                "No Groq API key available. Add yours in Settings "
                "(https://console.groq.com/keys) or set GROQ_API_KEY on the server."
            )
        return str(key)

    def complete(self, *, system: str, messages: Sequence[LLMMessage]) -> str:
        payload = self._payload(system, messages)
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                resp = client.post(_GROQ_CHAT_URL, headers=self._headers(), json=payload)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Groq request failed: {exc}") from exc
        if resp.status_code != 200:
            raise RuntimeError(_groq_http_error(resp, self._model, byok=bool(self._api_key)))
        body = resp.json()
        choices = body.get("choices") or [{}]
        return (choices[0].get("message") or {}).get("content") or ""


def _sse_delta(line: str) -> Optional[str]:
    """The text fragment in one SSE line of an OpenAI-style chat stream, ''
    for a frame without content, None for anything that is not a data frame."""
    if not line or not line.startswith("data:"):
        return None
    raw = line[5:].strip()
    if not raw or raw == "[DONE]":
        return None
    try:
        frame = json.loads(raw)
    except ValueError:
        return None
    choices = frame.get("choices") or [{}]
    delta = (choices[0].get("delta") or {})
    return delta.get("content") or ""


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
