"""Read-only WorkspaceFiles over a public GitHub repo. `root` is the repo URL.

One tree call per (repo, head sha) is cached in memory; `refresh` re-reads the
default branch tip and drops the cache when it moved. File reads go through the
contents API one file at a time, so a GITHUB_TOKEN is strongly advised on a
shared server (see docs/WORKSPACE-PLAN.md section 6).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from sim.adapters.build.github_api import GitHubApi, GitHubReadError, parse_repo
from sim.core.ports.workspace import FileContent, FileEntry, ReadOnlyWorkspace


@dataclass
class _Snapshot:
    sha: str
    blobs: dict          # path -> size
    dirs: set            # every directory path, "" for the root


class GitHubWorkspaceFiles:
    def __init__(self, api: Optional[GitHubApi] = None, token: Optional[str] = None,
                 max_bytes: int = 200_000) -> None:
        self._api = api or GitHubApi(token=token)
        self._max = max_bytes
        self._cache: dict[str, _Snapshot] = {}

    # -- cache ------------------------------------------------------------
    def _key(self, root: str) -> tuple[str, str]:
        return parse_repo(root)

    def _snapshot(self, root: str, force: bool = False) -> _Snapshot:
        owner, repo = self._key(root)
        k = f"{owner}/{repo}".lower()
        snap = self._cache.get(k)
        if snap is not None and not force:
            return snap
        _, sha = self._api.head(owner, repo)
        if snap is not None and snap.sha == sha:
            return snap
        blobs: dict[str, int] = {}
        dirs: set[str] = {""}
        for node in self._api.tree(owner, repo, sha) if sha else []:
            path = node.get("path") or ""
            if not path or path.split("/")[0] == ".git":
                continue
            if node.get("type") == "tree":
                dirs.add(path)
            elif node.get("type") == "blob":
                blobs[path] = int(node.get("size") or 0)
                parent = path.rsplit("/", 1)[0] if "/" in path else ""
                while parent and parent not in dirs:
                    dirs.add(parent)
                    parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
        snap = _Snapshot(sha=sha, blobs=blobs, dirs=dirs)
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
                seen[path] = FileEntry(path[len(prefix):], False, size)
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
        owner, repo = self._key(root)
        try:
            text = self._api.file_text(owner, repo, rel, ref=snap.sha, max_bytes=self._max)
        except GitHubReadError as e:
            return FileContent(rel, None, str(e))
        if text is None:
            return FileContent(rel, None, "binary file")
        return FileContent(rel, text, "")

    def write_file(self, root: str, relpath: str, text: str) -> None:
        raise ReadOnlyWorkspace("this workspace mirrors your GitHub repo: push, then Refresh")

    def diff(self, root: str) -> str:
        """Net changes against the fork parent via the compare API (only a
        fork has a starter to compare with)."""
        owner, repo = self._key(root)
        info = self._api.repo(owner, repo)
        parent = info.get("parent") if info.get("fork") else None
        if not parent:
            return ""
        base = f"{parent['owner']['login']}:{parent.get('default_branch', 'main')}"
        head = f"{owner}:{info.get('default_branch', 'main')}"
        try:
            cmp = self._api.compare(owner, repo, base, head)
        except GitHubReadError:
            return ""
        parts = []
        for f in cmp.get("files", []):
            name = f.get("filename", "")
            parts.append(f"diff --git a/{name} b/{name}")
            parts.append(f"--- a/{name}\n+++ b/{name}")
            parts.append(f.get("patch") or f"(binary or too large: {f.get('status', '?')})")
        return "\n".join(parts)

    def refresh(self, root: str) -> str:
        snap = self._snapshot(root, force=True)
        return snap.sha[:7] if snap.sha else "(empty repo)"


def _norm(relpath: str) -> str:
    rel = (relpath or "").replace("\\", "/").strip().strip("/")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("path escapes the workspace")
    return "/".join(parts)
