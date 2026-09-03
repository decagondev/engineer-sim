from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Optional, Protocol

from sim.adapters.environment.local_folder import LocalFolderEnvironment
from sim.core.ports.environment import (
    SandboxError, SandboxHandle, SandboxUnavailable,
)


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    """Small injectable seam so the Docker lifecycle is testable without a daemon."""

    def run(self, args: list[str], timeout: float = 60) -> RunResult: ...


class SubprocessRunner:
    def run(self, args: list[str], timeout: float = 60) -> RunResult:
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as e:
            raise SandboxUnavailable(
                "docker CLI not found — install Docker Desktop and make sure it's running"
            ) from e
        except subprocess.SubprocessError as e:
            raise SandboxError(f"docker command failed: {e}") from e
        return RunResult(r.returncode, r.stdout.strip(), r.stderr.strip())


class DockerEnvironment:
    """Per-session Docker container. The scenario's starter repo is seeded into a
    host workdir (git-baselined) and bind-mounted into the container at
    /workspace, so the tester can drive it with their own agent on the host while
    code RUNS isolated in the container. The git build record reads the host
    workdir unchanged.

    Isolation: the container is a real process/filesystem boundary for execution.
    It is not a full security sandbox against a determined adversary; it's the
    realistic dev environment the flight-sim analogy calls for.
    """

    def __init__(self, root: str, starter_template: str = "",
                 image: str = "python:3.11-slim", runner: CommandRunner | None = None,
                 memory: str = "2g", cpus: str = "2", pids: str = "512",
                 name_prefix: str = "sim-") -> None:
        self._fs = LocalFolderEnvironment(root, starter_template, git_baseline=True)
        self._image = image
        self._runner = runner or SubprocessRunner()
        self._memory, self._cpus, self._pids = memory, cpus, pids
        self._prefix = name_prefix

    def _name(self, session_id: str) -> str:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self._prefix + (safe or "session")

    def _hint(self, name: str) -> str:
        return f"docker exec -it {name} bash   # your files are in /workspace"

    def provision(self, session_id: str) -> SandboxHandle:
        host = self._fs.provision(session_id)          # seed + git baseline on host
        name = self._name(session_id)

        if self._exists(name):
            self._runner.run(["docker", "start", name])  # ensure running
            return SandboxHandle(session_id, host.workdir, created=False,
                                 container=name, connect_hint=self._hint(name))

        res = self._runner.run([
            "docker", "run", "-d", "--name", name,
            "-v", f"{host.workdir}:/workspace", "-w", "/workspace",
            "--memory", self._memory, "--cpus", self._cpus,
            "--pids-limit", self._pids,
            self._image, "sleep", "infinity",
        ], timeout=180)
        if res.returncode != 0:
            # host dir exists but the container didn't come up — surface clearly
            raise SandboxError(f"docker run failed: {res.stderr or res.stdout}")
        return SandboxHandle(session_id, host.workdir, created=True,
                             container=name, connect_hint=self._hint(name))

    def handle(self, session_id: str) -> Optional[SandboxHandle]:
        host = self._fs.handle(session_id)
        if host is None:
            return None
        name = self._name(session_id)
        exists = self._exists(name)
        return SandboxHandle(session_id, host.workdir, created=False,
                             container=(name if exists else None),
                             connect_hint=(self._hint(name) if exists else None))

    def teardown(self, session_id: str) -> None:
        self._runner.run(["docker", "rm", "-f", self._name(session_id)])
        self._fs.teardown(session_id)

    def _exists(self, name: str) -> bool:
        res = self._runner.run([
            "docker", "ps", "-a", "--filter", f"name=^{name}$",
            "--format", "{{.Names}}",
        ])
        return name in res.stdout.split()
