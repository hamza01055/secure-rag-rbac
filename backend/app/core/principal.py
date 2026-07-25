"""The caller's identity. Constructed server-side only."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """Immutable. Nothing downstream can widen its own permissions mid-request.

    Constructed only from a validated token plus a database read. There is no
    constructor path that accepts request-supplied fields, which is the point:
    a role that arrives in a request body is an authorization bypass with extra
    steps.
    """

    user_id: str
    email: str
    role: str
    clearance: int
    tenant_id: str
    is_admin: bool = False

    def audit_dict(self) -> dict[str, str | int]:
        return {
            "user_id": self.user_id,
            "role": self.role,
            "clearance": self.clearance,
            "tenant_id": self.tenant_id,
        }
