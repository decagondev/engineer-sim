"""Files browser (WorkspaceReader) tests — including path-safety."""
import pytest

from sim.adapters.workspace.local_reader import LocalWorkspaceReader


@pytest.fixture
def wd(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "README.md").write_text("hello world\n")
    (tmp_path / "data" / "x.csv").write_text("a,b\n1,2\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref\n")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02\xff")
    return str(tmp_path)


def test_files01_list_hides_git_and_sorts_dirs_first(wd):
    names = [e.name for e in LocalWorkspaceReader().list_dir(wd)]
    assert ".git" not in names
    assert names[0] == "data"                 # dirs first
    assert "README.md" in names


def test_files02_read_text(wd):
    c = LocalWorkspaceReader().read_file(wd, "README.md")
    assert c.text == "hello world\n" and c.note == ""


def test_files03_binary_flagged(wd):
    c = LocalWorkspaceReader().read_file(wd, "blob.bin")
    assert c.text is None and "binary" in c.note


def test_files04_too_large(wd):
    import pathlib
    pathlib.Path(wd, "big.txt").write_text("x" * 100)
    c = LocalWorkspaceReader(max_bytes=10).read_file(wd, "big.txt")
    assert c.text is None and "too large" in c.note


def test_files05_path_traversal_blocked(wd):
    r = LocalWorkspaceReader()
    with pytest.raises(ValueError):
        r.read_file(wd, "../secret")
    with pytest.raises(ValueError):
        r.list_dir(wd, "../..")
