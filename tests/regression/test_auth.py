"""Auth modes: password stays open; fake mode scopes by role."""
from fastapi.testclient import TestClient

from sim.app.composition_root import build_app
from sim.app.config import Config


def _pw(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "p.db"),
                 sandbox_root=str(tmp_path / "b"))
    return TestClient(build_app(cfg)), {"X-Instructor-Token": "$T0mV13w"}


def _fake(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake",
                 db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"),
                 bootstrap_admin_email="admin@t.local")
    return TestClient(build_app(cfg))


def _h(uid, role, email=""):
    em = email or f"{uid}@t.local"
    return {"Authorization": f"Bearer fake:{uid}:{role}:{em}"}


def test_smk20_password_mode_default(tmp_path):
    c, h = _pw(tmp_path)
    assert c.get("/api/auth/config").json()["auth_mode"] == "password"
    assert c.get("/api/instructor/sessions").status_code == 401
    assert c.get("/api/instructor/sessions", headers=h).status_code == 200


def test_auth01_assign_and_challenger_list(tmp_path):
    c = _fake(tmp_path)
    inst, ch, stranger = _h("i1", "instructor"), _h("c1", "challenger"), _h("c2", "challenger")
    created = c.post("/api/instructor/sessions",
                     json={"scenario": "churn_dashboard", "level": "mid",
                           "assignee_uid": "c1"}, headers=inst).json()
    sid = created["session_id"]
    mine = c.get("/api/me/sessions", headers=ch).json()["sessions"]
    assert any(s["session_id"] == sid for s in mine)
    other = c.get("/api/me/sessions", headers=stranger).json()["sessions"]
    assert not any(s["session_id"] == sid for s in other)
    assert c.get(f"/api/session/{sid}/transcript", headers=ch).status_code == 200
    assert c.get(f"/api/session/{sid}/transcript", headers=stranger).status_code == 403


def test_auth02_challenger_blocked_from_instructor(tmp_path):
    c = _fake(tmp_path)
    ch = _h("c1", "challenger")
    assert c.get("/api/instructor/sessions", headers=ch).status_code == 403
    assert c.get("/api/scenarios", headers=ch).status_code == 403
    assert c.get("/api/admin/users", headers=ch).status_code == 403


def test_auth03_admin_users_crud_and_last_admin(tmp_path):
    c = _fake(tmp_path)
    admin = _h("a1", "admin", "admin@t.local")
    # first login bootstraps admin@t.local as admin (count_role 0)
    r = c.get("/api/auth/me", headers=admin)
    assert r.status_code == 200 and r.json()["role"] == "admin"
    created = c.post("/api/admin/users",
                     json={"email": "x@t.local", "role": "challenger"},
                     headers=admin).json()
    assert created["ok"]
    users = c.get("/api/admin/users", headers=admin).json()["users"]
    assert any(u["email"] == "x@t.local" for u in users)
    uid = created["uid"]
    assert c.patch(f"/api/admin/users/{uid}",
                   json={"role": "instructor"}, headers=admin).json()["ok"]
    # cannot delete last admin
    assert c.delete("/api/admin/users/a1", headers=admin).status_code == 400


def test_auth04_grade_and_export_scoped(tmp_path):
    c = _fake(tmp_path)
    inst, ch = _h("i1", "instructor"), _h("c1", "challenger")
    sid = c.post("/api/instructor/sessions",
                 json={"scenario": "iv_unique_id", "level": "junior",
                       "assignee_uid": "c1"}, headers=inst).json()["session_id"]
    assert c.post(f"/api/session/{sid}/grade", json={}, headers=ch).status_code == 200
    assert c.post(f"/api/session/{sid}/grade", json={},
                  headers=_h("c9", "challenger")).status_code == 403
    exp = c.get(f"/api/instructor/session/{sid}/export.md", headers=inst)
    assert exp.status_code == 200 and "Assessment audit" in exp.text


def test_auth05_admin_cascade_delete(tmp_path):
    c = _fake(tmp_path)
    inst, admin = _h("i1", "instructor"), _h("a1", "admin", "admin@t.local")
    c.get("/api/auth/me", headers=admin)
    sid = c.post("/api/instructor/sessions",
                 json={"scenario": "churn_dashboard", "level": "mid"},
                 headers=inst).json()["session_id"]
    c.post(f"/api/session/{sid}/start", headers=inst)
    assert c.delete(f"/api/admin/sessions/{sid}", headers=admin).json()["ok"]
    listed = c.get("/api/admin/sessions", headers=admin).json()["sessions"]
    assert not any(s["session_id"] == sid for s in listed)


def test_auth06_pages_exist(tmp_path):
    c, _ = _pw(tmp_path)
    for path in ("/login", "/challenger", "/admin", "/instructor"):
        assert c.get(path).status_code == 200
