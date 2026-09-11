"""Pure authorization: Principal + resource → allow. No I/O, no Firebase."""
from __future__ import annotations

from sim.core.ports.identity import Principal
from sim.core.ports.session_registry import SessionRecord


def is_admin(p: Principal | None) -> bool:
    return bool(p) and not p.disabled and p.role == "admin"


def is_instructor(p: Principal | None) -> bool:
    return bool(p) and not p.disabled and p.role in ("instructor", "admin")


def is_challenger(p: Principal | None) -> bool:
    return bool(p) and not p.disabled and p.role == "challenger"


def can_admin(p: Principal | None) -> bool:
    return is_admin(p)


def can_use_instructor_api(p: Principal | None) -> bool:
    return is_instructor(p)


def can_access_session(p: Principal | None, rec: SessionRecord | None,
                       *, mutate: bool = False) -> bool:
    """Admin: all. Instructor: owned. Challenger: assigned (read or mutate)."""
    if p is None or p.disabled:
        return False
    if p.role == "admin":
        return True
    if rec is None:
        # unknown session: instructors may create/assign; challengers may not
        return p.role == "instructor" and mutate
    if p.role == "instructor":
        return rec.owner_uid == p.uid
    if p.role == "challenger":
        return rec.assignee_uid == p.uid
    return False


def can_grade(p: Principal | None, rec: SessionRecord | None) -> bool:
    if p is None or p.disabled:
        return False
    if p.role == "admin":
        return True
    if rec is None:
        return False
    if p.role == "instructor":
        return rec.owner_uid == p.uid
    if p.role == "challenger":
        return rec.assignee_uid == p.uid
    return False


def can_claim_session(p: Principal | None, rec: SessionRecord | None) -> bool:
    if not is_challenger(p) or rec is None:
        return False
    return rec.assignee_uid == "" or rec.assignee_uid == p.uid
