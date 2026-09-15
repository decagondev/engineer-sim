from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


class ReadOnlyWorkspace(RuntimeError):
    """The workspace behind this root cannot be written (e.g. a GitHub repo)."""


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


class WorkspaceFiles(Protocol):
    """Port: the files of one workspace. `root` is whatever the adapter needs to
    find it (a sandbox workdir for the folder adapter, a repo URL for GitHub);
    the web layer never inspects it. Path-safe: never escapes the root.
    """

    def list_dir(self, root: str, relpath: str = "") -> Sequence[FileEntry]: ...

    def read_file(self, root: str, relpath: str) -> FileContent: ...

    def write_file(self, root: str, relpath: str, text: str) -> None: ...

    def refresh(self, root: str) -> str:
        """Re-read the source and return a short revision label."""
        ...


# Older name, kept for adapters and tests that only read.
WorkspaceReader = WorkspaceFiles
