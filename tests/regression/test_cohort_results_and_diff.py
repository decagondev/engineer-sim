"""Roadmap items 4 (cohort results) and 7 (diff against the starter)."""
import subprocess

from fastapi.testclient import TestClient

from sim.adapters.workspace.local_reader import LocalWorkspaceReader
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.grading.rubric import Rubric
from sim.core.reporting.cohort import cohort_results, results_csv

RUBRIC = Rubric.from_list([{"key": "discovery", "weight": 2, "description": ""},
                           {"key": "scoping", "weight": 1, "description": ""}])


def test_cr01_cohort_results_pure():
    members = [{"uid": "u1", "email": "a@t", "name": "A"}, {"uid": "u2", "email": "b@t", "name": "B"},
               {"uid": "u3", "email": "c@t", "name": "C"}]
    rows = [{"session_id": "s1", "assignee_uid": "u1", "state": "reviewed", "submitted": True,
             "grade_total": 0.6, "review_total": 0.8, "last_ts": "t2"},
            {"session_id": "s2", "assignee_uid": "u2", "state": "not_started", "submitted": False,
             "grade_total": None, "review_total": None, "last_ts": "t1"}]
    grades = {"s1": {"total": 0.8, "total_model": 0.6, "review": {"comment": "x"},
                     "scores": [{"key": "discovery", "score": 0.9}, {"key": "scoping", "score": 0.6}]}}
    r = cohort_results("iv_parking", members, rows, grades, RUBRIC)
    assert r.graded == 1 and r.submitted == 1 and set(r.not_submitted) == {"u2", "u3"}
    a = next(m for m in r.members if m.uid == "u1")
    assert a.review_total == 0.8 and a.model_total == 0.6 and a.scores == {"discovery": 0.9, "scoping": 0.6}
    assert next(m for m in r.members if m.uid == "u3").state == "no_session"
    disc = next(c for c in r.criteria if c.key == "discovery")
    assert disc.n == 1 and disc.mean == 0.9 and disc.values == (0.9,)
    assert r.total_mean == 0.8
    csv = results_csv(r)
    assert csv.splitlines()[0] == "name,email,session_id,state,model_total,review_total,discovery,scoping"
    assert "A,a@t,s1,reviewed,0.600,0.800,0.900,0.600" in csv


def _h(uid, role, email=""):
    return {"Authorization": f"Bearer fake:{uid}:{role}:{email or uid + '@t.local'}"}


def test_cr02_cohort_results_route(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake", db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"), bootstrap_admin_email="admin@t.local")
    c = TestClient(build_app(cfg))
    admin, inst = _h("a1", "admin", "admin@t.local"), _h("i1", "instructor")
    c.get("/api/auth/me", headers=admin)
    c.post("/api/admin/users", json={"email": "i1@t.local", "role": "instructor"}, headers=admin)
    co = c.post("/api/admin/cohorts", json={"name": "C"}, headers=admin).json()["id"]
    chs = []
    for i in range(3):
        u = c.post("/api/admin/users", json={"email": f"c{i}@t.local", "role": "challenger", "name": f"C{i}"},
                   headers=admin).json()
        chs.append(u); c.post(f"/api/admin/cohorts/{co}/members", json={"uid": u["uid"]}, headers=admin)
    r = c.post(f"/api/instructor/cohorts/{co}/sessions", json={"scenario": "iv_parking"}, headers=inst).json()
    sids = {x["uid"]: x["session_id"] for x in r["created"]}
    # one graded and reviewed, one only started, one untouched
    u0, u1 = chs[0], chs[1]
    h0 = _h(u0["uid"], "challenger", "c0@t.local")
    c.post(f"/api/session/{sids[u0['uid']]}/start", headers=h0)
    c.post(f"/api/session/{sids[u0['uid']]}/submit", json={"filename": "DESIGN.md", "content": "# d\nq\n"}, headers=h0)
    c.post(f"/api/session/{sids[u0['uid']]}/grade", json={}, headers=inst)
    c.put(f"/api/instructor/session/{sids[u0['uid']]}/review", json={"scores": {"discovery": 1.0}, "comment": "top"}, headers=inst)
    c.post(f"/api/session/{sids[u1['uid']]}/start", headers=_h(u1["uid"], "challenger", "c1@t.local"))

    d = c.get(f"/api/instructor/cohorts/{co}/results?scenario=iv_parking&fresh=1", headers=inst).json()
    rep = d["report"]
    assert d["title"].startswith("Interview") and rep["graded"] == 1 and rep["submitted"] == 1
    by = {m["uid"]: m for m in rep["members"]}
    assert by[u0["uid"]]["state"] == "reviewed" and by[u0["uid"]]["scores"]["discovery"] == 1.0
    assert by[u0["uid"]]["review_total"] != by[u0["uid"]]["model_total"]
    assert by[u1["uid"]]["state"] == "active" and by[chs[2]["uid"]]["state"] == "not_started"
    assert len(rep["not_submitted"]) == 2
    disc = next(cr for cr in rep["criteria"] if cr["key"] == "discovery")
    assert disc["n"] == 1 and disc["mean"] == 1.0
    csv = c.get(f"/api/instructor/cohorts/{co}/results.csv?scenario=iv_parking", headers=inst)
    assert csv.status_code == 200 and "C0,c0@t.local" in csv.text
    assert c.get(f"/api/instructor/cohorts/{co}/results?scenario=nope", headers=inst).status_code == 400
    assert c.get(f"/api/instructor/cohorts/zzz/results?scenario=iv_parking", headers=inst).status_code == 404


def test_df01_local_diff_against_starter(tmp_path):
    wd = tmp_path / "wd"; wd.mkdir()
    (wd / "a.py").write_bytes(b"print(1)\n")
    subprocess.run(["git", "-C", str(wd), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(wd), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(wd), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(wd), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(wd), "commit", "-q", "-m", "starter"], check=True)
    files = LocalWorkspaceReader()
    assert files.diff(str(wd)) == ""
    files.write_file(str(wd), "a.py", "print(1)\nprint(2)\n")
    out = files.diff(str(wd))
    assert "diff --git a/a.py b/a.py" in out and "+print(2)" in out
    assert LocalWorkspaceReader().diff(str(tmp_path)) == "", "not a repo: no diff, no error"


def test_df02_diff_routes(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"), sandbox_root=str(tmp_path / "b"))
    c = TestClient(build_app(cfg))
    sid = "s-diff"
    c.post(f"/api/session/{sid}/start")
    assert c.get(f"/api/session/{sid}/files/diff").status_code == 409
    c.post(f"/api/session/{sid}/environment/provision")
    d = c.get(f"/api/session/{sid}/files/diff").json()
    assert d["diff"] == "" and "no changes" in d["note"]
    c.put(f"/api/session/{sid}/files/write", json={"path": "src/analysis.py", "text": "# changed\n"})
    d = c.get(f"/api/session/{sid}/files/diff").json()
    assert "src/analysis.py" in d["diff"] and "+# changed" in d["diff"]
