"""Copy a local sim.db into Firestore. Does not delete the SQLite file.

  set PERSISTENCE=firestore
  set FIREBASE_PROJECT_ID=...
  set FIREBASE_CREDENTIALS_JSON=...
  set SIM_DB_PATH=sim.db
  python tools/migrate_sqlite_to_firestore.py
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim.app.config import Config
from sim.adapters.persistence.stores import build_stores
from sim.core.ports.repository import StoredMessage
from sim.core.ports.session_registry import SessionRecord
from sim.core.ports.settings import InstructorSettings
from sim.core.ports.tickets import Ticket
from sim.core.ports.users import UserRecord


def _rows(conn, sql: str):
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql).fetchall()
    except sqlite3.OperationalError:
        return []


def migrate(db_path: str, stores) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    counts = {
        "users": 0, "sessions": 0, "messages": 0, "unlock": 0,
        "mail": 0, "tickets": 0, "submissions": 0, "settings": 0,
    }

    for r in _rows(conn, "SELECT * FROM users"):
        keys = r.keys()
        stores.users.upsert(UserRecord(
            uid=r["uid"], email=r["email"], role=r["role"],
            disabled=bool(r["disabled"]),
            created_at=r["created_at"] or "",
            last_login=r["last_login"] or "",
            name=r["name"] if "name" in keys else "",
            groq_key_enc=r["groq_key_enc"] if "groq_key_enc" in keys else "",
            github_token_enc=r["github_token_enc"] if "github_token_enc" in keys else "",
            github_scope=r["github_scope"] if "github_scope" in keys else "",
            gitlab_token_enc=r["gitlab_token_enc"] if "gitlab_token_enc" in keys else "",
            gitlab_scope=r["gitlab_scope"] if "gitlab_scope" in keys else "",
        ))
        counts["users"] += 1

    for r in _rows(conn, "SELECT * FROM session_registry"):
        stores.session_registry.upsert(SessionRecord(
            id=r["id"], owner_uid=r["owner_uid"] or "",
            assignee_uid=r["assignee_uid"] or "",
            scenario_key=r["scenario_key"] or "",
            level=r["level"] or "", status=r["status"] or "assigned",
            created_at=r["created_at"] or "",
        ))
        counts["sessions"] += 1

    for r in _rows(conn, "SELECT * FROM session_settings"):
        if r["level"]:
            stores.settings.set_session_level(r["session_id"], r["level"])
        if r["scenario"]:
            stores.settings.set_session_scenario(r["session_id"], r["scenario"])
        counts["settings"] += 1

    for r in _rows(conn, "SELECT * FROM instructor_settings WHERE id=1"):
        stores.settings.set_instructor(InstructorSettings(
            bool(r["onboarded"]), r["default_level"] or "senior"))
        counts["settings"] += 1

    for r in _rows(conn, "SELECT * FROM scenario_config"):
        if r["starter_url"]:
            stores.settings.set_scenario_starter_url(r["scenario_key"], r["starter_url"])
        keys = r.keys()
        if "enabled" in keys:
            stores.settings.set_scenario_enabled(r["scenario_key"], bool(r["enabled"]))
        counts["settings"] += 1

    for r in _rows(conn, "SELECT * FROM messages ORDER BY id"):
        stores.repo.append(StoredMessage(
            session_id=r["session_id"], sender=r["sender"],
            channel=r["channel"], content=r["content"],
            ts=r["ts"], kind=r["kind"] or "message",
        ))
        counts["messages"] += 1

    for r in _rows(conn, "SELECT * FROM unlock_state"):
        stores.unlock.set_unlocked(r["session_id"], r["persona_key"], int(r["unlocked"]))
        counts["unlock"] += 1

    for r in _rows(conn, "SELECT * FROM mail_threads"):
        put = getattr(stores.mailstore, "put_thread", None)
        if put:
            put(r["session_id"], r["id"], r["subject"], r["participant"],
                r["created_ts"], r["last_persona_ts"] or "", r["last_read_ts"] or "")
        else:
            th = stores.mailstore.create_thread(
                r["session_id"], r["subject"], r["participant"], r["created_ts"])
            if r["last_persona_ts"]:
                stores.mailstore.touch_persona(
                    r["session_id"], th.id, r["last_persona_ts"])
            if r["last_read_ts"]:
                stores.mailstore.mark_read(r["session_id"], th.id, r["last_read_ts"])
        counts["mail"] += 1

    for r in _rows(conn, "SELECT * FROM tickets ORDER BY seq"):
        keys = r.keys()
        ticket = Ticket(
            r["id"], r["session_id"], r["title"], r["description"], r["status"],
            r["created_by"], r["ts"], seq=r["seq"] or 1,
            issue_type=r["issue_type"] if "issue_type" in keys else "task",
            priority=r["priority"] if "priority" in keys else "medium",
            labels=r["labels"] if "labels" in keys else "")
        put = getattr(stores.ticketstore, "put_ticket", None)
        if put:
            put(ticket)
        else:
            stores.ticketstore.create(
                ticket.session_id, ticket.title, ticket.description, ticket.status,
                ticket.created_by, ticket.ts, issue_type=ticket.issue_type,
                priority=ticket.priority, labels=ticket.labels)
        counts["tickets"] += 1

    for r in _rows(conn, "SELECT * FROM submissions ORDER BY seq"):
        keys = r.keys()
        stores.submissions.save(
            r["session_id"], r["filename"], r["content"], r["ts"],
            kind=r["kind"] if "kind" in keys and r["kind"] else "patch")
        counts["submissions"] += 1

    conn.close()
    return counts


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="", help="SQLite path (default SIM_DB_PATH / sim.db)")
    args = p.parse_args()
    cfg = Config.from_env()
    db_path = args.db or cfg.db_path or "sim.db"
    if not Path(db_path).is_file():
        print(f"SQLite file not found: {db_path}", file=sys.stderr)
        return 1
    if cfg.persistence not in ("firestore", "firebase"):
        print("Set PERSISTENCE=firestore before running this migrator.", file=sys.stderr)
        return 1
    stores = build_stores(cfg)
    counts = migrate(db_path, stores)
    print("Copied:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
