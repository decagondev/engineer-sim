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


def test_auth07_admin_lists_legacy_recorded_sessions(tmp_path):
    """Classroom runs live in the message store; admin must see them even
    when they were never written to the assignment registry."""
    c = _fake(tmp_path)
    admin = _h("a1", "admin", "admin@t.local")
    c.get("/api/auth/me", headers=admin)
    sid = "s-legacy01"
    assert c.post(f"/api/session/{sid}/start", headers=admin).status_code == 200
    listed = c.get("/api/admin/sessions", headers=admin).json()["sessions"]
    assert any(s["session_id"] == sid for s in listed)
    row = next(s for s in listed if s["session_id"] == sid)
    assert row["count"] >= 1


def test_auth08_admin_name_and_cohorts(tmp_path):
    c = _fake(tmp_path)
    admin = _h("a1", "admin", "admin@t.local")
    c.get("/api/auth/me", headers=admin)
    created = c.post("/api/admin/users",
                     json={"email": "pat@t.local", "role": "challenger",
                           "name": "Pat"}, headers=admin).json()
    uid = created["uid"]
    assert created["name"] == "Pat"
    assert c.patch(f"/api/admin/users/{uid}",
                   json={"name": "Patricia"}, headers=admin).json()["name"] == "Patricia"
    users = c.get("/api/admin/users?sort=name&direction=asc", headers=admin).json()["users"]
    assert users[0]["name"] in ("Patricia", "admin") or any(u["name"] == "Patricia" for u in users)
    names = [u["name"] or u["email"] for u in users]
    assert names == sorted(names, key=str.lower)

    co = c.post("/api/admin/cohorts",
                json={"name": "April intake", "notes": "week 1"},
                headers=admin).json()
    assert co["ok"] and co["name"] == "April intake"
    cid = co["id"]
    assert c.post(f"/api/admin/cohorts/{cid}/members",
                  json={"uid": uid}, headers=admin).json()["ok"]
    detail = c.get(f"/api/admin/cohorts/{cid}", headers=admin).json()
    assert any(m["uid"] == uid and m["name"] == "Patricia" for m in detail["members"])
    onboard = c.post(f"/api/admin/cohorts/{cid}/onboard",
                     json={"email": "new@t.local", "name": "Nia",
                           "role": "challenger"}, headers=admin).json()
    assert onboard["ok"] and onboard["name"] == "Nia"
    listed = c.get("/api/admin/cohorts?sort=members&direction=desc",
                   headers=admin).json()["cohorts"]
    assert listed[0]["id"] == cid and listed[0]["member_count"] == 2
    assert c.delete(f"/api/admin/cohorts/{cid}/members/{uid}",
                    headers=admin).json()["ok"]
    assert len(c.get(f"/api/admin/cohorts/{cid}", headers=admin).json()["members"]) == 1


def test_auth09_challenger_settings_byok(tmp_path, monkeypatch):
    monkeypatch.setattr("sim.adapters.llm.groq_client.validate_groq_key", lambda k: None)
    c = _fake(tmp_path)
    ch = _h("c1", "challenger")
    c.get("/api/auth/me", headers=ch)
    me = c.get("/api/auth/me", headers=ch).json()
    assert me["has_groq_key"] is False
    assert "groq_key" not in me and "groq_key_enc" not in me
    assert c.patch("/api/me", json={"name": "Casey"}, headers=ch).json()["name"] == "Casey"
    saved = c.patch("/api/me", json={"groq_key": "gsk_secret_test"}, headers=ch)
    assert saved.status_code == 200 and saved.json()["has_groq_key"] is True
    assert "gsk_secret_test" not in str(saved.json())
    me = c.get("/api/auth/me", headers=ch).json()
    assert me["name"] == "Casey" and me["has_groq_key"] is True
    assert "gsk_" not in str(me)
    admin = _h("a1", "admin", "admin@t.local")
    c.get("/api/auth/me", headers=admin)
    users = c.get("/api/admin/users", headers=admin).json()["users"]
    casey = next(u for u in users if u["email"] == "c1@t.local")
    assert casey["has_groq_key"] is True
    assert "groq_key_enc" not in casey and "groq_key" not in casey
    assert c.patch("/api/admin/users/c1", json={"name": "Casey Lee"},
                   headers=admin).json()["name"] == "Casey Lee"
    assert c.get("/api/auth/me", headers=ch).json()["has_groq_key"] is True
    assert c.patch("/api/me", json={"clear_groq_key": True},
                   headers=ch).json()["has_groq_key"] is False
    monkeypatch.setattr(
        "sim.adapters.llm.groq_client.validate_groq_key",
        lambda k: (_ for _ in ()).throw(RuntimeError("Groq rejected that key.")))
    bad = c.patch("/api/me", json={"groq_key": "nope"}, headers=ch)
    assert bad.status_code == 400
    assert c.patch("/api/me", json={"name": "X"}).status_code == 401


def test_auth09_password_mode_blocks_me_patch(tmp_path):
    c, _h = _pw(tmp_path)
    assert c.patch("/api/me", json={"name": "X"}).status_code == 400


def test_auth10_admin_user_full_crud(tmp_path):
    c = _fake(tmp_path)
    admin = _h("a1", "admin", "admin@t.local")
    ch = _h("c1", "challenger")
    c.get("/api/auth/me", headers=admin)
    created = c.post("/api/admin/users",
                     json={"email": "sam@t.local", "name": "Sam",
                           "role": "challenger", "password": "secret1"},
                     headers=admin).json()
    uid = created["uid"]
    co = c.post("/api/admin/cohorts", json={"name": "Spring"},
                headers=admin).json()
    cid = co["id"]
    patched = c.patch(f"/api/admin/users/{uid}",
                      json={"name": "Samantha", "email": "samantha@t.local",
                            "role": "instructor", "cohort_ids": [cid],
                            "password": "secret2"},
                      headers=admin).json()
    assert patched["ok"] and patched["name"] == "Samantha"
    assert patched["email"] == "samantha@t.local"
    assert patched["role"] == "instructor"
    assert patched["cohort_ids"] == [cid]
    assert patched["password_set"] is True
    assert "password" not in patched and "secret2" not in str(patched)
    listed = c.get("/api/admin/users", headers=admin).json()["users"]
    sam = next(u for u in listed if u["uid"] == uid)
    assert sam["name"] == "Samantha" and cid in sam["cohort_ids"]
    assert "password" not in sam
    cleared = c.patch(f"/api/admin/users/{uid}",
                      json={"cohort_ids": []}, headers=admin).json()
    assert cleared["cohort_ids"] == []
    reset = c.patch(f"/api/admin/users/{uid}",
                    json={"send_reset": True}, headers=admin).json()
    assert reset["ok"] and reset["reset_sent"] is True
    assert c.patch(f"/api/admin/users/{uid}",
                   json={"name": "Nope"}, headers=ch).status_code == 403
    taken = c.patch(f"/api/admin/users/{uid}",
                    json={"email": "admin@t.local"}, headers=admin)
    assert taken.status_code == 400


def test_auth_claim01_unassigned_link_is_claimable(tmp_path):
    """Instructor hands out a link with no assignee: the first challenger to open
    it is 403 on the scenario, claims it, then has access. A second challenger
    cannot take it over."""
    c = _fake(tmp_path)
    inst, ch, other = _h("i1", "instructor"), _h("c1", "challenger"), _h("c2", "challenger")
    sid = c.post("/api/instructor/sessions",
                 json={"scenario": "iv_url_shortener", "level": "senior"},
                 headers=inst).json()["session_id"]
    assert c.get(f"/api/session/{sid}/scenario", headers=ch).status_code == 403
    assert c.post(f"/api/session/{sid}/claim", headers=ch).json()["ok"] is True
    sc = c.get(f"/api/session/{sid}/scenario", headers=ch).json()
    assert [p["key"] for p in sc["personas"]] == ["sia", "rowan"]
    assert c.post(f"/api/session/{sid}/claim", headers=other).status_code == 403
    assert c.get(f"/api/session/{sid}/scenario", headers=other).status_code == 403


def test_auth_claim02_unknown_session_not_claimable(tmp_path):
    """A session id nobody created (e.g. typed by hand) cannot be claimed."""
    c = _fake(tmp_path)
    ch = _h("c1", "challenger")
    assert c.post("/api/session/s-madeup/claim", headers=ch).status_code == 403
    assert c.get("/api/session/s-madeup/scenario", headers=ch).status_code == 403


def test_auth_cohort01_batch_sessions_for_cohort(tmp_path):
    """Instructor creates one session per challenger in a cohort; non-challengers
    and members who already hold the scenario are skipped; each challenger sees
    only their own session; a stranger cannot open another's."""
    c = _fake(tmp_path)
    admin, inst = _h("a1", "admin", "admin@t.local"), _h("i1", "instructor")
    c.get("/api/auth/me", headers=admin)
    co = c.post("/api/admin/cohorts", json={"name": "Sept intake"}, headers=admin).json()["id"]
    students = []
    for i in range(3):
        u = c.post("/api/admin/users",
                   json={"email": f"s{i}@t.local", "role": "challenger", "name": f"Student {i}"},
                   headers=admin).json()
        students.append(u)
        assert c.post(f"/api/admin/cohorts/{co}/members", json={"uid": u["uid"]}, headers=admin).json()["ok"]
    ta = c.post("/api/admin/users", json={"email": "ta@t.local", "role": "instructor"}, headers=admin).json()
    c.post(f"/api/admin/cohorts/{co}/members", json={"uid": ta["uid"]}, headers=admin)

    listed = c.get("/api/instructor/cohorts", headers=inst).json()["cohorts"]
    assert [x["id"] for x in listed] == [co]
    assert listed[0]["member_count"] == 4 and listed[0]["challenger_count"] == 3

    r = c.post(f"/api/instructor/cohorts/{co}/sessions",
               json={"scenario": "iv_url_shortener", "level": "senior"}, headers=inst).json()
    assert r["ok"] and len(r["created"]) == 3
    assert [x["reason"] for x in r["skipped"]] == ["role is instructor"]
    sids = {x["email"]: x["session_id"] for x in r["created"]}

    for i in range(3):
        me_h = _h("tok%d" % i, "challenger", f"s{i}@t.local")   # resolves by email
        mine = c.get("/api/me/sessions", headers=me_h).json()["sessions"]
        assert [s["session_id"] for s in mine] == [sids[f"s{i}@t.local"]]
        assert c.get(f"/api/session/{sids[f's{i}@t.local']}/scenario", headers=me_h).json()["key"] == "iv_url_shortener"
    assert c.get(f"/api/session/{sids['s0@t.local']}/scenario",
                 headers=_h("x", "challenger", "s1@t.local")).status_code == 403

    # second run on the same scenario skips everyone; detail shows what they hold
    again = c.post(f"/api/instructor/cohorts/{co}/sessions",
                   json={"scenario": "iv_url_shortener", "level": "senior"}, headers=inst).json()
    assert again["created"] == [] and sum(1 for x in again["skipped"] if "already" in x["reason"]) == 3
    detail = c.get(f"/api/instructor/cohorts/{co}?scenario=iv_url_shortener", headers=inst).json()
    held = {m["email"]: [s["session_id"] for s in m["sessions"]] for m in detail["members"]}
    assert held["s0@t.local"] == [sids["s0@t.local"]] and held["ta@t.local"] == []
    # skip_existing=false creates a fresh set
    third = c.post(f"/api/instructor/cohorts/{co}/sessions",
                   json={"scenario": "iv_url_shortener", "level": "junior", "skip_existing": False},
                   headers=inst).json()
    assert len(third["created"]) == 3

    # validation + role gates
    assert c.post(f"/api/instructor/cohorts/{co}/sessions", json={"scenario": "nope"}, headers=inst).status_code == 400
    assert c.post("/api/instructor/cohorts/co-missing/sessions", json={"scenario": "churn_dashboard"}, headers=inst).status_code == 404
    assert c.get("/api/instructor/cohorts", headers=_h("c9", "challenger")).status_code == 403
