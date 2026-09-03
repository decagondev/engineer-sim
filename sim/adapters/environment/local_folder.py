from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from sim.core.ports.environment import SandboxHandle


class LocalFolderEnvironment:
    """SPIKE adapter: each session gets a folder seeded from the scenario's
    starter template, git-initialised so the build record can diff the tester's
    work against the starter baseline.

    NOT a security boundary — it's a working directory, not a sandbox. Do not run
    untrusted code in it. The Docker adapter (same Environment port) is the
    hardening path; see docs/SPIKE_ENVIRONMENT.md.
    """

    def __init__(self, root: str, starter_template: str = "",
                 git_baseline: bool = True) -> None:
        self._root = Path(root)
        self._starter = Path(starter_template) if starter_template else None
        self._git_baseline = git_baseline

    def _dir(self, session_id: str) -> Path:
        # keep session ids filesystem-safe
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self._root / (safe or "session")

    def provision(self, session_id: str) -> SandboxHandle:
        d = self._dir(session_id)
        if d.exists():
            return SandboxHandle(session_id, str(d.resolve()), created=False)
        d.mkdir(parents=True, exist_ok=True)
        if self._starter and self._starter.exists():
            shutil.copytree(self._starter, d, dirs_exist_ok=True)
        if self._git_baseline:
            self._baseline(d)
        return SandboxHandle(session_id, str(d.resolve()), created=True)

    def handle(self, session_id: str) -> Optional[SandboxHandle]:
        d = self._dir(session_id)
        if d.exists():
            return SandboxHandle(session_id, str(d.resolve()), created=False)
        return None

    def teardown(self, session_id: str) -> None:
        shutil.rmtree(self._dir(session_id), ignore_errors=True)

    @staticmethod
    def _baseline(d: Path) -> None:
        try:
            run = lambda *a: subprocess.run(["git", "-C", str(d), *a],
                                            capture_output=True, text=True, timeout=20)
            run("init", "-q")
            run("config", "user.email", "sim@example.com")
            run("config", "user.name", "flight-sim")
            run("add", "-A")
            run("commit", "-q", "-m", "scenario starter (baseline)")
        except (subprocess.SubprocessError, FileNotFoundError):
            pass  # git absent -> build record just won't have a baseline
