from __future__ import annotations

import os

# Configuration is strict by design: the app refuses to boot without a real
# secret and a database URL. Tests supply throwaway values rather than relaxing
# the validator, so the production guardrail stays exactly as strict as it reads.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault("EMBEDDING_PROVIDER", "local")

import pytest

from app.core.principal import Principal
from app.vector.base import Chunk


def make_principal(role: str = "Engineering", clearance: int = 40,
                   tenant: str = "t-1") -> Principal:
    return Principal(user_id="u-1", email=f"{role.lower()}@acme.test", role=role,
                     clearance=clearance, tenant_id=tenant, is_admin=role == "Admin")


def make_chunk(cid: str, text: str, *, roles: list[str] | None = None,
               clearance: int = 0, doc: str = "d-1", idx: int = 0,
               score: float = 0.5, tenant: str = "t-1") -> Chunk:
    return Chunk(id=cid, document_id=doc, text=text, score=score,
                 allowed_roles=roles or ["Engineering", "Admin"],
                 min_clearance=clearance, tenant_id=tenant, chunk_index=idx)


@pytest.fixture
def intern() -> Principal:
    return make_principal("Intern", 10)


@pytest.fixture
def hr() -> Principal:
    return make_principal("HR", 60)
