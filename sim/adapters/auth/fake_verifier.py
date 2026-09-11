from __future__ import annotations

from sim.core.ports.identity import IdentityError, Principal, ROLES


class FakeVerifier:
    """Deterministic verifier for tests.

    Token shapes:
      fake:<uid>:<role>
      fake:<uid>:<role>:<email>
    """

    def verify(self, token: str) -> Principal:
        raw = (token or "").strip()
        if raw.lower().startswith("bearer "):
            raw = raw[7:].strip()
        if not raw.startswith("fake:"):
            raise IdentityError("invalid fake token")
        parts = raw.split(":")
        if len(parts) < 3:
            raise IdentityError("invalid fake token")
        uid, role = parts[1], parts[2]
        email = parts[3] if len(parts) > 3 else f"{uid}@test.local"
        if not uid:
            raise IdentityError("invalid fake token")
        if role not in ROLES:
            role = "challenger"
        return Principal(uid=uid, email=email, role=role)
