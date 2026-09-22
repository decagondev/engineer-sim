"""Port for a hosted git forge (GitHub, a GitLab instance). The build observer
and the repo workspace only ever see these normalised shapes, so adding a host
is one adapter and no route changes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, Sequence


class RepoHostError(RuntimeError):
    """The repo couldn't be read (not found, private, rate-limited, unreachable)."""


@dataclass(frozen=True)
class RepoRef:
    host: str            # "github.com", "labs.gauntletai.com"
    owner: str           # user, org, or a nested GitLab namespace "group/sub"
    repo: str
    url: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass(frozen=True)
class RepoInfo:
    default_branch: str = "main"
    full_name: str = ""
    is_fork: bool = False
    parent_full_name: str = ""
    parent_default_branch: str = ""
    web_url: str = ""


@dataclass(frozen=True)
class Commit:
    sha: str
    date: str = ""
    message: str = ""


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str = "modified"     # added | modified | removed | renamed
    additions: int = 0
    deletions: int = 0
    patch: str = ""


@dataclass(frozen=True)
class TreeNode:
    path: str
    is_dir: bool = False
    size: int = -1               # -1 when the host's tree listing carries no size
    sha: str = ""


@dataclass(frozen=True)
class WriteResult:
    blob_sha: str = ""
    commit_sha: str = ""


class RepoHost(Protocol):
    """One forge. Every method raises RepoHostError for the expected failures
    and ValueError when a URL does not belong to this host."""

    @property
    def label(self) -> str: ...            # "GitHub", "GitLab"

    def parse(self, url: str) -> RepoRef: ...

    def info(self, ref: RepoRef) -> RepoInfo: ...

    def head(self, ref: RepoRef) -> tuple[str, str]: ...     # (default branch, tip sha)

    def commits(self, ref: RepoRef, n: int = 30) -> Sequence[Commit]: ...

    def changes(self, ref: RepoRef) -> Sequence[ChangedFile]: ...   # net diff vs the fork parent, [] if not a fork

    def tree(self, ref: RepoRef, sha: str) -> Sequence[TreeNode]: ...

    def file_text(self, ref: RepoRef, path: str, at: str = "",
                  max_bytes: int = 200_000) -> Optional[str]: ...

    def put_file(self, ref: RepoRef, path: str, text: str, message: str,
                 sha: str = "", branch: str = "") -> WriteResult: ...
