"""Docker environment adapter — lifecycle tested via a fake runner (no daemon)."""
import pytest

from sim.adapters.environment.docker import (
    DockerEnvironment, RunResult, SubprocessRunner,
)
from sim.core.ports.environment import SandboxError, SandboxUnavailable


class FakeDocker:
    """Records docker invocations and simulates container state."""

    def __init__(self, fail_run: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.existing: set[str] = set()
        self.fail_run = fail_run

    def run(self, args, timeout=60) -> RunResult:
        self.calls.append(args)
        if args[:2] == ["docker", "ps"]:
            name = None
            for i, a in enumerate(args):
                if a == "--filter" and args[i + 1].startswith("name="):
                    name = args[i + 1][len("name="):].strip("^$")
            return RunResult(0, name if name in self.existing else "", "")
        if args[:2] == ["docker", "run"]:
            if self.fail_run:
                return RunResult(1, "", "port already allocated")
            self.existing.add(args[args.index("--name") + 1])
            return RunResult(0, "container-id", "")
        if args[:2] == ["docker", "start"]:
            return RunResult(0, "", "")
        if args[:3] == ["docker", "rm", "-f"]:
            self.existing.discard(args[-1])
            return RunResult(0, "", "")
        return RunResult(0, "", "")

    def cmd_strings(self):
        return [" ".join(c) for c in self.calls]


@pytest.fixture
def starter(tmp_path):
    src = tmp_path / "starter"
    src.mkdir()
    (src / "README.md").write_text("the ticket\n")
    return src


# DOCK-01: provision runs a container, bind-mounts, seeds host, returns hint
def test_dock01_provision_creates_container(tmp_path, starter):
    fake = FakeDocker()
    env = DockerEnvironment(root=str(tmp_path / "boxes"),
                            starter_template=str(starter),
                            image="python:3.11-slim", runner=fake)
    h = env.provision("s1")
    from pathlib import Path
    assert h.created is True
    assert h.container == "sim-s1"
    assert "docker exec -it sim-s1" in h.connect_hint
    assert (Path(h.workdir) / "README.md").exists()      # host seeded
    run_cmd = next(c for c in fake.cmd_strings() if c.startswith("docker run"))
    assert ":/workspace" in run_cmd and "python:3.11-slim" in run_cmd
    assert "--memory 2g" in run_cmd and "sleep infinity" in run_cmd


# DOCK-02: second provision reuses the container (start, no second run)
def test_dock02_idempotent(tmp_path, starter):
    fake = FakeDocker()
    env = DockerEnvironment(root=str(tmp_path / "boxes"),
                            starter_template=str(starter), runner=fake)
    env.provision("s1")
    h2 = env.provision("s1")
    assert h2.created is False
    runs = [c for c in fake.cmd_strings() if c.startswith("docker run")]
    starts = [c for c in fake.cmd_strings() if c.startswith("docker start")]
    assert len(runs) == 1 and len(starts) >= 1


# DOCK-03: teardown removes container and host dir
def test_dock03_teardown(tmp_path, starter):
    fake = FakeDocker()
    env = DockerEnvironment(root=str(tmp_path / "boxes"),
                            starter_template=str(starter), runner=fake)
    env.provision("s1")
    assert env.handle("s1").container == "sim-s1"
    env.teardown("s1")
    assert env.handle("s1") is None                       # host dir gone
    assert any(c.startswith("docker rm -f sim-s1") for c in fake.cmd_strings())


# DOCK-04: a failed docker run surfaces a clear SandboxError
def test_dock04_run_failure_raises(tmp_path, starter):
    env = DockerEnvironment(root=str(tmp_path / "boxes"),
                            starter_template=str(starter), runner=FakeDocker(fail_run=True))
    with pytest.raises(SandboxError, match="docker run failed"):
        env.provision("s1")


# DOCK-05: a missing docker binary surfaces SandboxUnavailable (real subprocess)
def test_dock05_missing_docker_binary():
    runner = SubprocessRunner()
    with pytest.raises(SandboxUnavailable):
        runner.run(["docker-does-not-exist-xyz", "ps"])
