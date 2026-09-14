"""Firestore adapters against an in-process fake. No live project required."""
import pytest

from sim.app.config import Config
from sim.adapters.persistence.firestore_store import (
    FirestoreCohortDirectory, FirestoreMailStore, FirestoreMessageRepository,
    FirestoreSessionRegistry, FirestoreSettingsStore, FirestoreSubmissionStore,
    FirestoreTicketStore, FirestoreUnlockStore, FirestoreUserDirectory,
)
from sim.core.ports.cohorts import CohortRecord
from sim.adapters.persistence.stores import build_stores
from sim.core.ports.repository import StoredMessage
from sim.core.ports.session_registry import SessionRecord
from sim.core.ports.settings import InstructorSettings
from sim.core.ports.users import UserRecord
from tests.unit.fake_firestore import FakeFirestore


def _all(db):
    return (
        FirestoreMessageRepository(db),
        FirestoreUnlockStore(db),
        FirestoreMailStore(db),
        FirestoreTicketStore(db),
        FirestoreSettingsStore(db),
        FirestoreSubmissionStore(db),
        FirestoreUserDirectory(db),
        FirestoreSessionRegistry(db),
        FirestoreCohortDirectory(db),
    )


def test_persistence_defaults_to_sqlite():
    assert Config().persistence == "sqlite"


def test_firestore_refuses_without_project():
    cfg = Config(persistence="firestore", firebase_project_id="")
    with pytest.raises(RuntimeError, match="FIREBASE_PROJECT_ID"):
        build_stores(cfg)


def test_unknown_persistence_rejected(tmp_path):
    with pytest.raises(ValueError, match="PERSISTENCE"):
        build_stores(Config(persistence="s3", db_path=str(tmp_path / "x.db")))


def test_sqlite_factory_still_default(tmp_path):
    stores = build_stores(Config(db_path=str(tmp_path / "t.db")))
    assert stores.repo.list_sessions() == []


def test_firestore_roundtrip():
    db = FakeFirestore()
    repo, unlock, mail, tickets, settings, subs, users, sessions, cohorts = _all(db)

    users.upsert(UserRecord("u1", "a@t.local", "admin", name="Ada",
                            groq_key_enc="cipher"))
    assert users.get("u1").name == "Ada"
    assert users.get("u1").groq_key_enc == "cipher"
    cohorts.upsert(CohortRecord("co-1", "Spring", "notes", "t0"))
    cohorts.add_member("co-1", "u1")
    assert list(cohorts.members("co-1")) == ["u1"]
    assert list(cohorts.cohorts_for("u1")) == ["co-1"]
    assert users.get_by_email("A@t.local").uid == "u1"
    assert users.count_role("admin") == 1

    sessions.upsert(SessionRecord(
        id="s-1", owner_uid="u1", assignee_uid="c1",
        scenario_key="churn_dashboard", level="mid", status="assigned"))
    rec = sessions.get("s-1")
    assert rec.owner_uid == "u1" and rec.scenario_key == "churn_dashboard"

    settings.set_session_level("s-1", "senior")
    settings.set_session_scenario("s-1", "iv_unique_id")
    assert settings.get_session_level("s-1") == "senior"
    assert settings.get_session_scenario("s-1") == "iv_unique_id"
    assert sessions.get("s-1").owner_uid == "u1"

    settings.set_instructor(InstructorSettings(True, "mid"))
    assert settings.get_instructor().default_level == "mid"
    settings.set_scenario_starter_url("churn_dashboard", "https://x")
    settings.set_scenario_enabled("churn_dashboard", False)
    assert settings.get_scenario_starter_url("churn_dashboard") == "https://x"
    assert settings.get_scenario_enabled("churn_dashboard") is False

    m = repo.append(StoredMessage("s-1", "tester", "general", "hi", "2026-01-01T00:00:00Z"))
    assert m.id == 1
    assert repo.list_for_session("s-1")[0].content == "hi"
    listed = repo.list_sessions()
    assert listed[0]["session_id"] == "s-1" and listed[0]["count"] == 1

    unlock.set_unlocked("s-1", "priya", 2)
    assert unlock.get_unlocked("s-1", "priya") == 2

    th = mail.create_thread("s-1", "Hello", "dana", "t1")
    mail.touch_persona("s-1", th.id, "t2")
    assert mail.unread_count("s-1") == 1
    mail.mark_read("s-1", th.id, "t3")
    assert mail.unread_count("s-1") == 0

    t = tickets.create("s-1", "Do it", "desc", "todo", "priya", "t1")
    tickets.update_status("s-1", t.id, "done", "t2")
    assert tickets.get("s-1", t.id).status == "done"
    assert tickets.delete_one("s-1", t.id)

    sub = subs.save("s-1", "work.diff", "+++ a\n", "t1")
    assert sub.seq == 1 and subs.latest("s-1").filename == "work.diff"

    repo.delete_for_session("s-1")
    assert repo.list_sessions() == []
    assert sessions.get("s-1") is not None
    assert sessions.delete("s-1")
    assert sessions.get("s-1") is None


def test_migrate_sqlite_into_firestore_stores(tmp_path):
    from sim.adapters.persistence.stores import Stores
    from sim.adapters.persistence.sqlite_repo import SqliteMessageRepository
    from sim.adapters.persistence.sqlite_sessions import SqliteSessionRegistry
    from sim.adapters.persistence.sqlite_users import SqliteUserDirectory
    from tools.migrate_sqlite_to_firestore import migrate

    path = str(tmp_path / "old.db")
    src_users = SqliteUserDirectory(path)
    src_users.upsert(UserRecord("u1", "tom@t.local", "admin"))
    src_reg = SqliteSessionRegistry(path)
    src_reg.upsert(SessionRecord(id="s-old", owner_uid="u1",
                                 scenario_key="churn_dashboard", level="mid"))
    src_repo = SqliteMessageRepository(path)
    src_repo.append(StoredMessage("s-old", "tester", "general", "yo", "t0"))

    db = FakeFirestore()
    dest = Stores(*_all(db))
    counts = migrate(path, dest)
    assert counts["users"] == 1 and counts["messages"] == 1
    assert dest.users.get_by_email("tom@t.local").role == "admin"
    assert dest.repo.list_for_session("s-old")[0].content == "yo"
    assert dest.session_registry.get("s-old").owner_uid == "u1"
