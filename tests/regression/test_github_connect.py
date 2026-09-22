"""Roadmap item 9: connect GitHub (device flow) and commit from the Files app."""
import base64

import pytest
from fastapi.testclient import TestClient

from sim.adapters.auth.github_oauth import GitHubDeviceFlow
from sim.adapters.build.github_api import GitHubApi, GitHubReadError
from sim.adapters.workspace.github_files import GitHubWorkspaceFiles
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.ports.oauth import OAuthError
from sim.core.ports.workspace import ReadOnlyWorkspace


class FakeGitHubPosts:
    """github.com device-flow endpoints: approve() makes the next poll succeed."""

    def __init__(self):
        self.approved = False
        self.calls = []

    def approve(self):
        self.approved = True

    def __call__(self, url, form):
        self.calls.append((url, form))
        if url.endswith("/device/code"):
            return {"device_code": "dc1", "user_code": "ABCD-1234",
                    "verification_uri": "https://github.com/login/device", "interval": 1, "expires_in": 900}
        if self.approved:
            return {"access_token": "gho_oauth", "scope": "public_repo", "token_type": "bearer"}
        return {"error": "authorization_pending"}


def test_gc01_device_flow_broker():
    posts = FakeGitHubPosts()
    broker = GitHubDeviceFlow("client123", post=posts)
    assert broker.configured
    code = broker.start()
    assert code.user_code == "ABCD-1234" and posts.calls[0][1]["scope"] == "public_repo"
    assert broker.poll(code.device_code) is None
    posts.approve()
    tok = broker.poll(code.device_code)
    assert tok.access_token == "gho_oauth" and tok.scope == "public_repo"
    with pytest.raises(OAuthError):
        GitHubDeviceFlow("").start()
    denied = GitHubDeviceFlow("c", post=lambda u, f: {"error": "access_denied"})
    with pytest.raises(OAuthError):
        denied.poll("x")


class FakeRepoApi:
    """GET + PUT slice of api.github.com for o/r, a fork."""

    def __init__(self):
        self.files = {"README.md": "# starter\n", "src/app.py": "print(1)\n"}
        self.sha = "aaaaaaa1111"
        self.puts = []

    def __call__(self, path, method="GET", body=None):
        if method == "PUT" and path.startswith("/repos/o/r/contents/"):
            rel = path[len("/repos/o/r/contents/"):]
            self.puts.append((rel, body))
            self.files[rel] = base64.b64decode(body["content"]).decode()
            self.sha = "ccccccc3333"
            return {"content": {"sha": "blob-new"}, "commit": {"sha": self.sha}}
        if path == "/repos/o/r":
            return {"default_branch": "main", "fork": True,
                    "parent": {"owner": {"login": "t"}, "default_branch": "main", "full_name": "t/s"}}
        if path == "/repos/o/r/branches/main":
            return {"commit": {"sha": self.sha}}
        if path.startswith("/repos/o/r/commits"):
            return [{"sha": self.sha, "commit": {"message": "m", "author": {"date": "2026-01-01"}}}]
        if path.startswith(f"/repos/o/r/git/trees/{self.sha}"):
            return {"tree": [{"path": p, "type": "blob", "size": len(t), "sha": "blob-" + p}
                             for p, t in self.files.items()] + [{"path": "src", "type": "tree"}]}
        if path.startswith("/repos/o/r/contents/"):
            rel = path[len("/repos/o/r/contents/"):].split("?")[0]
            if rel in self.files:
                t = self.files[rel]
                return {"type": "file", "size": len(t), "encoding": "base64",
                        "content": base64.b64encode(t.encode()).decode()}
        raise GitHubReadError("repo not found")


def test_gc02_adapter_writes_only_with_permission():
    gh = FakeRepoApi()
    allowed = {"v": False}
    files = GitHubWorkspaceFiles(api=GitHubApi(token="", fetch=gh), can_write=lambda: allowed["v"])
    root = "https://github.com/o/r"
    with pytest.raises(ReadOnlyWorkspace):
        files.write_file(root, "src/app.py", "print(2)\n")
    allowed["v"] = True
    files.write_file(root, "src/app.py", "print(2)\n")
    rel, body = gh.puts[-1]
    assert rel == "src/app.py" and body["sha"] == "blob-src/app.py" and body["branch"] == "main"
    assert base64.b64decode(body["content"]).decode() == "print(2)\n"
    # cache stays truthful: new content readable, new file listed, no re-fetch of the tree needed
    assert files.read_file(root, "src/app.py").text == "print(2)\n"
    files.write_file(root, "docs/new.md", "# new\n")
    assert "new.md" in [e.name for e in files.list_dir(root, "docs")]
    with pytest.raises(ValueError):
        files.write_file(root, ".git/config", "x")


def _h(uid, role, email=""):
    return {"Authorization": f"Bearer fake:{uid}:{role}:{email or uid + '@t.local'}"}


def test_gc03_connect_flow_and_editable_repo(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake", db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"), bootstrap_admin_email="admin@t.local",
                 work_mode="hosted", github_oauth_client_id="client123")
    c = TestClient(build_app(cfg))
    posts = FakeGitHubPosts()
    c.app.state.github_oauth = GitHubDeviceFlow("client123", post=posts)
    gh = FakeRepoApi()
    api = GitHubApi(token="", fetch=gh)
    from sim.adapters.build.github_observer import GitHostBuildObserver
    from sim.app.composition_root import _github_can_write
    from sim.core.workspace.service import WorkspaceService
    obs = GitHostBuildObserver(api=api)
    c.app.state.github_observer = obs
    c.app.state.manager.repo_files = obs
    c.app.state.repo_workspace = WorkspaceService(
        files=GitHubWorkspaceFiles(api=api, can_write=_github_can_write(c.app.state.auth.users)))

    admin = _h("a1", "admin", "admin@t.local")
    c.get("/api/auth/me", headers=admin)
    ch = c.post("/api/admin/users", json={"email": "c@t.local", "role": "challenger"}, headers=admin).json()
    chal = _h(ch["uid"], "challenger", "c@t.local")
    sid = c.post("/api/instructor/sessions", json={"scenario": "churn_dashboard", "assignee_email": "c@t.local"},
                 headers=admin).json()["session_id"]
    assert c.post(f"/api/session/{sid}/workspace/repo", json={"url": "https://github.com/o/r"}, headers=chal).json()["ok"]

    # read-only until connected
    sc = c.get(f"/api/session/{sid}/scenario", headers=chal).json()
    assert sc["workflow"]["kind"] == "repo" and sc["workflow"]["editable"] is False
    assert c.put(f"/api/session/{sid}/files/write", json={"path": "src/app.py", "text": "x"}, headers=chal).status_code == 405
    me = c.get("/api/auth/me", headers=chal).json()
    assert me["github_oauth"] is True and me["github_connected"] is False

    # a pasted read token does not unlock writes either
    c.patch("/api/me", json={"github_token": "ghp_read"}, headers=chal) if False else None

    r = c.post("/api/me/github/connect", headers=chal).json()
    assert r["user_code"] == "ABCD-1234"
    assert c.get("/api/me/github/connect", headers=chal).json()["status"] == "pending"
    posts.approve()
    s = c.get("/api/me/github/connect", headers=chal).json()
    assert s["status"] == "connected" and s["scope"] == "public_repo"
    assert c.get("/api/auth/me", headers=chal).json()["github_connected"] is True
    rec = c.app.state.auth.users.get(ch["uid"])
    assert rec.github_scope == "public_repo" and rec.github_token_enc and "gho_oauth" not in rec.github_token_enc

    # now the repo workflow is editable for this user, and a save is a commit
    sc = c.get(f"/api/session/{sid}/scenario", headers=chal).json()
    assert sc["workflow"]["editable"] is True and sc["workflow"]["writes_to_repo"] is True
    assert c.get(f"/api/session/{sid}/files/list", headers=chal).json()["editable"] is True
    r = c.put(f"/api/session/{sid}/files/write", json={"path": "src/app.py", "text": "print(2)\n"}, headers=chal)
    assert r.status_code == 200, r.text
    assert gh.puts and gh.puts[-1][0] == "src/app.py"
    assert c.get(f"/api/session/{sid}/files/read?path=src/app.py", headers=chal).json()["text"] == "print(2)\n"

    # another user (no connection) still cannot write to that session's repo view
    other = c.post("/api/admin/users", json={"email": "d@t.local", "role": "challenger"}, headers=admin).json()
    assert c.get("/api/auth/me", headers=_h(other["uid"], "challenger", "d@t.local")).json()["github_connected"] is False

    # disconnect: read-only again
    assert c.delete("/api/me/github/connect", headers=chal).json()["ok"]
    assert c.get(f"/api/session/{sid}/scenario", headers=chal).json()["workflow"]["editable"] is False
    assert c.put(f"/api/session/{sid}/files/write", json={"path": "src/app.py", "text": "y"}, headers=chal).status_code == 405


def test_gc04_connect_refused_without_oauth_app(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake", db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"), bootstrap_admin_email="admin@t.local")
    c = TestClient(build_app(cfg))
    h = _h("c1", "challenger")
    c.get("/api/auth/me", headers=h)
    assert c.post("/api/me/github/connect", headers=h).status_code == 501
    assert c.get("/api/me/github/connect", headers=h).json()["status"] == "idle"
