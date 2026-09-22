"""Calibration from the dashboard (roadmap item 2): reviewed sessions become
fixtures, a run grades them and records a report, apply flips the flag only
after a pass."""
import pytest
from fastapi.testclient import TestClient

from sim.adapters.persistence.firestore_store import FirestoreCalibrationRunStore
from sim.adapters.persistence.memory_calibration import InMemoryCalibrationRunStore
from sim.adapters.persistence.sqlite_calibration import SqliteCalibrationRunStore
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.grading.fixtures import fixture_from_review, group_by_rubric
from sim.core.grading.rubric import CriterionScore, Grade, Rubric
from sim.core.ports.calibration import CalibrationRun
from tests.unit.fake_firestore import FakeFirestore

RUBRIC = Rubric.from_list([{"key": "discovery", "weight": 2.0, "description": ""},
                           {"key": "scoping", "weight": 1.0, "description": ""}])


def test_cd01_fixture_from_review_uses_the_merged_verdict():
    class Row:
        def __init__(self, i, c): self.sender, self.channel, self.content, self.kind, self.id = "tester", "dm:x", c, "message", i
    rows = [Row(1, "hello")]
    merged = {"summary": "model says", "review": {"comment": "human says", "scores": {"discovery": 0.9}},
              "scores": [{"key": "discovery", "score": 0.9, "source": "human"},
                         {"key": "scoping", "score": 0.4, "source": "model"}]}
    fx = fixture_from_review("s1", rows, merged, RUBRIC, scenario_key="iv_parking", level="senior",
                             build_record="BR", expectation="EXP")
    assert fx["human"]["scores"] == {"discovery": 0.9, "scoping": 0.4}
    assert fx["human"]["summary"] == "human says" and fx["scenario"] == "iv_parking"
    assert fx["transcript"][0]["content"] == "hello" and fx["expectation"] == "EXP"
    assert fixture_from_review("s1", rows, {"scores": [], "review": None}, RUBRIC) is None
    groups = group_by_rubric([fx, dict(fx, scenario="nope")], lambda k: RUBRIC if k == "iv_parking" else None)
    assert len(groups) == 1 and groups[0][0] == "iv_parking" and len(groups[0][2]) == 1


def test_cd02_run_stores_roundtrip(tmp_path):
    for st in (InMemoryCalibrationRunStore(), SqliteCalibrationRunStore(str(tmp_path / "c.db")),
               FirestoreCalibrationRunStore(FakeFirestore())):
        assert st.latest() is None
        st.save(CalibrationRun(id="a", status="running", started="2026-01-01T00:00:00+00:00", total=2))
        st.save(CalibrationRun(id="a", status="done", started="2026-01-01T00:00:00+00:00", total=2, done=2,
                               passed=True, reports={"iv": {"n": 2, "passed": True}}))
        r = st.latest()
        assert r.status == "done" and r.passed and r.reports["iv"]["n"] == 2


class AgreeingGrader:
    """Grades exactly like the human did, by reading the fixture's human scores
    back out of the expectation string we plant."""

    def __init__(self, scores_by_id):
        self.scores_by_id = scores_by_id
        self.calls = 0

    def grade(self, session_id, reader, rubric, build_record="", expectation=""):
        self.calls += 1
        scores = self.scores_by_id.get(build_record, {})
        cs = tuple(CriterionScore(c.key, float(scores.get(c.key, 0.0)), "agree") for c in rubric.criteria)
        tw = sum(c.weight for c in rubric.criteria)
        total = sum(s.score * c.weight for s, c in zip(cs, rubric.criteria)) / tw
        return Grade(cs, total, "agreeing")


def _h(uid, role, email=""):
    return {"Authorization": f"Bearer fake:{uid}:{role}:{email or uid + '@t.local'}"}


def test_cd03_dashboard_run_and_apply(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake", db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"), bootstrap_admin_email="admin@t.local")
    c = TestClient(build_app(cfg))
    admin, inst = _h("a1", "admin", "admin@t.local"), _h("i1", "instructor")
    c.get("/api/auth/me", headers=admin)
    c.post("/api/admin/users", json={"email": "i1@t.local", "role": "instructor"}, headers=admin)

    # nothing reviewed yet: cannot run; fake provider: cannot run
    d = c.get("/api/admin/calibration", headers=admin).json()
    assert d["latest"] is None and d["fixtures_available"] == 0 and d["can_run"] is False
    assert c.post("/api/admin/calibration/run", headers=admin).status_code == 400

    # two graded and reviewed sessions on the same rubric
    human = {}
    for i in range(2):
        sid = c.post("/api/instructor/sessions", json={"scenario": "iv_parking"}, headers=inst).json()["session_id"]
        c.post(f"/api/session/{sid}/start", headers=inst)
        c.post(f"/api/session/{sid}/submit", json={"filename": "DESIGN.md", "content": f"# d{i}\nqueue\n"}, headers=inst)
        g = c.post(f"/api/session/{sid}/grade", json={}, headers=inst).json()
        assert "build_record" in c.app.state.grades.get(sid).body
        scores = {"discovery": 0.9 - 0.3 * i, "scoping": 0.8 - 0.2 * i}
        c.put(f"/api/instructor/session/{sid}/review", json={"scores": scores, "comment": "ok"}, headers=inst)
        merged = c.get(f"/api/session/{sid}/grade", headers=inst).json()
        human[c.app.state.grades.get(sid).body.get("build_record", "")] = {s["key"]: s["score"] for s in merged["scores"]}

    d = c.get("/api/admin/calibration", headers=admin).json()
    assert d["fixtures_available"] == 2
    fx = c.get("/api/admin/calibration/fixtures.json", headers=admin).json()["fixtures"]
    assert len(fx) == 2 and all(f["scenario"] == "iv_parking" for f in fx)

    # a grader that agrees with the humans passes; apply then unlocks
    c.app.state.calibration_grader = AgreeingGrader(human)
    assert c.post("/api/admin/calibration/apply", headers=admin).status_code == 409
    r = c.post("/api/admin/calibration/run?sync=1", headers=admin)
    assert r.status_code == 200, r.text
    run = c.get("/api/admin/calibration", headers=admin).json()["latest"]
    assert run["status"] == "done" and run["done"] == 2 and run["passed"] is True
    rep = run["reports"]["iv_parking"]
    assert rep["n"] == 2 and rep["total_mae"] == 0 and any("only 2 fixtures" in n for n in rep["notes"])
    assert c.get("/api/admin/settings", headers=admin).json()["grader_calibrated_effective"] is False
    assert c.post("/api/admin/calibration/apply", headers=admin).json()["calibrated"] is True
    assert c.get("/api/admin/settings", headers=admin).json()["grader_calibrated"] is True

    # a disagreeing grader fails and cannot be applied
    c.app.state.calibration_grader = AgreeingGrader({})
    c.post("/api/admin/calibration/run?sync=1", headers=admin)
    run = c.get("/api/admin/calibration", headers=admin).json()["latest"]
    assert run["status"] == "done" and run["passed"] is False
    assert c.post("/api/admin/calibration/apply", headers=admin).status_code == 409
    assert c.get("/api/admin/calibration", headers=admin).json()["running"] is False
    assert c.get("/api/admin/calibration", headers=_h("i1", "instructor")).status_code == 403
