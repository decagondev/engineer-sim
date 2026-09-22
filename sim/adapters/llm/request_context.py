"""Request-scoped context shared by the adapters: who is calling, and their
directory record fetched at most once per request.

`current_uid` is set by the auth middleware (HTTP) and the websocket handler;
`current_user(users)` returns that person's `UserRecord`, reading the directory
the first time and answering from the memo afterwards, so the key resolvers and
the write checks do not each pay a Firestore round trip. `prime_user` lets the
auth layer store the record it already fetched.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

current_uid: ContextVar[str] = ContextVar("sim_current_uid", default="")
# (uid, record-or-None); a memo for a different uid is stale and ignored
_current_user: ContextVar[Optional[tuple]] = ContextVar("sim_current_user", default=None)


def set_current_uid(uid: str) -> None:
    current_uid.set(uid or "")
    _current_user.set(None)


def prime_user(rec) -> None:
    """Remember `rec` as the current user's record for the rest of this request."""
    if rec is not None and getattr(rec, "uid", ""):
        _current_user.set((rec.uid, rec))


def forget_user() -> None:
    _current_user.set(None)


def current_user(users):
    """The current uid's UserRecord (or None), read from `users` at most once
    per request. A store write should call `prime_user` with the new record
    so later readers in the same request see it."""
    uid = current_uid.get()
    if not uid or users is None:
        return None
    memo = _current_user.get()
    if memo is not None and memo[0] == uid:
        return memo[1]
    rec = users.get(uid)
    _current_user.set((uid, rec))
    return rec
