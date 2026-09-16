"""Admin site settings: sign-up gate, grader-calibrated override, announcement,
and that instructor edits never wipe the admin fields."""
from fastapi.testclient import TestClient

from sim.adapters.persistence.firestore_store import FirestoreSettingsStore
from sim.adapters.persistence.sqlite_settings import SqliteSettingsStore
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.ports.settings import InstructorSettings
from tests.unit.fake_firestore import FakeFirestore


def _h(uid, role, email=""):
    return {"Authorization": f"Bearer fake:{uid}:{role}:{email or uid + '@t.local'}"}


def test_ss01_stores_keep_the_new_fields(tmp_path):
    for st in (SqliteSettingsStore(str(tmp_path / "s.db")), FirestoreSettingsStore(FakeFirestore())):
        assert st.get_instructor().allow_signup is True
        assert st.get_instructor().grader_calibrated is None
        st.set_instructor(InstructorSettings(True, "staff", allow_signup=False,
                                             grader_calibrated=True, announcement="Hi"))
        s = st.get_instructor()
        assert (s.default_level, s.allow_signup, s.grader_calibrated, s.announcement) == \
            ("staff", False, True, "Hi")
        st.set_instructor(InstructorSettings(True, "staff", grader_calibrated=False))
        assert st.get_instructor().grader_calibrated is False


def test_ss02_admin_settings_roundtrip_and_effects(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake", db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"), bootstrap_admin_email="admin@t.local")
    c = TestClient(build_app(cfg))
    admin = _h("a1", "admin", "admin@t.local")
    c.get("/api/auth/me", headers=admin)

    s = c.get("/api/admin/settings", headers=admin).json()
    assert s["allow_signup"] is True and s["grader_calibrated"] is None
    assert s["deployment"]["auth_mode"] == "fake" and "groq_key_set" in s["deployment"]
    assert c.get("/api/auth/config").json()["allow_signup"] is True

    # an unknown challenger can sign in while sign-up is allowed
    assert c.get("/api/auth/me", headers=_h("new1", "challenger")).status_code == 200

    r = c.put("/api/admin/settings", json={"allow_signup": False, "announcement": "  Thursday 2pm  ",
                                           "grader_calibrated": True, "default_level": "staff"},
              headers=admin)
    assert r.status_code == 200 and r.json()["allow_signup"] is False
    assert c.get("/api/auth/config").json()["allow_signup"] is False
    assert c.get("/api/site/announcement").json()["announcement"] == "Thursday 2pm"

    # unknown emails are refused; known ones and the bootstrap admin still work
    r = c.get("/api/auth/me", headers=_h("new2", "challenger"))
    assert r.status_code == 403 and "Ask your instructor" in r.json()["error"]
    assert c.get("/api/auth/me", headers=_h("new1", "challenger")).status_code == 200
    assert c.get("/api/auth/me", headers=admin).status_code == 200
    created = c.post("/api/admin/users", json={"email": "x@t.local", "role": "challenger"},
                     headers=admin).json()
    assert c.get("/api/auth/me", headers=_h(created["uid"], "challenger", "x@t.local")).status_code == 200

    # calibrated override removes the caveat from grades
    sid = "s-cal"
    c.post(f"/api/session/{sid}/start", headers=admin)
    g = c.post(f"/api/session/{sid}/grade", json={}, headers=admin).json()
    assert g["calibrated"] is True and "caveat" not in g

    # an instructor saving their default level keeps the admin fields
    inst = _h("i1", "instructor")
    c.post("/api/admin/users", json={"email": "i1@t.local", "role": "instructor"}, headers=admin)
    c.post("/api/instructor/settings", json={"default_level": "mid"}, headers=inst)
    s = c.get("/api/admin/settings", headers=admin).json()
    assert s["default_level"] == "mid" and s["allow_signup"] is False and s["grader_calibrated"] is True

    assert c.put("/api/admin/settings", json={"default_level": "nope"}, headers=admin).status_code == 400
    assert c.post("/api/admin/cache/clear", headers=admin).json()["ok"]
