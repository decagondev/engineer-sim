from __future__ import annotations

from typing import Optional, Protocol, Sequence


class SessionFileStore(Protocol):
    """Port: the files a learner edited in the browser, kept durably so a
    server-side workspace can be rebuilt after a restart (hosted filesystems
    are ephemeral). Only edited files are stored; the starter supplies the rest.
    """

    def put(self, session_id: str, relpath: str, text: str, ts: str) -> None: ...

    def get(self, session_id: str, relpath: str) -> Optional[str]: ...

    def list(self, session_id: str) -> Sequence[str]: ...

    def delete_session(self, session_id: str) -> None: ...
