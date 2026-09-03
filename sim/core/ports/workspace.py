from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class FileEntry:
    name: str
    is_dir: bool
    size: int


@dataclass(frozen=True)
class FileContent:
    path: str
    text: Optional[str]      # None when not shown (binary / too large)
    note: str = ""           # reason when text is None


class WorkspaceReader(Protocol):
    """Port: read-only view of a sandbox working directory. Path-safe: never
    escapes the given workdir.
    """

    def list_dir(self, workdir: str, relpath: str = "") -> Sequence[FileEntry]: ...

    def read_file(self, workdir: str, relpath: str) -> FileContent: ...
