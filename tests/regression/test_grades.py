"""Grades are persisted; a regrade replaces the last one; a newer submission
sends the session back to 'submitted'; export uses the stored grade."""
from fastapi.testclient import TestClient

from sim.adapters.persistence.firestore_store import FirestoreGradeStore
from sim.adapters.persistence.memory_grades import InMemoryGradeStore
from sim.adapters.persistence.sqlite_grades import SqliteGradeStore
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.ports.grades import StoredGrade
from tests.unit.fake_firestore import FakeFirestore

TOKEN = {"X-Instructor-Token": "$T0mV13w"}


def _grader_calls(c):
    llm = c.app.state.grader._llm
    return getattr(llm, "calls", None) or llm._fallback.calls


def test_gr01_stores_roundtrip(tmp_path):
    for st in (InMemoryGradeStore(), SqliteGradeStore(str(tmp_path / "g.db")),
               FirestoreGradeStore(FakeFirestore())):
        assert st.get("s") is None
        st.save(StoredGrade("s", 0.5, "senior", "2026-01-01T00:00:00+00:00", "i@t", False, False,
                            {"total": 0.5, "scores": []}))
        st.save(StoredGrade("s", 0.8, "senior", "2026-01-02T00:00:00+00:00", "i@t", True, False,
                            {"total": 0.8, "scores": [{"key": "discovery"}]}))
        g = st.get("s")
        assert g.total == 0.8 and g.include_tickets and g.body["scores"][0]["key"] == "discovery"
        st.delete_for_session("s")
        assert st.get("s") is None


def test_gr02_grade_persists_and_regrade_replaces(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"),
                 sandbox_root=str(tmp_path / "b"))
    c = TestClient(build_app(cfg))
    sid = "s-grade"
    c.post(f"/api/instructor/session/{sid}/scenario", json={"scenario": "iv_parking"}, headers=TOKEN)
    c.post(f"/api/session/{sid}/start")
    assert c.get(f"/api/session/{sid}/grade").status_code == 404
    c.post(f"/api/session/{sid}/submit", json={"filename": "DESIGN.md", "content": "# d\nqueue\n"})

    g1 = c.post(f"/api/session/{sid}/grade", json={}).json()
    assert g1["stored"] and g1["graded_at"] and g1["graded_by"]
    got = c.get(f"/api/session/{sid}/grade").json()
    assert got["graded_at"] == g1["graded_at"] and got["total"] == g1["total"]

    rows = c.get("/api/instructor/sessions", headers=TOKEN).json()["sessions"]
    row = next(r for r in rows if r["session_id"] == sid)
    assert row["state"] == "graded" and row["grade_total"] == g1["total"]
    ov = c.get("/api/instructor/overview", headers=TOKEN).json()["stats"]
    assert ov["totals"]["graded"] == 1 and ov["by_scenario"][0]["graded"] == 1

    # a fresh process still sees it, without calling the grader again
    c2 = TestClient(build_app(cfg))
    before = len(_grader_calls(c2))
    assert c2.get(f"/api/session/{sid}/grade").json()["graded_at"] == g1["graded_at"]
    md = c2.get(f"/api/instructor/session/{sid}/export.md", headers=TOKEN).text
    assert "Total:" in md and len(_grader_calls(c2)) == before, "export must use the stored grade"

    # regrade with tickets replaces the stored grade
    g2 = c2.post(f"/api/session/{sid}/grade", json={"include_tickets": True}).json()
    assert g2["include_tickets"] is True and g2["graded_at"] > g1["graded_at"]
    assert c2.get(f"/api/session/{sid}/grade").json()["include_tickets"] is True

    # a newer submission needs another look
    c2.post(f"/api/session/{sid}/submit", json={"filename": "DESIGN.md", "content": "# d v2\nqueue+cache\n"})
    rows = c2.get("/api/instructor/sessions", headers=TOKEN).json()["sessions"]
    assert next(r for r in rows if r["session_id"] == sid)["state"] == "submitted"


def test_gr03_admin_delete_removes_grade(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake", db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"), bootstrap_admin_email="admin@t.local")
    c = TestClient(build_app(cfg))
    admin = {"Authorization": "Bearer fake:a1:admin:admin@t.local"}
    c.get("/api/auth/me", headers=admin)
    sid = "s-del"
    c.post(f"/api/session/{sid}/start", headers=admin)
    c.post(f"/api/session/{sid}/grade", json={}, headers=admin)
    assert c.get(f"/api/session/{sid}/grade", headers=admin).status_code == 200
    assert c.delete(f"/api/admin/sessions/{sid}", headers=admin).json()["ok"]
    assert c.app.state.grades.get(sid) is None
