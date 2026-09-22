"""Instructor review: merge maths, stores, routes, export, states (roadmap item 1)."""
import pytest
from fastapi.testclient import TestClient

from sim.adapters.persistence.firestore_store import FirestoreReviewStore
from sim.adapters.persistence.memory_reviews import InMemoryReviewStore
from sim.adapters.persistence.sqlite_reviews import SqliteReviewStore
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.grading.review import HumanReview, ReviewError, merge_review, validate_review
from sim.core.grading.rubric import Rubric
from tests.unit.fake_firestore import FakeFirestore

RUBRIC = Rubric.from_list([
    {"key": "discovery", "weight": 2.0, "description": ""},
    {"key": "scoping", "weight": 2.0, "description": ""},
    {"key": "communication", "weight": 1.0, "description": ""},
])
GRADE = {
    "total": 0.6, "summary": "ok", "include_tickets": False,
    "weights": {"discovery": 2.0, "scoping": 2.0, "communication": 1.0},
    "scores": [{"key": "discovery", "score": 0.5, "evidence": "a"},
               {"key": "scoping", "score": 0.7, "evidence": "b"},
               {"key": "communication", "score": 0.6, "evidence": "c"}],
}


def test_rv01_merge_recomputes_total_with_grade_weights():
    plain = merge_review(GRADE, None, RUBRIC)
    assert plain["review"] is None and all(s["source"] == "model" for s in plain["scores"])
    assert plain["total"] == 0.6

    rv = HumanReview("s", {"discovery": 1.0}, "asked everything", "i@t", "2026-01-02T00:00:00+00:00")
    m = merge_review(GRADE, rv, RUBRIC)
    disc = next(s for s in m["scores"] if s["key"] == "discovery")
    assert disc["score"] == 1.0 and disc["source"] == "human" and disc["model_score"] == 0.5
    assert m["total"] == round((1.0 * 2 + 0.7 * 2 + 0.6 * 1) / 5, 3)
    assert m["total_model"] == 0.6 and m["review"]["comment"] == "asked everything"
    assert GRADE["scores"][0]["score"] == 0.5, "input must not be mutated"


def test_rv02_merge_handles_tickets_extra_credit():
    g = dict(GRADE, include_tickets=True, total_base=0.6, total=0.675,
             tickets_extra={"key": "tickets", "score": 0.5, "evidence": "t"})
    m = merge_review(g, HumanReview("s", {"tickets": 1.0}, "", "i", "t"), RUBRIC)
    assert m["tickets_extra"]["source"] == "human" and m["total_base"] == 0.6
    assert m["total"] == round(min(1.0, 0.6 + 0.15), 3)


def test_rv03_validate_review():
    assert validate_review({"discovery": "0.85", "tickets": 0.5}, RUBRIC) == {"discovery": 0.85, "tickets": 0.5}
    with pytest.raises(ReviewError):
        validate_review({"nope": 0.5}, RUBRIC)
    with pytest.raises(ReviewError):
        validate_review({"discovery": 1.5}, RUBRIC)
    with pytest.raises(ReviewError):
        validate_review({"discovery": "x"}, RUBRIC)
    with pytest.raises(ReviewError):
        validate_review({"tickets": 0.5}, RUBRIC, allow_tickets=False)


def test_rv04_stores_roundtrip(tmp_path):
    for st in (InMemoryReviewStore(), SqliteReviewStore(str(tmp_path / "r.db")),
               FirestoreReviewStore(FakeFirestore())):
        assert st.get("s") is None
        st.save(HumanReview("s", {"discovery": 0.9}, "good", "i@t", "t1"))
        st.save(HumanReview("s", {"discovery": 0.8, "scoping": 0.4}, "better", "i@t", "t2"))
        r = st.get("s")
        assert r.scores == {"discovery": 0.8, "scoping": 0.4} and r.comment == "better" and r.ts == "t2"
        st.delete_for_session("s")
        assert st.get("s") is None


def _fake(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake", db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"), bootstrap_admin_email="admin@t.local")
    return TestClient(build_app(cfg))


def _h(uid, role, email=""):
    return {"Authorization": f"Bearer fake:{uid}:{role}:{email or uid + '@t.local'}"}


def test_rv05_review_route_end_to_end(tmp_path):
    c = _fake(tmp_path)
    admin, inst, other = _h("a1", "admin", "admin@t.local"), _h("i1", "instructor"), _h("i2", "instructor")
    c.get("/api/auth/me", headers=admin)
    for uid in ("i1", "i2"):
        c.post("/api/admin/users", json={"email": f"{uid}@t.local", "role": "instructor"}, headers=admin)
    ch = c.post("/api/admin/users", json={"email": "c1@t.local", "role": "challenger"}, headers=admin).json()
    sid = c.post("/api/instructor/sessions", json={"scenario": "iv_parking", "assignee_email": "c1@t.local"},
                 headers=inst).json()["session_id"]
    chal = _h(ch["uid"], "challenger", "c1@t.local")
    c.post(f"/api/session/{sid}/start", headers=chal)
    c.post(f"/api/session/{sid}/submit", json={"filename": "DESIGN.md", "content": "# d\nq\n"}, headers=chal)
    g = c.post(f"/api/session/{sid}/grade", json={}, headers=inst).json()
    assert "weights" in g and g["review"] is None

    # only the owning instructor (or an admin) may review
    body = {"scores": {"discovery": 0.95}, "comment": "Strong questions."}
    assert c.put(f"/api/instructor/session/{sid}/review", json=body, headers=other).status_code == 403
    assert c.put(f"/api/instructor/session/{sid}/review", json=body, headers=chal).status_code == 403
    assert c.put(f"/api/instructor/session/{sid}/review", json={"scores": {"bogus": 1}}, headers=inst).status_code == 400
    r = c.put(f"/api/instructor/session/{sid}/review", json=body, headers=inst)
    assert r.status_code == 200, r.text
    merged = r.json()["grade"]
    disc = next(s for s in merged["scores"] if s["key"] == "discovery")
    assert disc["score"] == 0.95 and disc["source"] == "human"
    assert merged["review"]["reviewer"] == "i1@t.local" and merged["total"] != merged["total_model"]

    # readers see the merge; the challenger too
    got = c.get(f"/api/session/{sid}/grade", headers=chal).json()
    assert got["review"]["comment"] == "Strong questions." and got["total"] == merged["total"]

    # the session is reviewed on the dashboards
    rows = c.get("/api/instructor/sessions", headers=inst).json()["sessions"]
    row = next(x for x in rows if x["session_id"] == sid)
    assert row["state"] == "reviewed" and row["reviewed"] is True
    assert c.get("/api/instructor/overview?fresh=1", headers=inst).json()["stats"]["totals"]["reviewed"] == 1

    # export records both verdicts
    md = c.get(f"/api/instructor/session/{sid}/export.md", headers=inst).text
    assert "Instructor review" in md and "(instructor; model" in md and "Strong questions." in md

    # a regrade keeps the review; clearing it returns to the model grade
    c.post(f"/api/session/{sid}/grade", json={}, headers=inst)
    assert c.get(f"/api/session/{sid}/grade", headers=inst).json()["review"]["comment"] == "Strong questions."
    assert c.delete(f"/api/instructor/session/{sid}/review", headers=inst).json()["ok"]
    after = c.get(f"/api/session/{sid}/grade", headers=inst).json()
    assert after["review"] is None and all(s["source"] == "model" for s in after["scores"])
    rows = c.get("/api/instructor/sessions", headers=inst).json()["sessions"]
    assert next(x for x in rows if x["session_id"] == sid)["state"] == "graded"

    # admin cascade delete removes the review too
    c.put(f"/api/instructor/session/{sid}/review", json=body, headers=admin)
    assert c.delete(f"/api/admin/sessions/{sid}", headers=admin).json()["ok"]
    assert c.app.state.reviews.get(sid) is None
