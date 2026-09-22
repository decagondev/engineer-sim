"""Evidence links back to the transcript message it quotes (roadmap item 3)."""
from fastapi.testclient import TestClient

from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.grading.evidence import annotate, locate
from sim.core.ports.repository import StoredMessage


def _m(i, content, kind="message", sender="tester"):
    return StoredMessage(session_id="s", sender=sender, channel="dm:sol", content=content,
                         ts="2026-01-01T00:00:00+00:00", kind=kind, id=i)


ROWS = [
    _m(1, "How many spaces are we talking about, and how is occupancy sensed?"),
    _m(2, "A few hundred spaces over a handful of floors. Loop sensors on the ramps.", sender="sol"),
    _m(3, "[reveal] Sol opened up (rung 1).", kind="event"),
    _m(4, "How fresh does the lobby display need to be?"),
    _m(5, "Half a minute behind is fine.", sender="sol"),
]


def test_ev01_locate_exact_paraphrased_and_none():
    assert locate("asked 'how is occupancy sensed?' early on", ROWS) == 1
    assert locate("The candidate asked how fresh the lobby display needs to be", ROWS) == 4
    assert locate("Half a minute behind is fine.", ROWS) == 5
    assert locate("no evidence found", ROWS) is None
    assert locate("", ROWS) is None
    assert locate("Sol opened up (rung 1)", ROWS) is None, "events are never cited"


def test_ev02_annotate_adds_refs_without_mutating():
    grade = {"scores": [{"key": "discovery", "score": 0.7, "evidence": "asked how occupancy is sensed"}],
             "tickets_extra": {"key": "tickets", "score": 0.5, "evidence": "no tickets"}}
    out = annotate(grade, ROWS)
    assert out["scores"][0]["evidence_ref"] == 1
    assert out["tickets_extra"]["evidence_ref"] is None
    assert "evidence_ref" not in grade["scores"][0]


def test_ev03_grade_route_carries_refs(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"), sandbox_root=str(tmp_path / "b"))
    c = TestClient(build_app(cfg))
    h = {"X-Instructor-Token": "$T0mV13w"}
    sid = "s-ev"
    c.post(f"/api/instructor/session/{sid}/scenario", json={"scenario": "iv_parking"}, headers=h)
    c.post(f"/api/session/{sid}/start")
    # the fake grader cites "asked clarifying questions"; post a message that contains it
    svc = c.app.state.manager.for_session(sid).session_service
    svc.post_tester_message(sid, "I asked clarifying questions about scale first", target="sol")
    g = c.post(f"/api/session/{sid}/grade", json={}).json()
    disc = next(s for s in g["scores"] if s["key"] == "discovery")
    assert disc["evidence_ref"] is not None
    ids = {m["id"] for m in c.get(f"/api/session/{sid}/transcript").json()}
    assert disc["evidence_ref"] in ids
    assert c.get(f"/api/session/{sid}/grade").json()["scores"][0]["evidence_ref"] == disc["evidence_ref"]
