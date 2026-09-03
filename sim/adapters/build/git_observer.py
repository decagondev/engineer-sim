from __future__ import annotations

import subprocess


class GitBuildObserver:
    """BuildRecordSource backed by a local git repo. Reads the commit timeline
    and the net diff so the grader can see HOW the engineer built, not just the
    final result. Read-only; never writes to the repo.
    """

    def __init__(self, max_diff_chars: int = 8000) -> None:
        self._max = max_diff_chars

    def summary(self, repo_path: str) -> str:
        log = self._git(repo_path, ["log", "--pretty=format:%h %ad %s",
                                    "--date=short"])
        diff = self._git(repo_path, ["diff", "--stat", "HEAD"])
        first = self._first_commit(repo_path)
        net = self._git(repo_path, ["diff", f"{first}", "HEAD"]) if first else ""
        parts = [f"COMMITS:\n{log or '(none)'}",
                 f"CURRENT DIFFSTAT:\n{diff or '(clean)'}"]
        if net:
            parts.append("NET DIFF (truncated):\n" + net[: self._max])
        return "\n\n".join(parts)

    def _first_commit(self, repo_path: str) -> str:
        out = self._git(repo_path, ["rev-list", "--max-parents=0", "HEAD"])
        return out.splitlines()[0] if out else ""

    @staticmethod
    def _git(repo_path: str, args: list[str]) -> str:
        try:
            res = subprocess.run(
                ["git", "-C", repo_path, *args],
                capture_output=True, text=True, timeout=15,
            )
            return res.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            return ""
