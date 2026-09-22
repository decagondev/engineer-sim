"""FailoverLLMClient: try the primary model; on a transient failure (rate
limit, overload, timeout) try the configured fallbacks in order. Remembers the
last failover so the admin panel and /health can show it."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from sim.core.ports.llm import LLMClient, LLMMessage

_TRANSIENT = ("429", "rate limit", "rate_limit", "quota", "overloaded", "503", "502", "504",
              "timed out", "timeout", "temporarily", "capacity", "try again")


def is_transient(exc: BaseException) -> bool:
    text = f"{exc.__class__.__name__}: {exc}".lower()
    return any(k in text for k in _TRANSIENT)


class FailoverLLMClient:
    def __init__(self, primary: LLMClient, fallbacks: Sequence[tuple[str, LLMClient]] = (),
                 primary_name: str = "primary",
                 transient: Callable[[BaseException], bool] = is_transient) -> None:
        self._primary = primary
        self._primary_name = primary_name
        self._fallbacks = list(fallbacks)
        self._transient = transient
        self.last_failover: Optional[dict] = None
        self.failovers = 0

    @property
    def chain(self) -> list[str]:
        return [self._primary_name] + [n for n, _ in self._fallbacks]

    def status(self) -> dict:
        return {"chain": self.chain, "failovers": self.failovers, "last": self.last_failover}

    def complete(self, *, system: str, messages: Sequence[LLMMessage]) -> str:
        try:
            return self._primary.complete(system=system, messages=messages)
        except Exception as exc:
            if not self._fallbacks or not self._transient(exc):
                raise
            last_exc = exc
            came_from = self._primary_name
        for name, client in self._fallbacks:
            try:
                out = client.complete(system=system, messages=messages)
            except Exception as exc:
                last_exc = exc
                if not self._transient(exc):
                    raise
                came_from = name
                continue
            self.failovers += 1
            self.last_failover = {"ts": datetime.now(timezone.utc).isoformat(),
                                  "from": came_from, "to": name, "error": str(last_exc)[:200]}
            return out
        raise last_exc
