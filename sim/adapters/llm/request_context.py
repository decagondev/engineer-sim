from __future__ import annotations

from contextvars import ContextVar

current_uid: ContextVar[str] = ContextVar("sim_current_uid", default="")


def set_current_uid(uid: str) -> None:
    current_uid.set(uid or "")
