from datetime import datetime, timezone

from sim.adapters.auth.fake_verifier import FakeVerifier
from sim.adapters.auth.services import AuthServices
from sim.adapters.persistence.sqlite_users import InMemoryUserDirectory
from sim.core.access.policy import can_access_session, can_admin, can_grade, can_use_instructor_api
from sim.core.ports.identity import IdentityError, Principal
from sim.core.ports.session_registry import SessionRecord
from sim.core.ports.users import UserRecord


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


def test_sync_skips_write_when_login_is_fresh():
    users = InMemoryUserDirectory()
    now = datetime.now(timezone.utc).isoformat()
    users.upsert(UserRecord("u1", "a@t.local", "challenger",
                            created_at=now, last_login=now))
    writes = {"n": 0}
    real = users.upsert

    def counted(rec):
        writes["n"] += 1
        return real(rec)

    users.upsert = counted
    auth = AuthServices("fake", verifier=FakeVerifier(), users=users)
    p = auth.principal_from_token("fake:u1:challenger:a@t.local")
    assert p.uid == "u1" and writes["n"] == 0


def test_firebase_verify_caches_lookup(monkeypatch):
    from sim.adapters.auth.firebase_verifier import FirebaseVerifier
    calls = {"n": 0}

    class _Resp:
        status_code = 200
        def json(self):
            return {"users": [{"localId": "u1", "email": "a@t.local",
                               "emailVerified": True}]}

    v = FirebaseVerifier("fake-key", "proj")

    def post(*_a, **_k):
        calls["n"] += 1
        return _Resp()

    v._http.post = post
    a = v.verify("tok-1")
    b = v.verify("tok-1")
    assert a.uid == "u1" and b.uid == "u1" and calls["n"] == 1
    try:
        v.set_password("u1", "123")
        assert False
    except IdentityError as e:
        assert e.status == 400
