"""Persistence factory. Core never imports this — composition_root / manager do."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Stores:
    repo: object
    unlock: object
    mailstore: object
    ticketstore: object
    settings: object
    submissions: object
    users: object
    session_registry: object
    cohorts: object
    session_files: object = None


def build_stores(config) -> Stores:
    mode = (getattr(config, "persistence", None) or "sqlite").lower()
    if mode in ("firestore", "firebase"):
        from sim.adapters.persistence.firestore_client import make_firestore_client
        from sim.adapters.persistence.firestore_store import (
            FirestoreMailStore, FirestoreMessageRepository,
            FirestoreSessionRegistry, FirestoreSettingsStore,
            FirestoreSubmissionStore, FirestoreTicketStore,
            FirestoreCohortDirectory, FirestoreUnlockStore, FirestoreUserDirectory,
            FirestoreSessionFileStore,
        )
        db = make_firestore_client(config)
        return Stores(
            repo=FirestoreMessageRepository(db),
            unlock=FirestoreUnlockStore(db),
            mailstore=FirestoreMailStore(db),
            ticketstore=FirestoreTicketStore(db),
            settings=FirestoreSettingsStore(db),
            submissions=FirestoreSubmissionStore(db),
            users=FirestoreUserDirectory(db),
            session_registry=FirestoreSessionRegistry(db),
            cohorts=FirestoreCohortDirectory(db),
            session_files=FirestoreSessionFileStore(db),
        )
    if mode != "sqlite":
        raise ValueError(f"unknown PERSISTENCE: {mode!r}")
    from sim.adapters.persistence.sqlite_mail import SqliteMailStore
    from sim.adapters.persistence.sqlite_repo import SqliteMessageRepository
    from sim.adapters.persistence.sqlite_sessions import SqliteSessionRegistry
    from sim.adapters.persistence.sqlite_settings import SqliteSettingsStore
    from sim.adapters.persistence.sqlite_state import SqliteUnlockStore
    from sim.adapters.persistence.sqlite_submissions import SqliteSubmissionStore
    from sim.adapters.persistence.sqlite_tickets import SqliteTicketStore
    from sim.adapters.persistence.sqlite_cohorts import SqliteCohortDirectory
    from sim.adapters.persistence.sqlite_users import SqliteUserDirectory
    from sim.adapters.persistence.sqlite_session_files import SqliteSessionFileStore
    path = config.db_path
    return Stores(
        repo=SqliteMessageRepository(path),
        unlock=SqliteUnlockStore(path),
        mailstore=SqliteMailStore(path),
        ticketstore=SqliteTicketStore(path),
        settings=SqliteSettingsStore(path),
        submissions=SqliteSubmissionStore(path),
        users=SqliteUserDirectory(path),
        session_registry=SqliteSessionRegistry(path),
        cohorts=SqliteCohortDirectory(path),
        session_files=SqliteSessionFileStore(path),
    )
