"""Build a Firestore client. Imported only when PERSISTENCE=firestore."""
from __future__ import annotations

import os


def make_firestore_client(config):
    project = (getattr(config, "firebase_project_id", "") or "").strip()
    if not project:
        raise RuntimeError(
            "PERSISTENCE=firestore requires FIREBASE_PROJECT_ID")
    from google.cloud import firestore
    from sim.adapters.auth.service_account import service_account_credentials
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return firestore.Client(project=project)
    creds = service_account_credentials(
        getattr(config, "firebase_credentials_json", "") or "")
    if creds is not None:
        return firestore.Client(project=project, credentials=creds)
    try:
        return firestore.Client(project=project)
    except Exception as e:
        raise RuntimeError(
            "PERSISTENCE=firestore needs a service-account JSON "
            "(FIREBASE_CREDENTIALS_JSON as a path or inline JSON, "
            "or GOOGLE_APPLICATION_CREDENTIALS)"
        ) from e


def session_doc(db, session_id: str):
    return db.collection("sessions").document(_id(session_id))


def _id(value: str) -> str:
    text = (value or "").strip()
    if not text or "/" in text or text in (".", ".."):
        raise ValueError("invalid Firestore document id")
    return text
