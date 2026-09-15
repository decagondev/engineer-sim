"""Thin GitHub REST client shared by the build observer (commit history) and the
workspace reader (browse a pushed repo). Public repos only; a GITHUB_TOKEN just
raises the rate limit. `fetch` is injectable so tests never touch the network.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from typing import Callable, Optional


class GitHubReadError(RuntimeError):
    """A public GitHub repo couldn't be read (not found, private, rate-limited)."""


def parse_repo(url: str) -> tuple[str, str]:
    """Accept https://github.com/owner/repo(.git), github.com/owner/repo, or owner/repo."""
    u = (url or "").strip()
    m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+?)(?:\.git)?/?$", u)
    if m:
        return m.group(1), m.group(2)
    m2 = re.match(r"^([\w.-]+)/([\w.-]+?)(?:\.git)?$", u)
    if m2:
        return m2.group(1), m2.group(2)
    raise ValueError("that doesn't look like a GitHub repo URL")


def _default_fetch(token: str) -> Callable[[str], object]:
    def fetch(path: str):
        headers = {"Accept": "application/vnd.github+json",
                   "User-Agent": "flight-sim"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request("https://api.github.com" + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise GitHubReadError(
                    "repo not found — check the URL, and make sure the repo is public")
            if e.code in (403, 429):
                raise GitHubReadError(
                    "GitHub rate limit hit — wait a minute, or set a GITHUB_TOKEN")
            raise GitHubReadError(f"GitHub returned {e.code}")
        except urllib.error.URLError as e:
            raise GitHubReadError(f"couldn't reach GitHub: {e.reason}")
    return fetch


class GitHubApi:
    def __init__(self, token: Optional[str] = None,
                 fetch: Optional[Callable[[str], object]] = None) -> None:
        self._token = token or os.environ.get("GITHUB_TOKEN") or ""
        self._fetch = fetch or _default_fetch(self._token)

    def get(self, path: str):
        return self._fetch(path)

    # -- repo metadata ----------------------------------------------------
    def repo(self, owner: str, repo: str) -> dict:
        return self.get(f"/repos/{owner}/{repo}") or {}

    def commits(self, owner: str, repo: str, n: int = 30) -> list:
        return self.get(f"/repos/{owner}/{repo}/commits?per_page={n}") or []

    def compare(self, owner: str, repo: str, base: str, head: str) -> dict:
        return self.get(f"/repos/{owner}/{repo}/compare/{base}...{head}") or {}

    def head(self, owner: str, repo: str) -> tuple[str, str]:
        """(default branch, sha of its tip)."""
        info = self.repo(owner, repo)
        branch = info.get("default_branch", "main")
        ref = self.get(f"/repos/{owner}/{repo}/branches/{branch}") or {}
        sha = ((ref.get("commit") or {}).get("sha") or "")
        return branch, sha

    # -- contents ---------------------------------------------------------
    def tree(self, owner: str, repo: str, sha: str) -> list:
        data = self.get(f"/repos/{owner}/{repo}/git/trees/{sha}?recursive=1") or {}
        return data.get("tree") or []

    def contents(self, owner: str, repo: str, path: str = "", ref: str = ""):
        q = f"?ref={ref}" if ref else ""
        p = f"/repos/{owner}/{repo}/contents/{path.strip('/')}{q}"
        return self.get(p)

    def file_text(self, owner: str, repo: str, path: str,
                  ref: str = "", max_bytes: int = 200_000) -> Optional[str]:
        """Decoded text of one file, or None when it is missing, binary or too big."""
        try:
            data = self.contents(owner, repo, path, ref)
        except GitHubReadError:
            return None
        if not isinstance(data, dict) or data.get("type") != "file":
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
