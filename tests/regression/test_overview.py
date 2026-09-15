"""Dashboard overview endpoints: counts, key coverage, session states."""
from fastapi.testclient import TestClient

from sim.adapters.auth.secretbox import encrypt_secret, secret_from_config
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.ports.users import UserRecord


def _fake(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake",
                 db_path=str(tmp_path / "f.db"), sandbox_root=str(tmp_path / "b"),
                 bootstrap_admin_email="admin@t.local")
    return cfg, TestClient(build_app(cfg))


def _h(uid, role, email=""):
    return {"Authorization": f"Bearer fake:{uid}:{role}:{email or uid + '@t.local'}"}


def test_ov01_admin_and_instructor_overview(tmp_path):
    cfg, c = _fake(tmp_path)
    admin, inst = _h("a1", "admin", "admin@t.local"), _h("i1", "instructor")
    c.get("/api/auth/me", headers=admin)
    co = c.post("/api/admin/cohorts", json={"name": "C1"}, headers=admin).json()["id"]
    uids = []
    for i in range(3):
        u = c.post("/api/admin/users", json={"email": f"c{i}@t.local", "role": "challenger"},
                   headers=admin).json()
        uids.append(u["uid"])
        c.post(f"/api/admin/cohorts/{co}/members", json={"uid": u["uid"]}, headers=admin)
    # one challenger (who never chats here, so no real Groq call) stored a key
    users = c.app.state.auth.users
    rec = users.get(uids[2])
    users.upsert(UserRecord(uid=rec.uid, email=rec.email, role=rec.role,
                            groq_key_enc=encrypt_secret(secret_from_config(cfg), "gsk_x")))

    r = c.post(f"/api/instructor/cohorts/{co}/sessions",
               json={"scenario": "iv_parking"}, headers=inst).json()
    sids = {x["uid"]: x["session_id"] for x in r["created"]}
    # first challenger starts and submits, second only starts
    c.post(f"/api/session/{sids[uids[0]]}/start", headers=_h(uids[0], "challenger", "c0@t.local"))
    c.put(f"/api/session/{sids[uids[0]]}/files/write",
          json={"path": "DESIGN.md", "text": "# d\nqueue\n"},
          headers=_h(uids[0], "challenger", "c0@t.local"))
    assert c.post(f"/api/session/{sids[uids[0]]}/submit-doc",
                  headers=_h(uids[0], "challenger", "c0@t.local")).json()["ok"]
    c.post(f"/api/session/{sids[uids[1]]}/start", headers=_h(uids[1], "challenger", "c1@t.local"))

    ov = c.get("/api/instructor/overview", headers=inst).json()
    t = ov["stats"]["totals"]
    assert (t["sessions"], t["submitted"], t["active"], t["not_started"]) == (3, 1, 1, 1)
    assert t["active_24h"] == 2
    sc = ov["stats"]["by_scenario"][0]
    assert sc["key"] == "iv_parking" and sc["submitted"] == 1 and sc["title"]
    assert ov["stats"]["activity"][-1]["active"] == 2
    states = {r["session_id"]: r["state"] for r in ov["recent"]}
    assert states[sids[uids[0]]] == "submitted" and states[sids[uids[2]]] == "not_started"
    assert all(r["assignee"].endswith("@t.local") for r in ov["recent"])

    rows = c.get("/api/instructor/sessions", headers=inst).json()["sessions"]
    assert {r["state"] for r in rows} == {"submitted", "active", "not_started"}

    ad = c.get("/api/admin/overview", headers=admin).json()
    assert ad["users"]["by_role"]["challenger"] == 3 and ad["users"]["with_groq"] == 1
    assert ad["users"]["with_github"] == 0
    assert ad["cohorts"]["count"] == 1 and ad["cohorts"]["members"] == 3
    assert ad["scenarios"]["by_track"]["interview"] == 20
    assert ad["sessions"]["totals"]["submitted"] == 1
    assert ad["auth"]["auth_mode"] == "fake"

    detail = c.get(f"/api/instructor/cohorts/{co}", headers=inst).json()
    flags = {m["uid"]: m["has_groq_key"] for m in detail["members"]}
    assert flags[uids[2]] is True and flags[uids[1]] is False
    assert c.get("/api/admin/overview", headers=inst).status_code == 403
