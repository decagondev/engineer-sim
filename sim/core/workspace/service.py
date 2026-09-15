"""WorkspaceService: the learner's editable files for one session.

Composes two ports. `files` is the workspace itself (a sandbox folder, or a
read-only GitHub repo). `store` is the durable overlay of files the learner
edited in the browser, so a hosted server can rebuild the folder after a
restart. Pure: no I/O of its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from sim.core.ports.session_files import SessionFileStore
from sim.core.ports.workspace import FileContent, FileEntry, WorkspaceFiles

DESIGN_FILE = "DESIGN.md"
TICKETS_FILE = "TICKETS.md"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceWriteError(ValueError):
    """The write was refused (bad path, too large, read-only workspace)."""


@dataclass
class WorkspaceService:
    files: WorkspaceFiles
    store: Optional[SessionFileStore] = None
    clock: Callable[[], str] = _utcnow_iso
    max_bytes: int = 900_000          # under the 1 MB Firestore document cap
    _hydrated: set = field(default_factory=set)

    # -- reads --------------------------------------------------------------
    def list_dir(self, root: str, session_id: str, relpath: str = "") -> Sequence[FileEntry]:
        self.hydrate(root, session_id)
        return self.files.list_dir(root, relpath)

    def read(self, root: str, session_id: str, relpath: str) -> FileContent:
        self.hydrate(root, session_id)
        return self.files.read_file(root, relpath)

    # -- writes -------------------------------------------------------------
    def write(self, root: str, session_id: str, relpath: str, text: str) -> None:
        rel = _clean(relpath)
        if len(text.encode("utf-8")) > self.max_bytes:
            raise WorkspaceWriteError(
                f"file too large to save here (limit {self.max_bytes // 1000} KB)")
        # the durable copy first: if the folder is lost the edit is not
        if self.store is not None:
            self.store.put(session_id, rel, text, self.clock())
        self.files.write_file(root, rel, text)

    def hydrate(self, root: str, session_id: str) -> int:
        """Replay stored edits onto a (re)provisioned workspace. Once per
        session per process; returns how many files were restored."""
        key = (root, session_id)
        if self.store is None or key in self._hydrated:
            return 0
        self._hydrated.add(key)
        restored = 0
        for rel in self.store.list(session_id):
            text = self.store.get(session_id, rel)
            if text is None:
                continue
            try:
                current = self.files.read_file(root, rel)
                if current.text == text:
                    continue
            except (FileNotFoundError, IsADirectoryError, ValueError):
                pass
            try:
                self.files.write_file(root, rel, text)
                restored += 1
            except Exception:
                continue
        return restored

    def forget(self, root: str, session_id: str) -> None:
        """After a teardown the next provision must hydrate again."""
        self._hydrated.discard((root, session_id))

    # -- submission -----------------------------------------------------------
    def design_text(self, root: str, session_id: str) -> str:
        """DESIGN.md as it is now, with TICKETS.md appended when present."""
        self.hydrate(root, session_id)
        parts = []
        for name in (DESIGN_FILE, TICKETS_FILE):
            try:
                c = self.files.read_file(root, name)
            except (FileNotFoundError, IsADirectoryError, ValueError):
                continue
            if c.text and c.text.strip():
                parts.append(c.text if name == DESIGN_FILE else f"\n\n# {name}\n\n{c.text}")
        return "".join(parts)


def _clean(relpath: str) -> str:
    rel = (relpath or "").replace("\\", "/").strip().strip("/")
    if not rel:
        raise WorkspaceWriteError("a file name is required")
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise WorkspaceWriteError("invalid path")
    if parts[0] == ".git":
        raise WorkspaceWriteError("the .git folder is managed for you")
    return "/".join(parts)
