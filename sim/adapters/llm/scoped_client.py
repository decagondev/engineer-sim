"""LLMClient that prefers the signed-in user's Groq key when one is stored."""
from __future__ import annotations

from typing import Callable, Sequence

from sim.core.ports.llm import LLMClient, LLMMessage


class ScopedLLMClient:
    def __init__(
        self,
        fallback: LLMClient,
        *,
        resolve_key: Callable[[], str],
        groq_model: str,
    ) -> None:
        self._fallback = fallback
        self._resolve_key = resolve_key
        self._groq_model = groq_model

    def complete(self, *, system: str, messages: Sequence[LLMMessage]) -> str:
        key = (self._resolve_key() or "").strip()
        if key:
            from sim.adapters.llm.groq_client import GroqClient
            return GroqClient(model=self._groq_model, api_key=key).complete(
                system=system, messages=messages)
        return self._fallback.complete(system=system, messages=messages)


def user_key_resolver(users, secret: str):
    def resolve() -> str:
        from sim.adapters.llm.request_context import current_uid
        from sim.adapters.auth.secretbox import decrypt_secret
        uid = current_uid.get()
        if not uid or users is None:
            return ""
        rec = users.get(uid)
        if rec is None or not rec.groq_key_enc:
            return ""
        try:
            return decrypt_secret(secret, rec.groq_key_enc)
        except ValueError:
            return ""
    return resolve


def wrap_user_scoped_llm(llm: LLMClient, *, users, config) -> LLMClient:
    from sim.adapters.auth.secretbox import secret_from_config
    return ScopedLLMClient(
        llm,
        resolve_key=user_key_resolver(users, secret_from_config(config)),
        groq_model=getattr(config, "groq_model", "llama-3.3-70b-versatile"),
    )
