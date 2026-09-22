"""SessionBus: wake-ups for live watchers of a session.

Writers (the chat loop, submit and grade routes) call `notify(sid)` from any
thread; each watcher holds an asyncio queue bound to its own event loop and is
woken with call_soon_threadsafe. The bus carries no data: a woken watcher
re-reads the transcript from the store, so nothing is lost if a wake-up is
missed and a periodic re-check covers the rest. In-process by design: the
deployment runs a single replica (railway.toml).
"""
from __future__ import annotations

import asyncio
import threading
from typing import Optional


class SessionBus:
    def __init__(self) -> None:
        self._subs: dict[str, set] = {}
        self._lock = threading.Lock()

    def subscribe(self, session_id: str) -> "asyncio.Queue[str]":
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        q._sim_loop = loop            # type: ignore[attr-defined]
        with self._lock:
            self._subs.setdefault(session_id, set()).add(q)
        return q

    def unsubscribe(self, session_id: str, q) -> None:
        with self._lock:
            subs = self._subs.get(session_id)
            if subs:
                subs.discard(q)
                if not subs:
                    self._subs.pop(session_id, None)

    def notify(self, session_id: str, reason: str = "changed") -> int:
        """Wake every watcher of the session; returns how many were woken."""
        with self._lock:
            subs = list(self._subs.get(session_id, ()))
        for q in subs:
            loop: Optional[asyncio.AbstractEventLoop] = getattr(q, "_sim_loop", None)
            if loop is None or loop.is_closed():
                continue
            try:
                loop.call_soon_threadsafe(q.put_nowait, reason)
            except RuntimeError:
                continue
        return len(subs)

    def watchers(self, session_id: str) -> int:
        with self._lock:
            return len(self._subs.get(session_id, ()))
