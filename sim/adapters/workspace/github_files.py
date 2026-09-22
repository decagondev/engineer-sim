"""WorkspaceFiles over a public repo on a forge (GitHub or a GitLab instance),
through the RepoHost port. `root` is the repo URL.

One tree call per (repo, head sha) is cached in memory; `refresh` re-reads the
default branch tip and drops the cache when it moved. File reads go through the
host one file at a time, so a server token is strongly advised on a shared
server (see docs/WORKSPACE-PLAN.md section 6). Writes commit through the host's
file API and only when `can_write(root)` says the current request may.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from sim.adapters.build.github_api import GitHubApi
from sim.core.ports.repo_host import RepoHost, RepoHostError, RepoRef
from sim.core.ports.workspace import FileContent, FileEntry, ReadOnlyWorkspace


@dataclass
class _Snapshot:
    sha: str
    blobs: dict          # path -> size (-1 when the host does not list sizes)
    dirs: set            # every directory path, "" for the root
    blob_shas: dict = None   # path -> blob sha (needed to update a file)
    branch: str = "main"


def _accepts_root(fn: Callable) -> bool:
    try:
        return len(inspect.signature(fn).parameters) >= 1
    except (TypeError, ValueError):
        return False


class RepoWorkspaceFiles:
    def __init__(self, host: RepoHost, max_bytes: int = 200_000, can_write=None) -> None:
        """can_write(root) says whether the *current request's* token may commit
        to that repo (a personal OAuth token with a write scope); the classroom
        token never writes. A zero-argument callable is accepted too."""
        self._host = host
        self._max = max_bytes
        self._cache: dict[str, _Snapshot] = {}
        fn = can_write or (lambda: False)
        self._can_write = fn if _accepts_root(fn) else (lambda root="": fn())

    @property
    def host(self) -> RepoHost:
        return self._host

    def can_write(self, root: str = "") -> bool:
        try:
            return bool(self._can_write(root))
        except Exception:
            return False

    # -- cache ------------------------------------------------------------
    def _ref(self, root: str) -> RepoRef:
        return self._host.parse(root)

    def _snapshot(self, root: str, force: bool = False) -> _Snapshot:
        ref = self._ref(root)
        k = f"{ref.host}/{ref.full_name}".lower()
        snap = self._cache.get(k)
        if snap is not None and not force:
            return snap
        branch, sha = self._host.head(ref)
        if snap is not None and snap.sha == sha:
            return snap
        blobs: dict[str, int] = {}
        blob_shas: dict[str, str] = {}
        dirs: set[str] = {""}
        for node in self._host.tree(ref, sha) if sha else []:
            path = node.path
            if not path or path.split("/")[0] == ".git":
                continue
            if node.is_dir:
                dirs.add(path)
            else:
                blobs[path] = int(node.size)
                blob_shas[path] = node.sha or ""
                parent = path.rsplit("/", 1)[0] if "/" in path else ""
                while parent and parent not in dirs:
                    dirs.add(parent)
                    parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
        snap = _Snapshot(sha=sha, blobs=blobs, dirs=dirs, blob_shas=blob_shas, branch=branch)
        self._cache[k] = snap
        return snap

    # -- WorkspaceFiles port ---------------------------------------------
    def list_dir(self, root: str, relpath: str = "") -> Sequence[FileEntry]:
        rel = _norm(relpath)
        snap = self._snapshot(root)
        if rel not in snap.dirs:
            raise NotADirectoryError(relpath)
        prefix = rel + "/" if rel else ""
        seen: dict[str, FileEntry] = {}
        for d in snap.dirs:
            if d and d.startswith(prefix) and "/" not in d[len(prefix):]:
                seen[d] = FileEntry(d[len(prefix):], True, 0)
        for path, size in snap.blobs.items():
            if path.startswith(prefix) and "/" not in path[len(prefix):]:
                seen[path] = FileEntry(path[len(prefix):], False, max(size, 0))
        return sorted(seen.values(), key=lambda e: (not e.is_dir, e.name.lower()))

    def read_file(self, root: str, relpath: str) -> FileContent:
        rel = _norm(relpath)
        snap = self._snapshot(root)
        if rel in snap.dirs:
            raise IsADirectoryError(relpath)
        if rel not in snap.blobs:
            raise FileNotFoundError(relpath)
        size = snap.blobs[rel]
        if size > self._max:
            return FileContent(rel, None, f"file too large to preview ({size} bytes)")
        try:
            text = self._host.file_text(self._ref(root), rel, at=snap.sha, max_bytes=self._max)
        except RepoHostError as e:
            return FileContent(rel, None, str(e))
        if text is None:
            return FileContent(rel, None, "binary file or too large to preview")
        return FileContent(rel, text, "")

    def write_file(self, root: str, relpath: str, text: str) -> None:
        """Commit one file to the learner's fork through the host's file API.
        Only with their own OAuth token; the classroom token never writes."""
        if not self.can_write(root):
            label = self._host.label_for(root) if hasattr(self._host, "label_for") else self._host.label
            raise ReadOnlyWorkspace(f"connect your {label} account in the Workspace app to edit here; "
                                    "otherwise push from your machine and press Refresh")
        rel = _norm(relpath)
        if not rel or rel.split("/")[0] == ".git":
            raise ValueError("invalid path")
        ref = self._ref(root)
        snap = self._snapshot(root)
        if rel in snap.dirs:
            raise IsADirectoryError(relpath)
        existing = (snap.blob_shas or {}).get(rel, "") or ("exists" if rel in snap.blobs else "")
        out = self._host.put_file(ref, rel, text, message=f"Edit {rel} from the workstation",
                                  sha=existing, branch=snap.branch)
        # keep the cache truthful without another tree fetch
        snap.blobs[rel] = len(text.encode("utf-8"))
        if snap.blob_shas is not None:
            snap.blob_shas[rel] = out.blob_sha or snap.blob_shas.get(rel, "") or "exists"
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        while parent and parent not in snap.dirs:
            snap.dirs.add(parent)
            parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
        if out.commit_sha:
            snap.sha = out.commit_sha

    def diff(self, root: str) -> str:
        """Net changes against the fork parent (only a fork has a starter to
        compare with)."""
        ref = self._ref(root)
        try:
            files = list(self._host.changes(ref))
        except RepoHostError:
            return ""
        parts = []
        for f in files:
            parts.append(f"diff --git a/{f.path} b/{f.path}")
            parts.append(f"--- a/{f.path}\n+++ b/{f.path}")
            parts.append(f.patch or f"(binary or too large: {f.status})")
        return "\n".join(parts)

    def refresh(self, root: str) -> str:
        snap = self._snapshot(root, force=True)
        return snap.sha[:7] if snap.sha else "(empty repo)"


class GitHubWorkspaceFiles(RepoWorkspaceFiles):
    """GitHub-only construction kept for the original wiring and tests."""

    def __init__(self, api: Optional[GitHubApi] = None, token: Optional[str] = None,
                 max_bytes: int = 200_000, can_write=None) -> None:
        from sim.adapters.build.github_host import GitHubHost
        super().__init__(host=GitHubHost(api=api or GitHubApi(token=token)),
                         max_bytes=max_bytes, can_write=can_write)

    @property
    def _api(self):
        return self._host.api


def _norm(relpath: str) -> str:
    rel = (relpath or "").replace("\\", "/").strip().strip("/")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("path escapes the workspace")
    return "/".join(parts)
