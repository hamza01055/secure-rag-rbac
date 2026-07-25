"""Developer console backing endpoint.

Three constraints, all load-bearing:
  1. Counts and ids, never excluded text. The moment it returns what a user was
     blocked from seeing, it *is* the vulnerability it was built to detect.
  2. Admin-gated and flag-gated, and it 404s rather than 403s when disabled —
     a 403 tells an attacker the endpoint exists.
  3. Refuses production. Enforced at startup, not here, so a misconfiguration
     is loud at boot instead of quiet at runtime.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import require_admin
from app.core.principal import Principal
from app.db import get_session
from app.models import User
from app.retrieval import build_filter, retrieve
from app.retrieval.embeddings import get_embedder
from app.schemas import TraceRequest
from app.vector import get_store

router = APIRouter(prefix="/api/debug", tags=["debug"])


def _guard() -> None:
    if not settings.debug_trace or settings.env == "production":
        raise HTTPException(404)


@router.post("/retrieval-trace")
async def retrieval_trace(
    body: TraceRequest,
    admin: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    _guard()

    stmt = select(User).options(selectinload(User.role)).where(User.email == body.as_user)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "no such user")

    subject = Principal(
        user_id=str(user.id), email=user.email, role=user.role.name,
        clearance=user.role.clearance_level, tenant_id=str(user.tenant_id),
        is_admin=user.role.name == "Admin",
    )

    flt = build_filter(subject)
    result = await retrieve(body.query, principal=subject, k=body.k)

    # The one unfiltered call in the system, confined to this guarded endpoint,
    # returning document ids only so the console can show an excluded count.
    vector = await get_embedder().embed_query(body.query)
    all_ids = await get_store().unfiltered_count_for_debug(
        vector, tenant_id=subject.tenant_id, limit=body.k
    )
    permitted_ids = {c.document_id for c in result.chunks}
    excluded_ids = sorted(set(all_ids) - permitted_ids)

    return {
        "principal": {
            "email": subject.email, "role": subject.role,
            "clearance": subject.clearance, "tenant_id": subject.tenant_id,
        },
        "filter": flt.as_dict(),
        "rewritten_query": result.rewritten_query,
        "candidates_considered": result.candidates_considered,
        "stage_ms": result.stage_ms,
        "permitted": [
            {**c.redacted(), "preview": c.text[:240], "filename": c.filename}
            for c in result.chunks
        ],
        "excluded_count": max(0, len(all_ids) - len(permitted_ids)),
        "excluded_document_ids": excluded_ids,
    }
