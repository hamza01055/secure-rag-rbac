from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_principal, require_admin
from app.core.principal import Principal
from app.db import get_session
from app.models import Document, Role
from app.services.ingest import Labels, delete_document, ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
async def list_documents(p: Principal = Depends(get_principal),
                         db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(
        select(Document).where(Document.tenant_id == p.tenant_id)
    )).scalars().all()
    # Non-admins see only documents their role can read. Listing a filename is
    # itself a disclosure: "Executive_Compensation_2026.xlsx" tells you plenty.
    return [
        {"id": str(d.id), "filename": d.filename, "status": d.status,
         "chunk_count": d.chunk_count, "min_clearance": d.min_clearance,
         "allowed_roles": [r.name for r in d.roles]}
        for d in rows
        if p.is_admin or (p.role in {r.name for r in d.roles} and p.clearance >= d.min_clearance)
    ]


@router.post("", status_code=201)
async def upload(
    file: UploadFile = File(...),
    allowed_roles: str = Form(...),          # comma-separated; no default
    min_clearance: int = Form(...),
    admin: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    roles = [r.strip() for r in allowed_roles.split(",") if r.strip()]
    if not roles:
        raise HTTPException(422, "at least one role is required")

    raw = (await file.read()).decode("utf-8", errors="replace")
    doc_id = str(uuid.uuid4())

    db.add(Document(
        id=doc_id, tenant_id=admin.tenant_id, filename=file.filename or "untitled",
        storage_key=f"local://{doc_id}", uploaded_by=admin.user_id,
        min_clearance=min_clearance, status="pending",
    ))
    await db.commit()

    count = await ingest_document(
        db, document_id=doc_id, tenant_id=admin.tenant_id,
        filename=file.filename or "untitled", raw_text=raw,
        labels=Labels(allowed_roles=roles, min_clearance=min_clearance),
    )
    return {"document_id": doc_id, "chunks": count}


@router.delete("/{document_id}", status_code=204)
async def remove(document_id: str, admin: Principal = Depends(require_admin),
                 db: AsyncSession = Depends(get_session)):
    await delete_document(db, document_id)
