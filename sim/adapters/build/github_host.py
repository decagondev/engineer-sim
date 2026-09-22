"""RepoHost adapter for github.com, over the thin GitHubApi client."""
from __future__ import annotations

import re
from typing import Optional, Sequence

from sim.adapters.build.github_api import GitHubApi, GitHubReadError, parse_repo
from sim.core.ports.repo_host import (ChangedFile, Commit, RepoInfo, RepoRef, TreeNode,
                                      WriteResult)


class GitHubHost:
    label = "GitHub"
    host = "github.com"

    def __init__(self, api: Optional[GitHubApi] = None, token: Optional[str] = None) -> None:
        self._api = api or GitHubApi(token=token)

    @property
    def api(self) -> GitHubApi:
        return self._api

    def owns(self, url: str) -> bool:
        u = (url or "").strip()
        if re.search(r"(^|[/@.])github\.com([:/]|$)", u, re.I):
            return True
        # bare owner/repo is GitHub by convention (the original accepted form)
        return bool(re.match(r"^[\w.-]+/[\w.-]+$", u)) and "." not in u.split("/")[0]

    def parse(self, url: str) -> RepoRef:
        owner, repo = parse_repo(url)
        return RepoRef(host=self.host, owner=owner, repo=repo, url=(url or "").strip())

    def info(self, ref: RepoRef) -> RepoInfo:
        d = self._api.repo(ref.owner, ref.repo)
        parent = d.get("parent") if d.get("fork") else None
        return RepoInfo(default_branch=d.get("default_branch") or "main",
                        full_name=d.get("full_name") or ref.full_name,
                        is_fork=bool(parent),
                        parent_full_name=(parent or {}).get("full_name", ""),
                        parent_default_branch=(parent or {}).get("default_branch", "main"),
                        web_url=d.get("html_url", ""))

    def head(self, ref: RepoRef) -> tuple[str, str]:
        return self._api.head(ref.owner, ref.repo)

    def commits(self, ref: RepoRef, n: int = 30) -> Sequence[Commit]:
        out = []
        for c in self._api.commits(ref.owner, ref.repo, n) or []:
            meta = c.get("commit") or {}
            out.append(Commit(sha=c.get("sha", ""),
                              date=((meta.get("author") or {}).get("date") or ""),
                              message=(meta.get("message") or "")))
        return out

    def changes(self, ref: RepoRef) -> Sequence[ChangedFile]:
        d = self._api.repo(ref.owner, ref.repo)
        parent = d.get("parent") if d.get("fork") else None
        if not parent:
            return []
        base = f"{parent['owner']['login']}:{parent.get('default_branch', 'main')}"
        head = f"{ref.owner}:{d.get('default_branch', 'main')}"
        try:
            cmp = self._api.compare(ref.owner, ref.repo, base, head)
        except GitHubReadError:
            return []
        return [ChangedFile(path=f.get("filename", ""), status=f.get("status") or "modified",
                            additions=int(f.get("additions") or 0),
                            deletions=int(f.get("deletions") or 0),
                            patch=f.get("patch") or "")
                for f in cmp.get("files", [])]

    def tree(self, ref: RepoRef, sha: str) -> Sequence[TreeNode]:
        out = []
        for node in self._api.tree(ref.owner, ref.repo, sha) if sha else []:
            path = node.get("path") or ""
            if not path:
                continue
            if node.get("type") == "tree":
                out.append(TreeNode(path=path, is_dir=True))
            elif node.get("type") == "blob":
                out.append(TreeNode(path=path, size=int(node.get("size") or 0),
                                    sha=node.get("sha") or ""))
        return out

    def file_text(self, ref: RepoRef, path: str, at: str = "",
                  max_bytes: int = 200_000) -> Optional[str]:
        return self._api.file_text(ref.owner, ref.repo, path, ref=at, max_bytes=max_bytes)

    def put_file(self, ref: RepoRef, path: str, text: str, message: str,
                 sha: str = "", branch: str = "") -> WriteResult:
        out = self._api.put_file(ref.owner, ref.repo, path, text, message, sha=sha, branch=branch)
        return WriteResult(blob_sha=((out or {}).get("content") or {}).get("sha", ""),
                           commit_sha=((out or {}).get("commit") or {}).get("sha", ""))
