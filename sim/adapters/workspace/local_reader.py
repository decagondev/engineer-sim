from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

from sim.core.ports.workspace import FileContent, FileEntry


class LocalWorkspaceReader:
    """Files of a sandbox workdir on the local filesystem. Refuses any path
    that resolves outside the workdir (no traversal) and never touches `.git`.
    Writes are atomic (temp file + rename). `snapshot` commits the working
    tree so the build record can diff a browser-edited workspace.
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

    def write_file(self, workdir: str, relpath: str, text: str) -> None:
        p = self._safe(workdir, relpath)
        base = Path(workdir).resolve()
        if p == base:
            raise IsADirectoryError(relpath)
        top = p.relative_to(base).parts[0]
        if top in self._hide:
            raise ValueError(f"{top} is managed for you")
        if p.is_dir():
            raise IsADirectoryError(relpath)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".sim-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def refresh(self, workdir: str) -> str:
        return self._git(workdir, "rev-parse", "--short", "HEAD") or "working copy"

    def snapshot(self, workdir: str, message: str = "submission") -> str:
        """Commit everything in the working tree; returns the new short sha or ''."""
        self._git(workdir, "add", "-A")
        self._git(workdir, "commit", "-q", "-m", message)
        return self._git(workdir, "rev-parse", "--short", "HEAD")

    @staticmethod
    def _git(workdir: str, *args: str) -> str:
        try:
            r = subprocess.run(["git", "-C", str(workdir), *args],
                               capture_output=True, text=True, timeout=20)
        except (subprocess.SubprocessError, FileNotFoundError):
            return ""
        return r.stdout.strip() if r.returncode == 0 else ""


LocalWorkspaceFiles = LocalWorkspaceReader
