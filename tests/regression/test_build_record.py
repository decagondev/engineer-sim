"""Git build-record adapter test — uses a throwaway git repo fixture."""
import subprocess

import pytest

from sim.adapters.build.git_observer import GitBuildObserver


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Tester")
    (tmp_path / "app.py").write_text("print('v1')\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "first cut")
    (tmp_path / "app.py").write_text("print('v2')\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "iterate")
    return tmp_path


def test_reg09_build_record_captures_commits_and_diff(repo):
    summary = GitBuildObserver().summary(str(repo))
    assert "first cut" in summary and "iterate" in summary
    assert "app.py" in summary


def test_reg09_build_record_safe_on_non_repo(tmp_path):
    # never raises, just returns an empty-ish record
    out = GitBuildObserver().summary(str(tmp_path))
    assert isinstance(out, str)
