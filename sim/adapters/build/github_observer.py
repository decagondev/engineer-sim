from __future__ import annotations

from typing import Optional

from sim.adapters.build.github_api import GitHubApi, GitHubReadError, parse_repo

__all__ = ["GitHubReadError", "parse_repo", "GitHostBuildObserver"]

# Documents the grader and the assessor should read verbatim when a repo is the
# source of the build record (design-doc tracks, and product repos that ship a
# write-up). Capped so a long README cannot crowd out the transcript.
_DOC_FILES = ("DESIGN.md", "TICKETS.md", "README.md")
_DOC_CAP = 12_000


class GitHostBuildObserver:
    """BuildRecordSource for a PUBLIC GitHub repo, read via the REST API. The
    learner submits their public repo URL; this reads the commit history (and, if
    it's a fork, the net diff against the starter) as the build record.

    Unauthenticated reads are rate-limited (~60/hr per IP); set GITHUB_TOKEN to
    raise that to ~5000/hr. Only public repos are read — no auth to the repo needed.
    """

    def __init__(self, token: Optional[str] = None, max_commits: int = 30,
                 max_files: int = 60, api: Optional[GitHubApi] = None) -> None:
        self._api = api or GitHubApi(token=token)
        self._max_commits = max_commits
        self._max_files = max_files

    @property
    def api(self) -> GitHubApi:
        return self._api

    # -- BuildRecordSource port: summary(path) where path is the repo URL --
    def summary(self, repo_url: str) -> str:
        owner, repo = parse_repo(repo_url)
        info = self._api.repo(owner, repo)
        default = info.get("default_branch", "main")
        commits = self._api.commits(owner, repo, self._max_commits)

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
                cmp = self._api.compare(owner, repo, base, head)
                files = cmp.get("files", [])
                lines.append(f"\nNET CHANGES vs starter ({parent['full_name']}): "
                             f"{len(files)} file(s)")
                for f in files[: self._max_files]:
                    lines.append(f"  {f.get('status','?'):9} {f.get('filename','')} "
                                 f"(+{f.get('additions',0)}/-{f.get('deletions',0)})")
            except GitHubReadError:
                pass

        for name in _DOC_FILES:
            text = self._api.file_text(owner, repo, name, ref=default)
            if text and text.strip():
                lines.append(f"\n{name}:\n{text[:_DOC_CAP]}")
        return "\n".join(lines)

    def read_file(self, repo_url: str, path: str) -> Optional[str]:
        """Text of one file on the default branch, or None. Never raises for
        the expected cases (missing file, private repo, rate limit)."""
        try:
            owner, repo = parse_repo(repo_url)
        except ValueError:
            return None
        try:
            return self._api.file_text(owner, repo, path)
        except GitHubReadError:
            return None

    def validate(self, repo_url: str) -> tuple[bool, str]:
        """Submit-time check: (ok, human message). Never raises for expected cases."""
        try:
            owner, repo = parse_repo(repo_url)
        except ValueError as e:
            return False, str(e)
        try:
            commits = self._api.commits(owner, repo, 1)
        except GitHubReadError as e:
            return False, str(e)
        if not commits:
            return False, "that repo has no commits yet — commit and push first"
        return True, f"{owner}/{repo} looks good"
