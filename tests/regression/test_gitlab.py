"""A self-hosted GitLab instance as a second forge: the RepoHost port, the
host router, the device flow with refresh tokens, and the connect routes."""
import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from sim.adapters.auth.gitlab_oauth import GitLabDeviceFlow
from sim.adapters.auth.gitlab_tokens import pack_token, unpack, user_token_resolver
from sim.adapters.auth.secretbox import decrypt_secret, encrypt_secret
from sim.adapters.build.github_api import GitHubApi
from sim.adapters.build.github_host import GitHubHost
from sim.adapters.build.github_observer import GitHostBuildObserver
from sim.adapters.build.gitlab_api import GitLabApi, GitLabHost, GitLabReadError
from sim.adapters.build.host_router import HostRouter
from sim.adapters.llm.request_context import current_uid, set_current_uid
from sim.adapters.persistence.firestore_store import FirestoreUserDirectory
from sim.adapters.persistence.sqlite_users import InMemoryUserDirectory, SqliteUserDirectory
from sim.adapters.workspace.github_files import RepoWorkspaceFiles
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.ports.oauth import OAuthError, OAuthToken
from sim.core.ports.users import UserRecord
from sim.core.ports.workspace import ReadOnlyWorkspace
from tests.unit.fake_firestore import FakeFirestore

LAB = "https://labs.gauntletai.com"
PROJ = "/projects/bryan%2Fagentforge"        # URL-encoded bryan/agentforge


class FakeGitLab:
    """A recorded slice of GitLab's v4 API for the fork bryan/agentforge (id 2049)
    of starter/agentforge (id 7)."""

    def __init__(self):
        self.sha = "1111111aaaa"
        self.files = {"README.md": "# starter\n", "DESIGN.md": "# Design\n\nqueue then workers\n",
                      "src/app.py": "print(1)\n", "src/pkg/__init__.py": ""}
        self.calls = []
        self.writes = []

    def push(self, path, text):
        self.files[path] = text
        self.sha = "2222222bbbb"

    def __call__(self, path, method="GET", body=None):
        self.calls.append((method, path))
        if method in ("PUT", "POST") and path.startswith("/projects/2049/repository/files/"):
            rel = path[len("/projects/2049/repository/files/"):].replace("%2F", "/")
            exists = rel in self.files
            if method == "POST" and exists or method == "PUT" and not exists:
                raise GitLabReadError("GitLab returned 400")
            self.writes.append((method, rel, body))
            self.files[rel] = body["content"]
            self.sha = "3333333cccc"
            return {"file_path": rel, "branch": body["branch"]}
        if path == PROJ:
            return {"id": 2049, "default_branch": "main", "path_with_namespace": "bryan/agentforge",
                    "visibility": "public", "web_url": f"{LAB}/bryan/agentforge",
                    "forked_from_project": {"id": 7, "path_with_namespace": "starter/agentforge",
                                            "default_branch": "main"}}
        if path == "/projects/2049/repository/branches/main":
            return {"name": "main", "commit": {"id": self.sha}}
        if path.startswith("/projects/2049/repository/commits"):
            return [{"id": self.sha, "short_id": self.sha[:8], "title": "work",
                     "message": "work\n\nmore", "committed_date": "2026-09-01T10:00:00Z"}]
        if path.startswith("/projects/2049/repository/compare"):
            assert "from_project_id=7" in path and "from=main" in path
            return {"diffs": [{"old_path": "src/app.py", "new_path": "src/app.py",
                               "diff": "@@ -1 +1,2 @@\n print(1)\n+print(2)\n",
                               "new_file": False, "renamed_file": False, "deleted_file": False},
                              {"old_path": "NEW.md", "new_path": "NEW.md", "diff": "@@ -0,0 +1 @@\n+new\n",
                               "new_file": True, "renamed_file": False, "deleted_file": False}]}
        if path.startswith("/projects/2049/repository/tree"):
            assert f"ref={self.sha}" in path
            if "page=1" not in path:
                return []
            tree = [{"id": "blob-" + p, "name": p.rsplit("/", 1)[-1], "type": "blob", "path": p}
                    for p in self.files]
            tree += [{"id": "t1", "name": "src", "type": "tree", "path": "src"},
                     {"id": "t2", "name": "pkg", "type": "tree", "path": "src/pkg"}]
            return tree
        if path.startswith("/projects/2049/repository/files/"):
            rel = path[len("/projects/2049/repository/files/"):].split("?")[0].replace("%2F", "/")
            if rel in self.files:
                t = self.files[rel]
                return {"file_path": rel, "size": len(t), "encoding": "base64",
                        "content": base64.b64encode(t.encode()).decode(), "blob_id": "blob-" + rel}
        raise GitLabReadError("project not found")


def _host(gl=None):
    gl = gl or FakeGitLab()
    return gl, GitLabHost(LAB, api=GitLabApi(LAB, fetch=gl))


def test_gl01_parse_urls():
    _, h = _host()
    r = h.parse("https://labs.gauntletai.com/bryan/agentforge")
    assert (r.host, r.owner, r.repo) == ("labs.gauntletai.com", "bryan", "agentforge")
    assert h.parse("https://labs.gauntletai.com/group/sub/proj.git").owner == "group/sub"
    assert h.parse("https://labs.gauntletai.com/bryan/agentforge/-/tree/main").repo == "agentforge"
    assert h.parse("git@labs.gauntletai.com:bryan/agentforge.git").full_name == "bryan/agentforge"
    assert h.owns("https://github.com/o/r") is False
    with pytest.raises(ValueError):
        h.parse("https://github.com/o/r")
    with pytest.raises(ValueError):
        h.parse("https://labs.gauntletai.com/onlygroup")


def test_gl02_host_reads_and_writes():
    gl, h = _host()
    ref = h.parse(f"{LAB}/bryan/agentforge")
    info = h.info(ref)
    assert info.is_fork and info.parent_full_name == "starter/agentforge" and info.default_branch == "main"
    assert h.head(ref) == ("main", "1111111aaaa")
    c = h.commits(ref, 5)[0]
    assert c.sha == "1111111aaaa" and c.message.startswith("work") and c.date.startswith("2026")
    nodes = {n.path: n for n in h.tree(ref, "1111111aaaa")}
    assert nodes["src"].is_dir and not nodes["src/app.py"].is_dir and nodes["src/app.py"].size == -1
    assert nodes["src/app.py"].sha == "blob-src/app.py"
    assert h.file_text(ref, "DESIGN.md", at="1111111aaaa").startswith("# Design")
    assert h.file_text(ref, "missing.md", at="main") is None
    ch = {f.path: f for f in h.changes(ref)}
    assert ch["src/app.py"].additions == 1 and ch["src/app.py"].deletions == 0
    assert ch["NEW.md"].status == "added"
    out = h.put_file(ref, "src/app.py", "print(2)\n", "msg", sha="blob-src/app.py", branch="main")
    assert gl.writes[-1][0] == "PUT" and gl.writes[-1][2]["commit_message"] == "msg"
    assert out.commit_sha == "3333333cccc"
    h.put_file(ref, "docs/new.md", "# n\n", "msg", sha="", branch="main")
    assert gl.writes[-1][0] == "POST", "a new file is created, not updated"
    # the project id is cached: one lookup, not one per call
    assert sum(1 for m, p in gl.calls if p == PROJ) <= 6


def test_gl03_router_workspace_and_observer():
    gl = FakeGitLab()
    gitlab = GitLabHost(LAB, api=GitLabApi(LAB, fetch=gl))
    gh_calls = []

    def gh_fetch(path, method="GET", body=None):
        gh_calls.append(path)
        raise GitLabReadError("nope")
    router = HostRouter([GitHubHost(api=GitHubApi(token="", fetch=gh_fetch)), gitlab],
                        can_write={"labs.gauntletai.com": lambda: True, "github.com": lambda: False})
    files = RepoWorkspaceFiles(host=router, can_write=router.can_write)
    root = f"{LAB}/bryan/agentforge"
    assert [(e.name, e.is_dir) for e in files.list_dir(root)] == [
        ("src", True), ("DESIGN.md", False), ("README.md", False)]
    assert [e.name for e in files.list_dir(root, "src")] == ["pkg", "app.py"]
    assert files.read_file(root, "DESIGN.md").text.startswith("# Design")
    with pytest.raises(FileNotFoundError):
        files.read_file(root, "nope.md")
    assert not gh_calls, "GitHub was never asked about a GitLab URL"
    tree_calls = len([1 for m, p in gl.calls if "/repository/tree" in p])
    files.list_dir(root, "src")
    assert len([1 for m, p in gl.calls if "/repository/tree" in p]) == tree_calls, "tree is cached"

    # writes: the GitLab host may, GitHub may not
    files.write_file(root, "src/app.py", "print(2)\n")
    assert gl.writes[-1][1] == "src/app.py" and files.read_file(root, "src/app.py").text == "print(2)\n"
    files.write_file(root, "docs/new.md", "# new\n")
    assert "new.md" in [e.name for e in files.list_dir(root, "docs")]
    with pytest.raises(ReadOnlyWorkspace) as ei:
        files.write_file("https://github.com/o/r", "x.md", "x")
    assert "GitHub" in str(ei.value)
    assert "diff --git a/NEW.md" in files.diff(root)
    gl.push("LATER.md", "x")
    assert files.refresh(root) == "2222222"
    assert "LATER.md" in [e.name for e in files.list_dir(root)]

    obs = GitHostBuildObserver(host=router)
    ok, msg = obs.validate(root)
    assert ok and "bryan/agentforge" in msg
    ok, msg = obs.validate("https://bitbucket.org/x/y")
    assert not ok and "github.com or labs.gauntletai.com" in msg
    summary = obs.summary(root)
    assert "on GitLab" in summary and "NET CHANGES vs starter (starter/agentforge)" in summary
    assert "DESIGN.md:\n# Design" in summary and "2222222" in summary
    assert obs.read_file(root, "DESIGN.md").startswith("# Design")


class FakeGitLabPosts:
    """/oauth/authorize_device + /oauth/token: approve() makes the next poll succeed."""

    def __init__(self):
        self.approved = False
        self.calls = []
        self.refreshes = 0

    def approve(self):
        self.approved = True

    def __call__(self, url, form):
        self.calls.append((url, form))
        if url.endswith("/oauth/authorize_device"):
            return {"device_code": "dc9", "user_code": "WXYZ-9876", "verification_uri": f"{LAB}/oauth/device",
                    "verification_uri_complete": f"{LAB}/oauth/device?user_code=WXYZ-9876",
                    "interval": 5, "expires_in": 300}
        if form.get("grant_type") == "refresh_token":
            self.refreshes += 1
            assert form["refresh_token"] == "rt1"
            return {"access_token": "glat_fresh", "refresh_token": "rt2", "expires_in": 7200, "scope": "api"}
        if self.approved:
            return {"access_token": "glat_oauth", "refresh_token": "rt1", "expires_in": 7200,
                    "scope": "api", "token_type": "Bearer"}
        return {"error": "authorization_pending"}


def test_gl04_device_flow_broker_and_refresh():
    posts = FakeGitLabPosts()
    broker = GitLabDeviceFlow(LAB, "app-id-1", post=posts)
    assert broker.configured
    code = broker.start("api")
    assert code.user_code == "WXYZ-9876" and code.verification_uri.endswith("user_code=WXYZ-9876")
    assert posts.calls[0][0] == f"{LAB}/oauth/authorize_device" and posts.calls[0][1]["scope"] == "api"
    assert broker.poll(code.device_code) is None
    posts.approve()
    tok = broker.poll(code.device_code)
    assert tok.access_token == "glat_oauth" and tok.refresh_token == "rt1" and tok.expires_in == 7200
    fresh = broker.refresh("rt1")
    assert fresh.access_token == "glat_fresh"
    assert not GitLabDeviceFlow("", "x").configured and not GitLabDeviceFlow(LAB, "").configured
    with pytest.raises(OAuthError):
        GitLabDeviceFlow(LAB, "").start()
    with pytest.raises(OAuthError):
        GitLabDeviceFlow(LAB, "c", post=lambda u, f: {"error": "access_denied"}).poll("x")


def test_gl05_token_bundle_and_resolver_refreshes_before_expiry():
    tok = OAuthToken("glat_a", scope="api", refresh_token="rt1", expires_in=7200)
    raw = pack_token(tok, now=1000.0)
    b = unpack(raw)
    assert b == {"access_token": "glat_a", "refresh_token": "rt1", "expires_at": 8200.0}
    assert unpack("glpat-plain") == {"access_token": "glpat-plain", "refresh_token": "", "expires_at": 0}

    posts = FakeGitLabPosts()
    broker = GitLabDeviceFlow(LAB, "app", post=posts)
    for users in (InMemoryUserDirectory(), FirestoreUserDirectory(FakeFirestore())):
        users.upsert(UserRecord("c1", "c@t.local", "challenger", gitlab_scope="api",
                                gitlab_token_enc=encrypt_secret("s", raw)))
        users.upsert(UserRecord("c2", "d@t.local", "challenger",
                                gitlab_token_enc=encrypt_secret("s", "glpat-mine")))
        clock = {"t": 2000.0}
        resolve = user_token_resolver(users, "s", "glpat-server", broker=broker, now=lambda: clock["t"])
        set_current_uid("c1"); assert resolve() == "glat_a"
        set_current_uid("c2"); assert resolve() == "glpat-mine"
        set_current_uid("nobody"); assert resolve() == "glpat-server"
        # close to expiry: refreshed once, new bundle stored, then served from the store
        clock["t"] = 8150.0
        before = posts.refreshes
        set_current_uid("c1"); assert resolve() == "glat_fresh"
        assert posts.refreshes == before + 1
        stored = unpack(decrypt_secret("s", users.get("c1").gitlab_token_enc))
        assert stored["refresh_token"] == "rt2" and stored["expires_at"] == 8150.0 + 7200
        assert resolve() == "glat_fresh" and posts.refreshes == before + 1
    current_uid.set("")


def test_gl06_user_fields_persist_in_all_stores(tmp_path):
    for users in (InMemoryUserDirectory(), SqliteUserDirectory(str(tmp_path / "u.db")),
                  FirestoreUserDirectory(FakeFirestore())):
        users.upsert(UserRecord("u1", "u@t.local", "challenger", gitlab_token_enc="enc", gitlab_scope="api"))
        rec = users.get("u1")
        assert rec.gitlab_token_enc == "enc" and rec.gitlab_scope == "api"
        users.upsert(UserRecord("u1", "u@t.local", "instructor"))
        assert users.get("u1").gitlab_token_enc == "" and users.get("u1").role == "instructor"
    # an old sqlite file without the columns is migrated in place
    import sqlite3
    old = tmp_path / "old.db"
    con = sqlite3.connect(str(old))
    con.execute("CREATE TABLE users (uid TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, role TEXT NOT NULL, "
                "disabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, last_login TEXT NOT NULL DEFAULT '')")
    con.execute("INSERT INTO users VALUES ('a','a@t.local','admin',0,'t','')")
    con.commit(); con.close()
    users = SqliteUserDirectory(str(old))
    assert users.get("a").gitlab_scope == ""
    users.upsert(UserRecord("a", "a@t.local", "admin", gitlab_scope="read_api"))
    assert users.get("a").gitlab_scope == "read_api"


def _h(uid, role, email=""):
    return {"Authorization": f"Bearer fake:{uid}:{role}:{email or uid + '@t.local'}"}


def test_gl07_connect_flow_and_editable_gitlab_repo(tmp_path, monkeypatch):
    cfg = Config(llm_provider="fake", auth_mode="fake", db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"), bootstrap_admin_email="admin@t.local",
                 work_mode="hosted", gitlab_url=LAB, gitlab_oauth_client_id="app-id-1")
    c = TestClient(build_app(cfg))
    posts = FakeGitLabPosts()
    c.app.state.gitlab_oauth = GitLabDeviceFlow(LAB, "app-id-1", post=posts)
    # swap the network client under the wired GitLab host; the router, the
    # observer, the workspace and the token resolver stay exactly as built
    gl = FakeGitLab()
    router = c.app.state.repo_files.host
    gitlab = router.host_for(f"{LAB}/x/y")
    assert gitlab is not None and gitlab.host == "labs.gauntletai.com"
    gitlab._api._fetch = gl

    admin = _h("a1", "admin", "admin@t.local")
    c.get("/api/auth/me", headers=admin)
    ch = c.post("/api/admin/users", json={"email": "c@t.local", "role": "challenger"}, headers=admin).json()
    chal = _h(ch["uid"], "challenger", "c@t.local")
    sid = c.post("/api/instructor/sessions", json={"scenario": "churn_dashboard", "assignee_email": "c@t.local"},
                 headers=admin).json()["session_id"]
    r = c.post(f"/api/session/{sid}/workspace/repo", json={"url": f"{LAB}/bryan/agentforge"}, headers=chal).json()
    assert r["ok"] and "bryan/agentforge" in r["message"], r
    assert c.post(f"/api/session/{sid}/workspace/repo", json={"url": "https://bitbucket.org/x/y"},
                  headers=chal).status_code == 400

    me = c.get("/api/auth/me", headers=chal).json()
    assert me["gitlab_oauth"] is True and me["gitlab_connected"] is False
    assert me["gitlab_host"] == "labs.gauntletai.com" and me["github_oauth"] is False
    sc = c.get(f"/api/session/{sid}/scenario", headers=chal).json()
    assert sc["workflow"]["kind"] == "repo" and sc["workflow"]["editable"] is False
    names = [e["name"] for e in c.get(f"/api/session/{sid}/files/list", headers=chal).json()["entries"]]
    assert "DESIGN.md" in names, "browsing a public GitLab project needs no sign-in"
    assert c.put(f"/api/session/{sid}/files/write", json={"path": "src/app.py", "text": "x"}, headers=chal).status_code == 405

    # connect: device code, poll, token bundle stored encrypted with its refresh token
    r = c.post("/api/me/gitlab/connect", headers=chal).json()
    assert r["user_code"] == "WXYZ-9876" and r["verification_uri"].startswith(LAB)
    assert c.get("/api/me/gitlab/connect", headers=chal).json()["status"] == "pending"
    posts.approve()
    s = c.get("/api/me/gitlab/connect", headers=chal).json()
    assert s["status"] == "connected" and s["scope"] == "api"
    rec = c.app.state.auth.users.get(ch["uid"])
    assert rec.gitlab_scope == "api" and "glat_oauth" not in rec.gitlab_token_enc
    from sim.adapters.auth.secretbox import secret_from_config
    bundle = unpack(decrypt_secret(secret_from_config(cfg), rec.gitlab_token_enc))
    assert bundle["refresh_token"] == "rt1" and bundle["expires_at"] > time.time()
    assert c.get("/api/auth/me", headers=chal).json()["gitlab_connected"] is True

    # the repo workflow is editable for this user now, and a save is a commit
    sc = c.get(f"/api/session/{sid}/scenario", headers=chal).json()
    assert sc["workflow"]["editable"] is True and sc["workflow"]["writes_to_repo"] is True
    r = c.put(f"/api/session/{sid}/files/write", json={"path": "src/app.py", "text": "print(2)\n"}, headers=chal)
    assert r.status_code == 200, r.text
    assert gl.writes[-1][:2] == ("PUT", "src/app.py") and gl.writes[-1][2]["branch"] == "main"
    assert c.get(f"/api/session/{sid}/files/read?path=src/app.py", headers=chal).json()["text"] == "print(2)\n"
    # ...and the request carried the user's token (the resolver reads the bundle)
    resolve = gitlab._api._resolve
    set_current_uid(ch["uid"]); assert resolve() == "glat_oauth"; current_uid.set("")

    # submit: the build record comes from GitLab
    r = c.post(f"/api/session/{sid}/submit-repo", json={}, headers=chal)
    assert r.status_code == 200, r.text
    # a pasted personal token is accepted (validated against the instance) but never unlocks writes
    monkeypatch.setattr("sim.adapters.build.gitlab_api.validate_token", lambda base, t: None)
    other = c.post("/api/admin/users", json={"email": "d@t.local", "role": "challenger"}, headers=admin).json()
    oh = _h(other["uid"], "challenger", "d@t.local")
    r = c.patch("/api/me", json={"gitlab_token": "glpat-mine"}, headers=oh).json()
    assert r["has_gitlab_token"] is True and r["gitlab_connected"] is False
    assert c.get("/api/auth/me", headers=oh).json()["has_gitlab_token"] is True
    assert c.put(f"/api/session/{sid}/files/write", json={"path": "src/app.py", "text": "y"}, headers=oh).status_code in (403, 405)
    assert c.patch("/api/me", json={"clear_gitlab_token": True}, headers=oh).json()["has_gitlab_token"] is False

    # disconnect: read-only again; deployment panel and health say GitLab is on
    assert c.delete("/api/me/gitlab/connect", headers=chal).json()["ok"]
    assert c.get(f"/api/session/{sid}/scenario", headers=chal).json()["workflow"]["editable"] is False
    dep = c.get("/api/admin/settings", headers=admin).json()["deployment"]
    assert dep["gitlab_url"] == LAB and dep["gitlab_oauth_set"] is True and dep["gitlab_token_set"] is False
    h = c.get("/health").json()
    assert h["gitlab_oauth"] is True and h["gitlab_url"] == LAB


def test_gl08_without_gitlab_url_nothing_changes(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake", db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"))
    c = TestClient(build_app(cfg))
    h = _h("c1", "challenger")
    me = c.get("/api/auth/me", headers=h).json()
    assert me["gitlab_oauth"] is False and me["gitlab_host"] == ""
    assert c.post("/api/me/gitlab/connect", headers=h).status_code == 501
    assert c.get("/api/me/gitlab/connect", headers=h).json()["status"] == "idle"
    assert c.patch("/api/me", json={"gitlab_token": "x"}, headers=h).status_code == 400
    assert [x.host for x in c.app.state.repo_files.host.hosts] == ["github.com"]
    assert c.get("/health").json()["gitlab_oauth"] is False
