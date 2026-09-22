from __future__ import annotations

from typing import Optional

from sim.adapters.build.github_api import GitHubApi, GitHubReadError, parse_repo
from sim.core.ports.repo_host import RepoHost, RepoHostError

__all__ = ["GitHubReadError", "parse_repo", "GitHostBuildObserver"]

# Documents the grader and the assessor should read verbatim when a repo is the
# source of the build record (design-doc tracks, and product repos that ship a
# write-up). Capped so a long README cannot crowd out the transcript.
_DOC_FILES = ("DESIGN.md", "TICKETS.md", "README.md")
_DOC_CAP = 12_000


class GitHostBuildObserver:
    """BuildRecordSource for a PUBLIC repo on any configured forge (GitHub, a
    GitLab instance), read through the RepoHost port. The learner submits their
    repo URL; this reads the commit history (and, if it's a fork, the net diff
    against the starter) as the build record.

    Anonymous reads are rate-limited; a server token (GITHUB_TOKEN / GITLAB_TOKEN)
    or the learner's own token raises that. Only public repos are read.
    """

    def __init__(self, token: Optional[str] = None, max_commits: int = 30,
                 max_files: int = 60, api: Optional[GitHubApi] = None,
                 host: Optional[RepoHost] = None) -> None:
        if host is None:
            from sim.adapters.build.github_host import GitHubHost
            host = GitHubHost(api=api or GitHubApi(token=token))
        self._host = host
        self._max_commits = max_commits
        self._max_files = max_files

    @property
    def host(self) -> RepoHost:
        return self._host

    @property
    def api(self):
        """The GitHub client when this observer is GitHub-only (older wiring)."""
        return getattr(self._host, "api", None)

    # -- BuildRecordSource port: summary(path) where path is the repo URL --
    def summary(self, repo_url: str) -> str:
        ref = self._host.parse(repo_url)
        info = self._host.info(ref)
        default = info.default_branch
        commits = list(self._host.commits(ref, self._max_commits))
        label = self._host.label if not hasattr(self._host, "label_for") else self._host.label_for(repo_url)

        lines = [f"REPO: {info.full_name or ref.full_name}  on {label}  (default branch: {default})",
                 f"COMMITS ({len(commits)}):"]
        for c in commits:
            msg = (c.message or "").splitlines()[0] if c.message else ""
            lines.append(f"  {c.sha[:7]} {c.date} {msg}")

        if info.is_fork:
            try:
                files = list(self._host.changes(ref))
            except RepoHostError:
                files = []
            if files:
                lines.append(f"\nNET CHANGES vs starter ({info.parent_full_name}): {len(files)} file(s)")
                for f in files[: self._max_files]:
                    lines.append(f"  {f.status:9} {f.path} (+{f.additions}/-{f.deletions})")

        for name in _DOC_FILES:
            try:
                text = self._host.file_text(ref, name, at=default)
            except RepoHostError:
                text = None
            if text and text.strip():
                lines.append(f"\n{name}:\n{text[:_DOC_CAP]}")
        return "\n".join(lines)

    def read_file(self, repo_url: str, path: str) -> Optional[str]:
        """Text of one file on the default branch, or None. Never raises for
        the expected cases (missing file, private repo, rate limit)."""
        try:
            ref = self._host.parse(repo_url)
        except ValueError:
            return None
        try:
            return self._host.file_text(ref, path)
        except RepoHostError:
            return None

    def validate(self, repo_url: str) -> tuple[bool, str]:
        """Submit-time check: (ok, human message). Never raises for expected cases."""
        try:
            ref = self._host.parse(repo_url)
        except ValueError as e:
            return False, str(e)
        try:
            commits = list(self._host.commits(ref, 1))
        except RepoHostError as e:
            return False, str(e)
        if not commits:
            return False, "that repo has no commits yet: commit and push first"
        return True, f"{ref.full_name} looks good"
