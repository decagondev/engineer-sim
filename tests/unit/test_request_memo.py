"""A1: the user's directory record is read at most once per request. The key
resolvers and the write checks share the record the auth gate fetched."""
from fastapi.testclient import TestClient

from sim.adapters.llm import request_context as rc
from sim.adapters.persistence.sqlite_users import InMemoryUserDirectory
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.ports.users import UserRecord
from tests.unit import fake_firestore
from tests.unit.fake_firestore import FakeFirestore


class CountingUsers(InMemoryUserDirectory):
    def __init__(self):
        super().__init__()
        self.reads = 0

    def get(self, uid):
        self.reads += 1
        return super().get(uid)


def test_memo01_current_user_reads_once_per_uid():
    users = CountingUsers()
    users.upsert(UserRecord("c1", "c@t.local", "challenger"))
    rc.set_current_uid("c1")
    assert rc.current_user(users).uid == "c1"
    assert rc.current_user(users).uid == "c1"
    assert users.reads == 1
    rc.set_current_uid("c1")                       # a new request forgets the memo
    rc.current_user(users)
    assert users.reads == 2
    rc.set_current_uid("nobody")
    assert rc.current_user(users) is None and rc.current_user(users) is None
    assert users.reads == 3, "a missing record is memoised too"
    rc.prime_user(UserRecord("c1", "c@t.local", "challenger", name="Primed"))
    rc.set_current_uid("c1"); rc.prime_user(users.get("c1")); users.reads = 0
    assert rc.current_user(users) is not None and users.reads == 0, "primed record needs no read"
    rc.set_current_uid("")
    assert rc.current_user(users) is None and rc.current_user(None) is None


def _users_reads(monkeypatch):
    db = FakeFirestore()
    counts = {"users": 0}
    orig_get = fake_firestore._Doc.get

    def get(self):
        if self._path and self._path[0] == "users":
            counts["users"] += 1
        return orig_get(self)

    monkeypatch.setattr(fake_firestore._Doc, "get", get)
    monkeypatch.setattr("sim.adapters.persistence.firestore_client.make_firestore_client",
                        lambda cfg: db)
    return db, counts


def test_memo02_one_directory_read_per_request(tmp_path, monkeypatch):
    db, counts = _users_reads(monkeypatch)
    cfg = Config(llm_provider="fake", auth_mode="fake", persistence="firestore",
                 firebase_project_id="x", sandbox_root=str(tmp_path / "b"),
                 bootstrap_admin_email="admin@t.local", work_mode="hosted",
                 github_oauth_client_id="cid")
    c = TestClient(build_app(cfg))
    admin = {"Authorization": "Bearer fake:a1:admin:admin@t.local"}
    c.get("/api/auth/me", headers=admin)
    ch = c.post("/api/admin/users", json={"email": "c@t.local", "role": "challenger"}, headers=admin).json()
    chal = {"Authorization": f"Bearer fake:{ch['uid']}:challenger:c@t.local"}
    sid = c.post("/api/instructor/sessions", json={"scenario": "churn_dashboard", "assignee_email": "c@t.local"},
                 headers=admin).json()["session_id"]
    c.get("/api/auth/me", headers=chal)          # warm: login freshness upsert happens here

    counts["users"] = 0
    assert c.get("/api/auth/me", headers=chal).status_code == 200
    assert counts["users"] <= 1, f"/api/auth/me read the directory {counts['users']} times"

    # the scenario payload asks both hosts' can_write and the workflow: still one read
    counts["users"] = 0
    r = c.get(f"/api/session/{sid}/scenario", headers=chal)
    assert r.status_code == 200 and counts["users"] <= 1, counts

    # a Files listing on a linked repo resolves the GitHub token and the write check
    counts["users"] = 0
    c.get(f"/api/session/{sid}/files/list", headers=chal)
    assert counts["users"] <= 1, counts
