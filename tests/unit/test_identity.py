from sim.adapters.auth.fake_verifier import FakeVerifier
from sim.core.access.policy import can_access_session, can_admin, can_grade, can_use_instructor_api
from sim.core.ports.identity import IdentityError, Principal
from sim.core.ports.session_registry import SessionRecord


def test_policy_matrix():
    admin = Principal("a", "a@x", "admin")
    inst = Principal("i", "i@x", "instructor")
    ch = Principal("c", "c@x", "challenger")
    other = Principal("o", "o@x", "challenger")
    rec = SessionRecord("s1", owner_uid="i", assignee_uid="c")
    assert can_admin(admin) and not can_admin(inst)
    assert can_use_instructor_api(admin) and can_use_instructor_api(inst)
    assert not can_use_instructor_api(ch)
    assert can_access_session(admin, rec)
    assert can_access_session(inst, rec) and not can_access_session(inst, SessionRecord("s2", owner_uid="x"))
    assert can_access_session(ch, rec) and not can_access_session(other, rec)
    assert can_grade(ch, rec) and can_grade(inst, rec) and not can_grade(other, rec)
    disabled = Principal("c", "c@x", "challenger", disabled=True)
    assert not can_access_session(disabled, rec)


def test_fake_verifier():
    v = FakeVerifier()
    p = v.verify("fake:u1:instructor:u1@t.local")
    assert p.uid == "u1" and p.role == "instructor" and p.email == "u1@t.local"
    try:
        v.verify("nope")
        assert False
    except IdentityError:
        pass
