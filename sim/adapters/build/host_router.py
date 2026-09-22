"""One RepoHost that fans out to the forge a URL belongs to. Adding a forge is
one entry in `hosts`; the observer and the workspace never know which one
answered. `can_write(url)` asks the matching host's permission check."""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from sim.core.ports.repo_host import (ChangedFile, Commit, RepoHost, RepoInfo, RepoRef,
                                      TreeNode, WriteResult)


class HostRouter:
    label = "repo host"

    def __init__(self, hosts: Sequence[RepoHost],
                 can_write: Optional[dict[str, Callable[[], bool]]] = None) -> None:
        self._hosts = [h for h in hosts if h is not None]
        self._can_write = dict(can_write or {})

    @property
    def hosts(self) -> Sequence[RepoHost]:
        return list(self._hosts)

    def host_for(self, url: str) -> Optional[RepoHost]:
        for h in self._hosts:
            if h.owns(url):
                return h
        return None

    def parse(self, url: str) -> RepoRef:
        h = self.host_for(url)
        if h is None:
            names = " or ".join(getattr(x, "host", "") or x.label for x in self._hosts) or "a known host"
            raise ValueError(f"that doesn't look like a repo URL on {names}")
        return h.parse(url)

    def _h(self, ref: RepoRef) -> RepoHost:
        for h in self._hosts:
            if getattr(h, "host", "") == ref.host:
                return h
        raise ValueError(f"no adapter for {ref.host}")

    def can_write(self, url: str = "") -> bool:
        """May the current request commit to `url`? Without a URL: to any host."""
        if not url:
            fns = list(self._can_write.values())
        else:
            h = self.host_for(url)
            fn = self._can_write.get(getattr(h, "host", "")) if h else None
            fns = [fn] if fn else []
        for fn in fns:
            try:
                if fn():
                    return True
            except Exception:
                continue
        return False

    def label_for(self, url: str) -> str:
        h = self.host_for(url)
        return h.label if h else "repo"

    def info(self, ref: RepoRef) -> RepoInfo:
        return self._h(ref).info(ref)

    def head(self, ref: RepoRef) -> tuple[str, str]:
        return self._h(ref).head(ref)

    def commits(self, ref: RepoRef, n: int = 30) -> Sequence[Commit]:
        return self._h(ref).commits(ref, n)

    def changes(self, ref: RepoRef) -> Sequence[ChangedFile]:
        return self._h(ref).changes(ref)

    def tree(self, ref: RepoRef, sha: str) -> Sequence[TreeNode]:
        return self._h(ref).tree(ref, sha)

    def file_text(self, ref: RepoRef, path: str, at: str = "", max_bytes: int = 200_000):
        return self._h(ref).file_text(ref, path, at, max_bytes)

    def put_file(self, ref: RepoRef, path: str, text: str, message: str,
                 sha: str = "", branch: str = "") -> WriteResult:
        return self._h(ref).put_file(ref, path, text, message, sha, branch)
