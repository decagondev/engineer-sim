from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


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


class GitHostBuildObserver:
    """BuildRecordSource for a PUBLIC GitHub repo, read via the REST API. The
    learner submits their public repo URL; this reads the commit history (and, if
    it's a fork, the net diff against the starter) as the build record.

    Unauthenticated reads are rate-limited (~60/hr per IP); set GITHUB_TOKEN to
    raise that to ~5000/hr. Only public repos are read — no auth to the repo needed.
    """

    def __init__(self, token: str | None = None, max_commits: int = 30,
                 max_files: int = 60) -> None:
        self._token = token or os.environ.get("GITHUB_TOKEN") or ""
        self._max_commits = max_commits
        self._max_files = max_files

    def _get(self, path: str):
        headers = {"Accept": "application/vnd.github+json",
                   "User-Agent": "flight-sim"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
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

    # -- BuildRecordSource port: summary(path) where path is the repo URL --
    def summary(self, repo_url: str) -> str:
        owner, repo = parse_repo(repo_url)
        info = self._get(f"/repos/{owner}/{repo}")
        default = info.get("default_branch", "main")
        commits = self._get(f"/repos/{owner}/{repo}/commits?per_page={self._max_commits}")

        lines = [f"REPO: {owner}/{repo}  (default branch: {default})",
                 f"COMMITS ({len(commits)}):"]
        for c in commits:
            msg = (c.get("commit", {}).get("message", "") or "").splitlines()[0]
            date = c.get("commit", {}).get("author", {}).get("date", "")
            lines.append(f"  {c.get('sha','')[:7]} {date} {msg}")

        parent = info.get("parent") if info.get("fork") else None
        if parent:
            base = f"{parent['owner']['login']}:{parent.get('default_branch','main')}"
            head = f"{owner}:{default}"
            try:
                cmp = self._get(f"/repos/{owner}/{repo}/compare/{base}...{head}")
                files = cmp.get("files", [])
                lines.append(f"\nNET CHANGES vs starter ({parent['full_name']}): "
                             f"{len(files)} file(s)")
                for f in files[: self._max_files]:
                    lines.append(f"  {f.get('status','?'):9} {f.get('filename','')} "
                                 f"(+{f.get('additions',0)}/-{f.get('deletions',0)})")
            except GitHubReadError:
                pass
        return "\n".join(lines)

    def validate(self, repo_url: str) -> tuple[bool, str]:
        """Submit-time check: (ok, human message). Never raises for expected cases."""
        try:
            owner, repo = parse_repo(repo_url)
        except ValueError as e:
            return False, str(e)
        try:
            commits = self._get(f"/repos/{owner}/{repo}/commits?per_page=1")
        except GitHubReadError as e:
            return False, str(e)
        if not commits:
            return False, "that repo has no commits yet — commit and push first"
        return True, f"{owner}/{repo} looks good"
