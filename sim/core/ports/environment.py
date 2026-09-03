from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


class SandboxUnavailable(RuntimeError):
    """The environment backend isn't available (e.g. Docker not installed/running)."""


class SandboxError(RuntimeError):
    """The environment backend failed to provision/teardown a sandbox."""


@dataclass(frozen=True)
class SandboxHandle:
    """A tester's working environment for a session."""

    session_id: str
    workdir: str            # absolute HOST path (git build record reads this)
    created: bool           # True if just provisioned, False if it already existed
    container: Optional[str] = None       # container name/id, if any
    connect_hint: Optional[str] = None    # how the tester gets in (e.g. docker exec)


class Environment(Protocol):
    """Port: a per-session sandbox the tester builds in. Local-folder and Docker
    adapters both satisfy this; the core never knows which is behind it (DIP/LSP).
    """

    def provision(self, session_id: str) -> SandboxHandle: ...

    def handle(self, session_id: str) -> Optional[SandboxHandle]: ...

    def teardown(self, session_id: str) -> None: ...
