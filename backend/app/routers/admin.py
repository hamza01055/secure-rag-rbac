from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.core.principal import Principal
from app.db import get_session
from app.models import AuditLog, Document, Role, User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/roles")
async def roles(admin: Principal = Depends(require_admin), db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(Role).where(Role.tenant_id == admin.tenant_id))).scalars().all()
    return [{"id": str(r.id), "name": r.name, "clearance_level": r.clearance_level} for r in rows]


@router.get("/users")
async def users(admin: Principal = Depends(require_admin), db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(User).where(User.tenant_id == admin.tenant_id))).scalars().all()
    return [{"id": str(u.id), "email": u.email, "role": u.role.name,
             "clearance": u.role.clearance_level, "is_active": u.is_active} for u in rows]


@router.post("/users/{user_id}/deactivate")
async def deactivate(user_id: str, admin: Principal = Depends(require_admin),
                     db: AsyncSession = Depends(get_session)):
    user = await db.get(User, user_id)
    if user:
        user.is_active = False
        await db.commit()
    # Takes effect on the caller's very next request, because get_principal
    # re-reads the user rather than trusting the token's claims.
    return {"ok": True}


@router.get("/stats")
async def stats(admin: Principal = Depends(require_admin), db: AsyncSession = Depends(get_session)):
    docs = (await db.execute(select(func.count(Document.id))
                             .where(Document.tenant_id == admin.tenant_id))).scalar_one()
    queries = (await db.execute(select(func.count(AuditLog.id))
                                .where(AuditLog.tenant_id == admin.tenant_id))).scalar_one()
    empty = (await db.execute(select(func.count(AuditLog.id))
                              .where(AuditLog.tenant_id == admin.tenant_id,
                                     AuditLog.returned == 0))).scalar_one()
    ungrounded = (await db.execute(select(func.count(AuditLog.id))
                                   .where(AuditLog.tenant_id == admin.tenant_id,
                                          AuditLog.grounded.is_(False)))).scalar_one()
    # A spike in zero-result queries usually means a filter bug, not a corpus
    # gap. Worth an alert rather than a dashboard nobody opens.
    return {"documents": docs, "queries": queries,
            "zero_result_queries": empty, "ungrounded_answers": ungrounded}
