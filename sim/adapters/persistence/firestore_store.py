"""Firestore implementations of every persistence port. Not imported by core."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from sim.adapters.persistence.firestore_client import session_doc
from sim.core.ports.cohorts import CohortRecord
from sim.core.ports.mail import MailThread
from sim.core.ports.repository import StoredMessage
from sim.core.ports.session_registry import SessionRecord
from sim.core.ports.settings import InstructorSettings
from sim.core.ports.submissions import Submission
from sim.core.ports.tickets import Ticket
from sim.core.ports.users import UserRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data(snap) -> dict:
    return snap.to_dict() or {} if snap.exists else {}


def _max_int(col, field: str = "seq") -> int:
    n = 0
    for snap in col.stream():
        n = max(n, int((_data(snap).get(field) or 0)))
    return n


class FirestoreMessageRepository:
    def __init__(self, db) -> None:
        self._db = db

    def append(self, message: StoredMessage) -> StoredMessage:
        ref = session_doc(self._db, message.session_id)
        col = ref.collection("messages")
        seq = _max_int(col, "seq") + 1
        ts = message.ts or _now()
        payload = {
            "session_id": message.session_id, "sender": message.sender,
            "channel": message.channel, "content": message.content,
            "ts": ts, "kind": message.kind or "message", "seq": seq,
        }
        col.document(str(seq)).set(payload)
        snap = ref.get()
        existing = _data(snap)
        count = int(existing.get("message_count") or 0) + 1
        patch = {"message_count": count, "last_ts": ts}
        if not existing.get("first_ts"):
            patch["first_ts"] = ts
        if not snap.exists:
            patch.setdefault("created_at", ts)
            patch.setdefault("status", "active")
        ref.set(patch, merge=True)
        return StoredMessage(
            id=seq, session_id=message.session_id, sender=message.sender,
            channel=message.channel, content=message.content, ts=ts,
            kind=message.kind or "message",
        )

    def list_for_session(self, session_id: str) -> Sequence[StoredMessage]:
        snaps = list(session_doc(self._db, session_id).collection("messages").stream())
        rows = []
        for snap in snaps:
            d = _data(snap)
            rows.append(StoredMessage(
                id=int(d.get("seq") or snap.id or 0) or None,
                session_id=session_id, sender=d.get("sender") or "",
                channel=d.get("channel") or "", content=d.get("content") or "",
                ts=d.get("ts") or "", kind=d.get("kind") or "message",
            ))
        rows.sort(key=lambda m: (m.id or 0, m.ts))
        return rows

    def list_sessions(self) -> list[dict]:
        out = []
        for snap in self._db.collection("sessions").stream():
            d = _data(snap)
            count = int(d.get("message_count") or 0)
            if count <= 0:
                continue
            out.append({
                "session_id": snap.id, "count": count,
                "first_ts": d.get("first_ts") or "",
                "last_ts": d.get("last_ts") or "",
            })
        out.sort(key=lambda r: r.get("last_ts") or "", reverse=True)
        return out

    def delete_for_session(self, session_id: str) -> None:
        ref = session_doc(self._db, session_id)
        _delete_collection(ref.collection("messages"))
        ref.set({"message_count": 0, "first_ts": "", "last_ts": ""}, merge=True)


class FirestoreUnlockStore:
    def __init__(self, db) -> None:
        self._db = db

    def get_unlocked(self, session_id: str, persona_key: str) -> int:
        snap = session_doc(self._db, session_id).collection("unlock").document(
            persona_key).get()
        return int(_data(snap).get("unlocked") or 0)

    def set_unlocked(self, session_id: str, persona_key: str, count: int) -> None:
        session_doc(self._db, session_id).collection("unlock").document(
            persona_key).set({"unlocked": int(count), "persona_key": persona_key})

    def delete_for_session(self, session_id: str) -> None:
        _delete_collection(session_doc(self._db, session_id).collection("unlock"))


class FirestoreMailStore:
    def __init__(self, db) -> None:
        self._db = db

    def create_thread(self, session_id, subject, participant, ts) -> MailThread:
        return self.put_thread(session_id, uuid.uuid4().hex[:8], subject,
                               participant, ts)

    def put_thread(self, session_id, thread_id, subject, participant, ts,
                   last_persona_ts: str = "", last_read_ts: str = "") -> MailThread:
        session_doc(self._db, session_id).collection("mail").document(thread_id).set({
            "id": thread_id, "session_id": session_id, "subject": subject,
            "participant": participant, "created_ts": ts,
            "last_persona_ts": last_persona_ts, "last_read_ts": last_read_ts,
        })
        return MailThread(thread_id, session_id, subject, participant, ts)

    def get_thread(self, session_id, thread_id) -> Optional[MailThread]:
        snap = session_doc(self._db, session_id).collection("mail").document(
            thread_id).get()
        return self._row(session_id, snap) if snap.exists else None

    def list_threads(self, session_id) -> Sequence[MailThread]:
        rows = [self._row(session_id, s) for s in
                session_doc(self._db, session_id).collection("mail").stream()]
        rows.sort(key=lambda t: t.created_ts)
        return rows

    def mark_read(self, session_id, thread_id, ts) -> None:
        session_doc(self._db, session_id).collection("mail").document(
            thread_id).set({"last_read_ts": ts}, merge=True)

    def touch_persona(self, session_id, thread_id, ts) -> None:
        session_doc(self._db, session_id).collection("mail").document(
            thread_id).set({"last_persona_ts": ts}, merge=True)

    def unread_count(self, session_id) -> int:
        n = 0
        for snap in session_doc(self._db, session_id).collection("mail").stream():
            d = _data(snap)
            persona = d.get("last_persona_ts") or ""
            read = d.get("last_read_ts") or ""
            if persona and persona > read:
                n += 1
        return n

    def delete_for_session(self, session_id: str) -> None:
        _delete_collection(session_doc(self._db, session_id).collection("mail"))

    @staticmethod
    def _row(session_id, snap) -> MailThread:
        d = _data(snap)
        return MailThread(
            d.get("id") or snap.id, session_id,
            d.get("subject") or "", d.get("participant") or "",
            d.get("created_ts") or "")


class FirestoreTicketStore:
    def __init__(self, db) -> None:
        self._db = db

    def create(self, session_id, title, description, status, created_by, ts, *,
               issue_type: str = "task", priority: str = "medium",
               labels: str = "") -> Ticket:
        col = session_doc(self._db, session_id).collection("tickets")
        seq = _max_int(col, "seq") + 1
        return self.put_ticket(Ticket(
            uuid.uuid4().hex[:8], session_id, title, description, status,
            created_by, ts, seq, issue_type, priority, labels))

    def put_ticket(self, ticket: Ticket) -> Ticket:
        session_doc(self._db, ticket.session_id).collection("tickets").document(
            ticket.id).set({
            "id": ticket.id, "session_id": ticket.session_id,
            "title": ticket.title, "description": ticket.description,
            "status": ticket.status, "created_by": ticket.created_by,
            "ts": ticket.ts, "seq": ticket.seq,
            "issue_type": ticket.issue_type, "priority": ticket.priority,
            "labels": ticket.labels,
        })
        return ticket

    def get(self, session_id, ticket_id) -> Optional[Ticket]:
        snap = session_doc(self._db, session_id).collection("tickets").document(
            ticket_id).get()
        return self._row(session_id, snap) if snap.exists else None

    def list(self, session_id) -> Sequence[Ticket]:
        rows = [self._row(session_id, s) for s in
                session_doc(self._db, session_id).collection("tickets").stream()]
        rows.sort(key=lambda t: t.seq)
        return rows

    def update_status(self, session_id, ticket_id, status, ts) -> Optional[Ticket]:
        cur = self.get(session_id, ticket_id)
        if not cur:
            return None
        session_doc(self._db, session_id).collection("tickets").document(
            ticket_id).set({"status": status, "ts": ts}, merge=True)
        return Ticket(cur.id, cur.session_id, cur.title, cur.description,
                      status, cur.created_by, ts, cur.seq, cur.issue_type,
                      cur.priority, cur.labels)

    def delete_for_session(self, session_id: str) -> None:
        _delete_collection(session_doc(self._db, session_id).collection("tickets"))

    def delete_one(self, session_id: str, ticket_id: str) -> bool:
        ref = session_doc(self._db, session_id).collection("tickets").document(
            ticket_id)
        if not ref.get().exists:
            return False
        ref.delete()
        return True

    @staticmethod
    def _row(session_id, snap) -> Ticket:
        d = _data(snap)
        return Ticket(
            d.get("id") or snap.id, session_id,
            d.get("title") or "", d.get("description") or "",
            d.get("status") or "todo", d.get("created_by") or "",
            d.get("ts") or "", seq=int(d.get("seq") or 1),
            issue_type=d.get("issue_type") or "task",
            priority=d.get("priority") or "medium",
            labels=d.get("labels") or "",
        )


class FirestoreSettingsStore:
    def __init__(self, db) -> None:
        self._db = db

    def get_instructor(self) -> InstructorSettings:
        d = _data(self._db.collection("meta").document("instructor").get())
        if not d:
            return InstructorSettings()
        return InstructorSettings(bool(d.get("onboarded")),
                                  d.get("default_level") or "senior")

    def set_instructor(self, settings: InstructorSettings) -> None:
        self._db.collection("meta").document("instructor").set({
            "onboarded": bool(settings.onboarded),
            "default_level": settings.default_level,
        }, merge=True)

    def get_session_level(self, session_id: str) -> Optional[str]:
        level = _data(session_doc(self._db, session_id).get()).get("level") or ""
        return level or None

    def set_session_level(self, session_id: str, level: str) -> None:
        session_doc(self._db, session_id).set({"level": level}, merge=True)

    def get_session_scenario(self, session_id: str):
        d = _data(session_doc(self._db, session_id).get())
        return d.get("scenario_key") or d.get("scenario") or None

    def set_session_scenario(self, session_id: str, scenario_key: str) -> None:
        session_doc(self._db, session_id).set(
            {"scenario_key": scenario_key, "scenario": scenario_key}, merge=True)

    def get_session_repo_url(self, session_id: str):
        url = _data(session_doc(self._db, session_id).get()).get("repo_url") or ""
        return url or None

    def set_session_repo_url(self, session_id: str, url: str) -> None:
        session_doc(self._db, session_id).set({"repo_url": url}, merge=True)

    def get_scenario_starter_url(self, scenario_key: str):
        url = _data(self._db.collection("scenario_config").document(
            scenario_key).get()).get("starter_url") or ""
        return url or None

    def set_scenario_starter_url(self, scenario_key: str, url: str) -> None:
        self._db.collection("scenario_config").document(scenario_key).set(
            {"starter_url": url}, merge=True)

    def get_scenario_enabled(self, scenario_key: str) -> bool:
        snap = self._db.collection("scenario_config").document(scenario_key).get()
        if not snap.exists:
            return True
        val = _data(snap).get("enabled")
        return True if val is None else bool(val)

    def set_scenario_enabled(self, scenario_key: str, enabled: bool) -> None:
        self._db.collection("scenario_config").document(scenario_key).set(
            {"enabled": bool(enabled)}, merge=True)

    def delete_session_settings(self, session_id: str) -> None:
        session_doc(self._db, session_id).set(
            {"level": "", "scenario_key": "", "scenario": "", "repo_url": ""}, merge=True)


class FirestoreSessionFileStore:
    """Browser-edited workspace files: sessions/{sid}/files/{url-encoded path}."""

    def __init__(self, db) -> None:
        self._db = db

    @staticmethod
    def _id(relpath: str) -> str:
        from urllib.parse import quote
        return quote(relpath, safe="")

    def _col(self, session_id: str):
        return session_doc(self._db, session_id).collection("files")

    def put(self, session_id: str, relpath: str, text: str, ts: str) -> None:
        self._col(session_id).document(self._id(relpath)).set(
            {"relpath": relpath, "content": text, "ts": ts})

    def get(self, session_id: str, relpath: str) -> Optional[str]:
        d = _data(self._col(session_id).document(self._id(relpath)).get())
        return d.get("content") if d else None

    def list(self, session_id: str) -> Sequence[str]:
        return sorted(_data(s).get("relpath") or "" for s in self._col(session_id).stream())

    def delete_session(self, session_id: str) -> None:
        col = self._col(session_id)
        for snap in list(col.stream()):
            col.document(snap.id).delete()


class FirestoreSubmissionStore:
    def __init__(self, db) -> None:
        self._db = db

    def save(self, session_id, filename, content, ts, kind="patch") -> Submission:
        col = session_doc(self._db, session_id).collection("submissions")
        seq = _max_int(col, "seq") + 1
        lines = content.count("\n") + 1
        col.document(str(seq)).set({
            "session_id": session_id, "seq": seq, "filename": filename,
            "content": content, "lines": lines, "ts": ts, "kind": kind or "patch",
        })
        return Submission(session_id, seq, filename, content, lines, ts, kind)

    def latest(self, session_id) -> Optional[Submission]:
        rows = self.list(session_id)
        return rows[-1] if rows else None

    def list(self, session_id) -> Sequence[Submission]:
        rows = []
        for snap in session_doc(self._db, session_id).collection("submissions").stream():
            d = _data(snap)
            rows.append(Submission(
                session_id, int(d.get("seq") or 0),
                d.get("filename") or "", d.get("content") or "",
                int(d.get("lines") or 0), d.get("ts") or "",
                d.get("kind") or "patch"))
        rows.sort(key=lambda s: s.seq)
        return rows

    def delete_for_session(self, session_id: str) -> None:
        _delete_collection(session_doc(self._db, session_id).collection("submissions"))


class FirestoreUserDirectory:
    def __init__(self, db) -> None:
        self._db = db

    def get(self, uid: str) -> Optional[UserRecord]:
        snap = self._db.collection("users").document(uid).get()
        return self._row(snap) if snap.exists else None

    def get_by_email(self, email: str) -> Optional[UserRecord]:
        el = (email or "").strip().lower()
        if not el:
            return None
        hits = list(self._db.collection("users").where(
            "email_lower", "==", el).limit(1).stream())
        if hits:
            return self._row(hits[0])
        return None

    def upsert(self, user: UserRecord) -> UserRecord:
        existing = self.get(user.uid)
        if existing is None and user.email:
            existing = self.get_by_email(user.email)
        created = user.created_at or (existing.created_at if existing else _now())
        last = user.last_login or (existing.last_login if existing else "")
        rec = UserRecord(
            uid=user.uid, email=user.email, role=user.role,
            disabled=user.disabled, created_at=created, last_login=last,
            name=user.name,
            groq_key_enc=user.groq_key_enc)
        self._db.collection("users").document(rec.uid).set({
            "uid": rec.uid, "email": rec.email,
            "email_lower": (rec.email or "").lower(),
            "role": rec.role, "disabled": bool(rec.disabled),
            "created_at": rec.created_at, "last_login": rec.last_login,
            "name": rec.name,
            "groq_key_enc": rec.groq_key_enc,
        })
        return rec

    def list(self) -> Sequence[UserRecord]:
        rows = [self._row(s) for s in self._db.collection("users").stream()]
        rows.sort(key=lambda u: u.email.lower())
        return rows

    def delete(self, uid: str) -> bool:
        ref = self._db.collection("users").document(uid)
        if not ref.get().exists:
            return False
        ref.delete()
        return True

    def count_role(self, role: str) -> int:
        return sum(1 for u in self.list() if u.role == role and not u.disabled)

    @staticmethod
    def _row(snap) -> UserRecord:
        d = _data(snap)
        return UserRecord(
            uid=d.get("uid") or snap.id, email=d.get("email") or "",
            role=d.get("role") or "challenger",
            disabled=bool(d.get("disabled")),
            created_at=d.get("created_at") or "",
            last_login=d.get("last_login") or "",
            name=d.get("name") or "",
            groq_key_enc=d.get("groq_key_enc") or "",
        )


class FirestoreSessionRegistry:
    def __init__(self, db) -> None:
        self._db = db

    def get(self, session_id: str) -> Optional[SessionRecord]:
        snap = session_doc(self._db, session_id).get()
        if not snap.exists:
            return None
        return self._row(snap)

    def upsert(self, record: SessionRecord) -> SessionRecord:
        existing = self.get(record.id)
        created = record.created_at or (existing.created_at if existing else _now())
        payload = {
            "owner_uid": record.owner_uid,
            "assignee_uid": record.assignee_uid,
            "scenario_key": record.scenario_key,
            "scenario": record.scenario_key,
            "level": record.level,
            "status": record.status or "assigned",
            "created_at": created,
        }
        session_doc(self._db, record.id).set(payload, merge=True)
        return self.get(record.id)

    def list_all(self) -> Sequence[SessionRecord]:
        rows = [self._row(s) for s in self._db.collection("sessions").stream()]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows

    def list_by_owner(self, uid: str) -> Sequence[SessionRecord]:
        return [r for r in self.list_all() if r.owner_uid == uid]

    def list_by_assignee(self, uid: str) -> Sequence[SessionRecord]:
        return [r for r in self.list_all() if r.assignee_uid == uid]

    def delete(self, session_id: str) -> bool:
        ref = session_doc(self._db, session_id)
        existed = ref.get().exists
        for name in ("messages", "unlock", "mail", "tickets", "submissions"):
            _delete_collection(ref.collection(name))
        if existed:
            ref.delete()
        return existed

    @staticmethod
    def _row(snap) -> SessionRecord:
        d = _data(snap)
        return SessionRecord(
            id=snap.id,
            owner_uid=d.get("owner_uid") or "",
            assignee_uid=d.get("assignee_uid") or "",
            scenario_key=d.get("scenario_key") or d.get("scenario") or "",
            level=d.get("level") or "",
            status=d.get("status") or "assigned",
            created_at=d.get("created_at") or "",
        )


class FirestoreCohortDirectory:
    def __init__(self, db) -> None:
        self._db = db

    def _doc(self, cohort_id: str):
        return self._db.collection("cohorts").document(cohort_id)

    def get(self, cohort_id: str) -> Optional[CohortRecord]:
        snap = self._doc(cohort_id).get()
        return self._row(snap) if snap.exists else None

    def upsert(self, cohort: CohortRecord) -> CohortRecord:
        existing = self.get(cohort.id)
        created = cohort.created_at or (existing.created_at if existing else _now())
        self._doc(cohort.id).set({
            "id": cohort.id, "name": cohort.name,
            "notes": cohort.notes or "", "created_at": created,
        }, merge=True)
        return self.get(cohort.id)

    def list(self) -> Sequence[CohortRecord]:
        rows = [self._row(s) for s in self._db.collection("cohorts").stream()]
        rows.sort(key=lambda c: c.name.lower())
        return rows

    def delete(self, cohort_id: str) -> bool:
        ref = self._doc(cohort_id)
        if not ref.get().exists:
            return False
        _delete_collection(ref.collection("members"))
        ref.delete()
        return True

    def members(self, cohort_id: str) -> Sequence[str]:
        uids = [s.id for s in self._doc(cohort_id).collection("members").stream()]
        uids.sort()
        return uids

    def add_member(self, cohort_id: str, uid: str) -> None:
        self._doc(cohort_id).collection("members").document(uid).set({"uid": uid})

    def remove_member(self, cohort_id: str, uid: str) -> bool:
        ref = self._doc(cohort_id).collection("members").document(uid)
        if not ref.get().exists:
            return False
        ref.delete()
        return True

    def cohorts_for(self, uid: str) -> Sequence[str]:
        return [c.id for c in self.list() if uid in self.members(c.id)]

    def remove_user(self, uid: str) -> None:
        for c in self.list():
            self.remove_member(c.id, uid)

    @staticmethod
    def _row(snap) -> CohortRecord:
        d = _data(snap)
        return CohortRecord(
            id=d.get("id") or snap.id, name=d.get("name") or "",
            notes=d.get("notes") or "", created_at=d.get("created_at") or "",
        )


def _delete_collection(col) -> None:
    snaps = list(col.stream())
    for snap in snaps:
        snap.reference.delete()
