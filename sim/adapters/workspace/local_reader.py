from __future__ import annotations

from pathlib import Path
from typing import Sequence

from sim.core.ports.workspace import FileContent, FileEntry


class LocalWorkspaceReader:
    """Reads files from a sandbox workdir on the local filesystem. Refuses any
    path that resolves outside the workdir (no traversal). Read-only.
    """

    def __init__(self, max_bytes: int = 200_000, hide=(".git",)) -> None:
        self._max = max_bytes
        self._hide = set(hide)

    def _safe(self, workdir: str, relpath: str) -> Path:
        base = Path(workdir).resolve()
        target = (base / relpath).resolve()
        if target != base and base not in target.parents:
            raise ValueError("path escapes the workspace")
        return target

    def list_dir(self, workdir: str, relpath: str = "") -> Sequence[FileEntry]:
        base = self._safe(workdir, relpath)
        if not base.is_dir():
            raise NotADirectoryError(relpath)
        entries = []
        for p in sorted(base.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name in self._hide:
                continue
            entries.append(FileEntry(p.name, p.is_dir(),
                                     p.stat().st_size if p.is_file() else 0))
        return entries

    def read_file(self, workdir: str, relpath: str) -> FileContent:
        p = self._safe(workdir, relpath)
        if p.is_dir():
            raise IsADirectoryError(relpath)
        if not p.exists():
            raise FileNotFoundError(relpath)
        size = p.stat().st_size
        if size > self._max:
            return FileContent(relpath, None, f"file too large to preview ({size} bytes)")
        raw = p.read_bytes()
        try:
            return FileContent(relpath, raw.decode("utf-8"), "")
        except UnicodeDecodeError:
            return FileContent(relpath, None, "binary file")
