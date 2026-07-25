"""Audit writes. Ids and counts only."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal
from app.models import AuditLog
from app.vector.base import Chunk


async def record_query(
    db: AsyncSession,
    principal: Principal,
    query: str,
    chunks: list[Chunk],
    grounded: bool | None = None,
) -> None:
    db.add(AuditLog(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        role_name=principal.role,
        query=query,
        chunk_ids=[c.id for c in chunks],   # never c.text
        returned=len(chunks),
        grounded=grounded,
    ))
    await db.commit()
