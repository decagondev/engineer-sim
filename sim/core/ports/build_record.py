from __future__ import annotations

from typing import Protocol


class BuildRecordSource(Protocol):
    """Port: how the engineer built (commits + final diff) as the build record.
    Kept behind a port so the tester's real repo, a fixture repo, or a future
    remote source are all substitutable.
    """

    def summary(self, repo_path: str) -> str: ...
