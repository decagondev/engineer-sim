from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class ArchiveRecord:
    """A session's markdown audit, kept after the live session is deleted."""

    session_id: str
    ts: str
    title: str = ""
    scenario: str = ""
    assignee: str = ""
    state: str = ""
    size: int = 0
    markdown: str = ""      # omitted from listings

    def meta(self) -> dict:
        d = asdict(self)
        d.pop("markdown", None)
        return d


class ArchiveStore(Protocol):
    def put(self, record: ArchiveRecord) -> ArchiveRecord: ...

    def get(self, session_id: str) -> Optional[ArchiveRecord]: ...

    def list(self) -> Sequence[ArchiveRecord]:
        """Metadata only, newest first."""
        ...
