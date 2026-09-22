"""RepoHost adapter for a GitLab instance (gitlab.com or self-hosted, e.g.
https://labs.gauntletai.com) over its v4 REST API. Public projects read
anonymously; a token (GITLAB_TOKEN, a pasted personal token, or the OAuth token
from Connect GitLab) is sent as a Bearer header and is what allows commits.

`fetch(path, method, body)` is injectable so tests never touch the network.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional, Sequence

from sim.core.ports.repo_host import (ChangedFile, Commit, RepoHostError, RepoInfo, RepoRef,
                                      TreeNode, WriteResult)


class GitLabReadError(RepoHostError):
    pass


def _enc(path: str) -> str:
    return urllib.parse.quote(path, safe="")


def _default_fetch(base_url: str, resolve_token: Callable[[], str]) -> Callable[..., object]:
    def fetch(path: str, method: str = "GET", body: Optional[dict] = None):
        headers = {"Accept": "application/json", "User-Agent": "flight-sim"}
        token = (resolve_token() or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(base_url + "/api/v4" + path, headers=headers,
                                     data=data, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise GitLabReadError(
                    "project not found: check the URL, and make sure the project is public")
            if e.code == 401:
                raise GitLabReadError("GitLab wants a sign-in for that: connect GitLab in the "
                                      "Workspace app, or make the project public")
            if e.code == 403:
                raise GitLabReadError("GitLab refused that (this token has no permission)")
            if e.code == 429:
                raise GitLabReadError("GitLab rate limit hit: wait a minute and try again")
            raise GitLabReadError(f"GitLab returned {e.code}")
        except urllib.error.URLError as e:
            raise GitLabReadError(f"could not reach GitLab: {e.reason}")
    return fetch


def validate_token(base_url: str, token: str) -> None:
    """One cheap authenticated call so a bad token fails in Settings."""
    tok = (token or "").strip()
    if not tok:
        raise RuntimeError("Paste a GitLab token.")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/v4/user",
        headers={"Accept": "application/json", "User-Agent": "flight-sim",
                 "Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("GitLab rejected that token. Create a personal access token "
                               "with the read_api scope (api to commit from the browser).")
        raise RuntimeError(f"GitLab returned {e.code}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach GitLab: {e.reason}")


class GitLabApi:
    """Thin client: paths are relative to /api/v4."""

    def __init__(self, base_url: str, token: str = "",
                 fetch: Optional[Callable[..., object]] = None,
                 resolve_token: Optional[Callable[[], str]] = None) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self._token = token or ""
        self._resolve = resolve_token or (lambda: self._token)
        self._fetch = fetch or _default_fetch(self.base_url, self._resolve)

    def get(self, path: str):
        return self._fetch(path)

    def send(self, method: str, path: str, body: dict):
        return self._fetch(path, method, body)

    def project(self, full_path: str) -> dict:
        return self.get(f"/projects/{_enc(full_path)}") or {}

    def branch(self, pid, branch: str) -> dict:
        return self.get(f"/projects/{pid}/repository/branches/{_enc(branch)}") or {}

    def commits(self, pid, n: int = 30, ref: str = "") -> list:
        q = f"per_page={n}" + (f"&ref_name={_enc(ref)}" if ref else "")
        return self.get(f"/projects/{pid}/repository/commits?{q}") or []

    def compare(self, pid, from_ref: str, to_ref: str, from_project_id=None) -> dict:
        q = f"from={_enc(from_ref)}&to={_enc(to_ref)}"
        if from_project_id is not None:
            q += f"&from_project_id={from_project_id}"
        return self.get(f"/projects/{pid}/repository/compare?{q}") or {}

    def tree(self, pid, sha: str, max_pages: int = 50) -> list:
        out: list = []
        for page in range(1, max_pages + 1):
            chunk = self.get(f"/projects/{pid}/repository/tree?recursive=true&per_page=100"
                             f"&page={page}&ref={_enc(sha)}") or []
            out.extend(chunk)
            if len(chunk) < 100:
                break
        return out

    def file(self, pid, path: str, ref: str) -> dict:
        return self.get(f"/projects/{pid}/repository/files/{_enc(path)}?ref={_enc(ref)}") or {}

    def put_file(self, pid, path: str, branch: str, text: str, message: str, create: bool) -> dict:
        body = {"branch": branch, "content": text, "commit_message": message}
        return self.send("POST" if create else "PUT",
                         f"/projects/{pid}/repository/files/{_enc(path)}", body) or {}


class GitLabHost:
    label = "GitLab"

    def __init__(self, base_url: str, api: Optional[GitLabApi] = None, token: str = "",
                 resolve_token: Optional[Callable[[], str]] = None) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.host = urllib.parse.urlparse(self.base_url).netloc.lower() if self.base_url else ""
        self._api = api or GitLabApi(self.base_url, token=token, resolve_token=resolve_token)
        self._ids: dict[str, object] = {}

    @property
    def api(self) -> GitLabApi:
        return self._api

    def owns(self, url: str) -> bool:
        u = (url or "").strip().lower()
        return bool(self.host) and bool(re.search(r"(^|[/@])" + re.escape(self.host) + r"([:/]|$)", u))

    def parse(self, url: str) -> RepoRef:
        u = (url or "").strip()
        if not self.host or not self.owns(u):
            raise ValueError(f"that doesn't look like a project URL on {self.host or 'GitLab'}")
        m = re.search(re.escape(self.host) + r"[:/]+(.+?)(?:\.git)?/?$", u, re.I)
        parts = [p for p in (m.group(1) if m else "").split("/") if p]
        if "-" in parts:                       # web-only suffixes such as /-/tree/main
            parts = parts[:parts.index("-")]
        if len(parts) < 2 or any(c in "?#" for c in "".join(parts)):
            raise ValueError(f"a GitLab project URL looks like https://{self.host}/group/project")
        return RepoRef(host=self.host, owner="/".join(parts[:-1]), repo=parts[-1], url=u)

    # -- helpers ------------------------------------------------------------
    def _project(self, ref: RepoRef) -> dict:
        d = self._api.project(ref.full_name)
        if d.get("id"):
            self._ids[ref.full_name.lower()] = d["id"]
        return d

    def _pid(self, ref: RepoRef):
        key = ref.full_name.lower()
        if key not in self._ids:
            self._ids[key] = self._project(ref).get("id") or _enc(ref.full_name)
        return self._ids[key]

    # -- RepoHost -----------------------------------------------------------
    def info(self, ref: RepoRef) -> RepoInfo:
        d = self._project(ref)
        parent = d.get("forked_from_project") or {}
        return RepoInfo(default_branch=d.get("default_branch") or "main",
                        full_name=d.get("path_with_namespace") or ref.full_name,
                        is_fork=bool(parent),
                        parent_full_name=parent.get("path_with_namespace", ""),
                        parent_default_branch=parent.get("default_branch") or "main",
                        web_url=d.get("web_url", ""))

    def head(self, ref: RepoRef) -> tuple[str, str]:
        d = self._project(ref)
        branch = d.get("default_branch") or "main"
        b = self._api.branch(self._pid(ref), branch)
        return branch, ((b.get("commit") or {}).get("id") or "")

    def commits(self, ref: RepoRef, n: int = 30) -> Sequence[Commit]:
        return [Commit(sha=c.get("id", ""),
                       date=c.get("committed_date") or c.get("created_at") or "",
                       message=c.get("message") or c.get("title") or "")
                for c in self._api.commits(self._pid(ref), n) or []]

    def changes(self, ref: RepoRef) -> Sequence[ChangedFile]:
        d = self._project(ref)
        parent = d.get("forked_from_project") or {}
        if not parent.get("id"):
            return []
        try:
            cmp = self._api.compare(d.get("id"), parent.get("default_branch") or "main",
                                    d.get("default_branch") or "main", from_project_id=parent["id"])
        except RepoHostError:
            return []
        out = []
        for f in cmp.get("diffs", []) or []:
            diff = f.get("diff") or ""
            lines = diff.splitlines()
            adds = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
            dels = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))
            status = ("added" if f.get("new_file") else "removed" if f.get("deleted_file")
                      else "renamed" if f.get("renamed_file") else "modified")
            out.append(ChangedFile(path=f.get("new_path") or f.get("old_path") or "",
                                   status=status, additions=adds, deletions=dels, patch=diff))
        return out

    def tree(self, ref: RepoRef, sha: str) -> Sequence[TreeNode]:
        out = []
        for node in self._api.tree(self._pid(ref), sha) if sha else []:
            path = node.get("path") or ""
            if not path:
                continue
            if node.get("type") == "tree":
                out.append(TreeNode(path=path, is_dir=True))
            elif node.get("type") == "blob":
                out.append(TreeNode(path=path, size=-1, sha=node.get("id") or ""))
        return out

    def file_text(self, ref: RepoRef, path: str, at: str = "",
                  max_bytes: int = 200_000) -> Optional[str]:
        try:
            if not at:
                at = self.head(ref)[0]
            data = self._api.file(self._pid(ref), path, at)
        except RepoHostError:
            return None
        if not isinstance(data, dict) or not data.get("file_path"):
            return None
        if int(data.get("size") or 0) > max_bytes:
            return None
        raw = data.get("content") or ""
        if data.get("encoding") == "base64":
            try:
                return base64.b64decode(raw).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return None
        return raw or None

    def put_file(self, ref: RepoRef, path: str, text: str, message: str,
                 sha: str = "", branch: str = "") -> WriteResult:
        pid = self._pid(ref)
        if not branch:
            branch = self.head(ref)[0]
        self._api.put_file(pid, path, branch, text, message, create=not sha)
        # GitLab's file API answers with the path only; one branch read keeps
        # the cached tip truthful.
        try:
            tip = ((self._api.branch(pid, branch).get("commit") or {}).get("id") or "")
        except RepoHostError:
            tip = ""
        return WriteResult(blob_sha="", commit_sha=tip)
