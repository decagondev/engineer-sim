"""Environment (sandbox) spike tests. Local-folder adapter + build-record loop."""
import subprocess

import pytest

from sim.adapters.build.git_observer import GitBuildObserver
from sim.adapters.environment.local_folder import LocalFolderEnvironment


@pytest.fixture
def starter(tmp_path):
    src = tmp_path / "starter"
    (src / "data").mkdir(parents=True)
    (src / "README.md").write_text("the ticket\n")
    (src / "data" / "usage.csv").write_text("account_id,x\nacct_1,1\n")
    return src


# ENV-01: provision seeds the starter + is idempotent
def test_env01_provision_seeds_and_is_idempotent(tmp_path, starter):
    env = LocalFolderEnvironment(root=str(tmp_path / "boxes"),
                                 starter_template=str(starter))
    h1 = env.provision("s-abc")
    assert h1.created is True
    from pathlib import Path
    assert (Path(h1.workdir) / "README.md").exists()
    assert (Path(h1.workdir) / "data" / "usage.csv").exists()
    h2 = env.provision("s-abc")          # again -> not re-created
    assert h2.created is False and h2.workdir == h1.workdir


# ENV-02: teardown removes it
def test_env02_teardown(tmp_path, starter):
    env = LocalFolderEnvironment(root=str(tmp_path / "boxes"),
                                 starter_template=str(starter))
    env.provision("s-x")
    assert env.handle("s-x") is not None
    env.teardown("s-x")
    assert env.handle("s-x") is None


# ENV-03: no starter template still provisions an (empty) workdir
def test_env03_no_template(tmp_path):
    env = LocalFolderEnvironment(root=str(tmp_path / "boxes"), starter_template="")
    h = env.provision("s-empty")
    from pathlib import Path
    assert Path(h.workdir).is_dir()


# ENV-04: the build record captures tester work against the starter baseline
def test_env04_build_record_diffs_against_baseline(tmp_path, starter):
    env = LocalFolderEnvironment(root=str(tmp_path / "boxes"),
                                 starter_template=str(starter))
    h = env.provision("s-build")
    from pathlib import Path
    # simulate the tester doing work + committing
    (Path(h.workdir) / "solution.py").write_text("print('at-risk list')\n")
    for args in (["add", "-A"], ["commit", "-q", "-m", "ship at-risk list"]):
        subprocess.run(["git", "-C", h.workdir, *args], check=True,
                       capture_output=True, text=True)
    summary = GitBuildObserver().summary(h.workdir)
    assert "scenario starter (baseline)" in summary   # baseline commit present
    assert "ship at-risk list" in summary             # tester's commit present
    assert "solution.py" in summary                   # their file in the diff
