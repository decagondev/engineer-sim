"""Auth wiring used by the web adapter. Not imported by sim/core."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Mapping

from sim.core.access.policy import can_access_session, can_admin, can_grade, can_use_instructor_api
from sim.core.ports.identity import IdentityError, IdentityVerifier, Principal
from sim.core.ports.session_registry import SessionRecord, SessionRegistry
from sim.core.ports.users import UserDirectory, UserRecord

LOCAL_INSTRUCTOR_UID = "local-instructor"
LOCAL_INSTRUCTOR_EMAIL = "instructor@local"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _login_is_fresh(last_login: str, ttl_sec: int = 900) -> bool:
    if not last_login:
        return False
    try:
        prev = datetime.fromisoformat(last_login.replace("Z", "+00:00"))
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - prev < timedelta(seconds=ttl_sec)
    except ValueError:
        return False


class AuthServices:
    def __init__(
        self,
        mode: str,
        *,
        password: str = "",
        verifier: IdentityVerifier | None = None,
        users: UserDirectory | None = None,
        sessions: SessionRegistry | None = None,
        bootstrap_admin_email: str = "",
        firebase_api_key: str = "",
        firebase_auth_domain: str = "",
        firebase_project_id: str = "",
        firebase: IdentityVerifier | None = None,
    ) -> None:
        self.mode = (mode or "password").lower()
        self.password = password
        self.verifier = verifier
        self.users = users
        self.sessions = sessions
        self.bootstrap_admin_email = (bootstrap_admin_email or "").strip().lower()
        self.firebase_api_key = firebase_api_key
        self.firebase_auth_domain = firebase_auth_domain
        self.firebase_project_id = firebase_project_id
        self.firebase = firebase  # extra methods create_email_user / send_password_reset

    @property
    def gated(self) -> bool:
        return self.mode in ("firebase", "fake")

    def public_config(self) -> dict:
        out = {"auth_mode": self.mode, "firebase": None}
        if self.mode == "firebase":
            out["firebase"] = {
                "apiKey": self.firebase_api_key,
                "authDomain": self.firebase_auth_domain,
                "projectId": self.firebase_project_id,
            }
        return out

    def token_from_headers(self, headers: Mapping[str, str]) -> str:
        authz = headers.get("authorization") or headers.get("Authorization") or ""
        if authz.lower().startswith("bearer "):
            return authz[7:].strip()
        if self.mode == "fake":
            uid = headers.get("x-test-uid") or headers.get("X-Test-Uid") or ""
            role = headers.get("x-test-role") or headers.get("X-Test-Role") or "challenger"
            email = headers.get("x-test-email") or headers.get("X-Test-Email") or ""
            if uid:
                return f"fake:{uid}:{role}:{email}" if email else f"fake:{uid}:{role}"
        return ""

    def principal_from_token(self, token: str) -> Principal:
        if not self.gated:
            raise IdentityError("token auth disabled")
        if self.verifier is None:
            raise IdentityError("no verifier configured", status=503)
        if not token:
            raise IdentityError("missing token")
        principal = self.verifier.verify(token)
        return self._sync_directory(principal)

    def principal_from_headers(self, headers: Mapping[str, str]) -> Principal:
        return self.principal_from_token(self.token_from_headers(headers))

    def _sync_directory(self, p: Principal) -> Principal:
        if self.users is None:
            return p
        rec = self.users.get(p.uid) or (
            self.users.get_by_email(p.email) if p.email else None)
        if rec is None:
            role = p.role or "challenger"
            if (self.bootstrap_admin_email and p.email
                    and p.email.lower() == self.bootstrap_admin_email
                    and self.users.count_role("admin") == 0):
                role = "admin"
            rec = self.users.upsert(UserRecord(
                uid=p.uid, email=p.email or f"{p.uid}@unknown.local",
                role=role, disabled=False, created_at=_now(), last_login=_now(),
            ))
        else:
            email = p.email or rec.email
            if email != rec.email or not _login_is_fresh(rec.last_login):
                rec = self.users.upsert(UserRecord(
                    uid=rec.uid, email=email, role=rec.role,
                    disabled=rec.disabled, created_at=rec.created_at,
                    last_login=_now(), name=rec.name,
                    groq_key_enc=rec.groq_key_enc,
                ))
        if rec.disabled:
            raise IdentityError("account disabled", status=403)
        return Principal(
            uid=rec.uid, email=rec.email, role=rec.role,
            disabled=False, email_verified=p.email_verified,
        )

    def session(self, session_id: str) -> SessionRecord | None:
        if self.sessions is None:
            return None
        return self.sessions.get(session_id)

    def touch_session(self, session_id: str, *, owner_uid: str = "",
                      assignee_uid: str | None = None, scenario_key: str = "",
                      level: str = "", status: str = "") -> SessionRecord | None:
        if self.sessions is None:
            return None
        existing = self.sessions.get(session_id)
        rec = SessionRecord(
            id=session_id,
            owner_uid=owner_uid or (existing.owner_uid if existing else ""),
            assignee_uid=(existing.assignee_uid if existing else "")
            if assignee_uid is None else assignee_uid,
            scenario_key=scenario_key or (existing.scenario_key if existing else ""),
            level=level or (existing.level if existing else ""),
            status=status or (existing.status if existing else "assigned"),
            created_at=existing.created_at if existing else _now(),
        )
        return self.sessions.upsert(rec)

    def allow_session(self, principal: Principal, session_id: str,
                      *, mutate: bool = False, grade: bool = False) -> bool:
        rec = self.session(session_id)
        if grade:
            return can_grade(principal, rec)
        return can_access_session(principal, rec, mutate=mutate)

    def allow_instructor(self, principal: Principal) -> bool:
        return can_use_instructor_api(principal)

    def allow_admin(self, principal: Principal) -> bool:
        return can_admin(principal)
