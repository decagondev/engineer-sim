"""Wave 4 of docs/WORKSPACE-PLAN.md: browse a linked GitHub repo, read-only."""
import base64

import pytest
from fastapi.testclient import TestClient

from sim.adapters.build.github_api import GitHubApi, GitHubReadError
from sim.adapters.workspace.github_files import GitHubWorkspaceFiles
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.ports.workspace import ReadOnlyWorkspace

DESIGN = "# Design\n\nqueue then workers\n"


class FakeGitHub:
    """A recorded slice of the GitHub REST API for owner o / repo r."""

    def __init__(self):
        self.sha = "aaaaaaa1111"
        self.files = {"README.md": "# starter\n", "DESIGN.md": DESIGN,
                      "src/app.py": "print(1)\n", "src/pkg/__init__.py": ""}
        self.calls = []

    def push(self, path, text):
        self.files[path] = text
        self.sha = "bbbbbbb2222"

    def __call__(self, path):
        self.calls.append(path)
        if path == "/repos/o/r":
            return {"default_branch": "main", "fork": True,
                    "parent": {"owner": {"login": "teacher"}, "default_branch": "main",
                               "full_name": "teacher/starter"}}
        if path.startswith("/repos/o/r/compare/"):
            return {"files": [{"filename": "src/app.py", "status": "modified", "additions": 1,
                               "deletions": 0, "patch": "@@ -1 +1,2 @@\n print(1)\n+print(2)"}]}
        if path == "/repos/o/r/branches/main":
            return {"commit": {"sha": self.sha}}
        if path.startswith("/repos/o/r/commits"):
            return [{"sha": self.sha, "commit": {"message": "work",
                                                 "author": {"date": "2026-01-01"}}}]
        if path.startswith(f"/repos/o/r/git/trees/{self.sha}"):
            tree = [{"path": p, "type": "blob", "size": len(t)} for p, t in self.files.items()]
            tree.append({"path": "src", "type": "tree"})
            return {"tree": tree}
        if path.startswith("/repos/o/r/contents/"):
            rel = path[len("/repos/o/r/contents/"):].split("?")[0]
            if rel in self.files:
                t = self.files[rel]
                return {"type": "file", "size": len(t), "encoding": "base64",
                        "content": base64.b64encode(t.encode()).decode()}
        raise GitHubReadError("repo not found")


def test_rw01_adapter_lists_reads_and_refreshes():
    gh = FakeGitHub()
    files = GitHubWorkspaceFiles(api=GitHubApi(token="", fetch=gh))
    root = "https://github.com/o/r"
    top = files.list_dir(root)
    assert [(e.name, e.is_dir) for e in top] == [
        ("src", True), ("DESIGN.md", False), ("README.md", False)]
    assert [e.name for e in files.list_dir(root, "src")] == ["pkg", "app.py"]
    assert files.read_file(root, "DESIGN.md").text == DESIGN
    with pytest.raises(FileNotFoundError):
        files.read_file(root, "nope.md")
    with pytest.raises(IsADirectoryError):
        files.read_file(root, "src")
    with pytest.raises(ValueError):
        files.read_file(root, "../etc/passwd")
    with pytest.raises(ReadOnlyWorkspace):
        files.write_file(root, "DESIGN.md", "x")

    tree_calls = len([c for c in gh.calls if "/git/trees/" in c])
    files.list_dir(root, "src")
    assert len([c for c in gh.calls if "/git/trees/" in c]) == tree_calls, "tree is cached"

    gh.push("NEW.md", "new\n")
    assert files.refresh(root) == "bbbbbbb"
    assert "NEW.md" in [e.name for e in files.list_dir(root)]


def _hosted(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"),
                 sandbox_root=str(tmp_path / "b"), work_mode="hosted")
    c = TestClient(build_app(cfg))
    gh = FakeGitHub()
    api = GitHubApi(token="", fetch=gh)
    from sim.adapters.build.github_observer import GitHostBuildObserver
    from sim.core.workspace.service import WorkspaceService
    obs = GitHostBuildObserver(api=api)
    c.app.state.github_observer = obs
    c.app.state.manager.repo_files = obs
    c.app.state.repo_workspace = WorkspaceService(files=GitHubWorkspaceFiles(api=api))
    return c, gh


def test_rw02_link_then_browse_then_grade(tmp_path):
    c, gh = _hosted(tmp_path)
    sid = "s-link"
    c.post(f"/api/session/{sid}/start")
    assert c.get(f"/api/session/{sid}/workspace/repo").json()["url"] == ""
    assert c.get(f"/api/session/{sid}/files/list").status_code == 409

    r = c.post(f"/api/session/{sid}/workspace/repo", json={"url": "https://github.com/o/r"})
    assert r.status_code == 200 and r.json()["ok"], r.text
    assert c.get(f"/api/session/{sid}/workspace/repo").json()["url"] == "https://github.com/o/r"
    texts = [m["content"] for m in c.get(f"/api/session/{sid}/transcript").json()]
    assert any("Linked repo: https://github.com/o/r" in t for t in texts)

    listing = c.get(f"/api/session/{sid}/files/list").json()
    assert listing["editable"] is False
    assert "DESIGN.md" in [e["name"] for e in listing["entries"]]
    assert c.get(f"/api/session/{sid}/files/read?path=src/app.py").json()["text"] == "print(1)\n"
    assert c.put(f"/api/session/{sid}/files/write",
                 json={"path": "a.md", "text": "x"}).status_code == 405

    gh.push("src/new.py", "pass\n")
    assert c.post(f"/api/session/{sid}/files/refresh").json()["revision"] == "bbbbbbb"
    assert "new.py" in [e["name"] for e in
                        c.get(f"/api/session/{sid}/files/list?path=src").json()["entries"]]

    # submit uses the linked repo when no URL is given; grader reads the repo
    r = c.post(f"/api/session/{sid}/submit-repo", json={})
    assert r.status_code == 200 and r.json()["ok"], r.text
    c.post(f"/api/session/{sid}/grade", json={})
    llm = c.app.state.grader._llm
    calls = getattr(llm, "calls", None) or llm._fallback.calls
    prompt = calls[-1]["messages"][0].content
    assert "REPO: o/r" in prompt and "queue then workers" in prompt


def test_rw03_link_refused_for_doc_tracks(tmp_path):
    c, _ = _hosted(tmp_path)
    sid = "s-doc-link"
    c.post(f"/api/instructor/session/{sid}/scenario",
           json={"scenario": "iv_parking"}, headers={"X-Instructor-Token": "$T0mV13w"})
    r = c.post(f"/api/session/{sid}/workspace/repo", json={"url": "https://github.com/o/r"})
    assert r.status_code == 405
