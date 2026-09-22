"""LLMClient that prefers the signed-in user's Groq key when one is stored."""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from sim.core.ports.llm import DeltaSink, LLMClient, LLMMessage, complete_with_deltas


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
        return self._run(system, messages, None)

    def stream(self, *, system: str, messages: Sequence[LLMMessage], on_delta: DeltaSink) -> str:
        return self._run(system, messages, on_delta)

    def _run(self, system: str, messages: Sequence[LLMMessage], on_delta: Optional[DeltaSink]) -> str:
        key = (self._resolve_key() or "").strip()
        if key:
            from sim.adapters.llm.failover import is_transient
            from sim.adapters.llm.groq_client import GroqClient
            emitted = 0

            def sink(chunk: str) -> None:
                nonlocal emitted
                emitted += 1
                on_delta(chunk)

            try:
                return complete_with_deltas(GroqClient(model=self._groq_model, api_key=key),
                                            system=system, messages=messages,
                                            on_delta=sink if on_delta is not None else None)
            except Exception as exc:
                # the learner's own key is rate-limited or Groq is down: use the
                # classroom chain rather than fail their turn (unless part of the
                # reply already went out)
                if emitted or not is_transient(exc):
                    raise
        return complete_with_deltas(self._fallback, system=system, messages=messages, on_delta=on_delta)


def user_key_resolver(users, secret: str):
    def resolve() -> str:
        from sim.adapters.llm.request_context import current_user
        from sim.adapters.auth.secretbox import decrypt_secret
        rec = current_user(users)
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
        groq_model=getattr(config, "groq_model", "openai/gpt-oss-120b"),
    )
