"""Ingestion.

Two invariants:
  1. A chunk is never written without labels. Not "written then labelled" —
     there is no window in which an unlabelled chunk is searchable, because a
     default-public chunk is a breach while an over-restricted one is a ticket.
  2. Failure cleans up vector points. An orphaned labelled point is invisible;
     an orphaned unlabelled point is the thing we are preventing.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnlabeledChunkError
from app.core.logging import get_logger
from app.models import Document, Role
from app.retrieval.embeddings import get_embedder
from app.services.chunker import chunk_text
from app.vector import Chunk, get_store

log = get_logger("ingest")


@dataclass(slots=True)
class Labels:
    allowed_roles: list[str]
    min_clearance: int

    def validate_against(self, known_roles: set[str]) -> None:
        if not self.allowed_roles:
            raise UnlabeledChunkError("refusing to index a document with no role labels")
        unknown = set(self.allowed_roles) - known_roles
        if unknown:
            # Free-text role names are how a typo becomes a document nobody can
            # read, or worse, a filter expression that matches unexpectedly.
            raise UnlabeledChunkError(f"unknown roles: {sorted(unknown)}")
        if not 0 <= self.min_clearance <= 100:
            raise UnlabeledChunkError("min_clearance out of range")


async def known_role_names(db: AsyncSession, tenant_id: str) -> set[str]:
    rows = await db.execute(select(Role.name).where(Role.tenant_id == tenant_id))
    return {r[0] for r in rows}


async def ingest_document(
    db: AsyncSession,
    *,
    document_id: str,
    tenant_id: str,
    filename: str,
    raw_text: str,
    labels: Labels,
) -> int:
    labels.validate_against(await known_role_names(db, tenant_id))

    # Admin is added to every document's allowlist rather than given a bypass
    # branch in the filter. Same effect, one fewer code path that skips the
    # security check.
    roles = sorted(set(labels.allowed_roles) | {"Admin"})

    store = get_store()
    embedder = get_embedder()

    pieces = chunk_text(raw_text)
    if not pieces:
        await db.execute(update(Document).where(Document.id == document_id)
                         .values(status="failed"))
        await db.commit()
        return 0

    chunks = [
        Chunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            tenant_id=tenant_id,
            text=p.text,
            chunk_index=p.index,
            source_page=p.page,
            filename=filename,
            allowed_roles=roles,
            min_clearance=labels.min_clearance,
        )
        for p in pieces
    ]

    for c in chunks:
        if not c.allowed_roles or not c.tenant_id:
            raise UnlabeledChunkError(f"chunk {c.id} missing labels")

    await db.execute(update(Document).where(Document.id == document_id)
                     .values(status="indexing"))
    await db.commit()

    try:
        vectors = await embedder.embed_batch([c.text for c in chunks])
        await store.upsert(chunks, vectors)
        await db.execute(
            update(Document).where(Document.id == document_id).values(
                status="indexed",
                chunk_count=len(chunks),
                indexed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        log.info("ingest_complete", document_id=document_id, chunks=len(chunks), roles=roles)
        return len(chunks)
    except Exception as exc:                                    # noqa: BLE001
        await store.delete_document(document_id)
        await db.execute(update(Document).where(Document.id == document_id)
                         .values(status="failed"))
        await db.commit()
        log.error("ingest_failed", document_id=document_id, error=str(exc))
        raise


async def delete_document(db: AsyncSession, document_id: str) -> None:
    """Vector points first, verify, then the relational row.

    A dangling PostgreSQL row is a cleanup task. A dangling vector point is a
    document you believe is deleted and isn't.
    """
    store = get_store()
    await db.execute(update(Document).where(Document.id == document_id)
                     .values(status="deleting"))
    await db.commit()

    await store.delete_document(document_id)
    remaining = await store.count_document(document_id)
    if remaining:
        raise RuntimeError(f"{remaining} vector points survived deletion of {document_id}")

    doc = await db.get(Document, document_id)
    if doc:
        await db.delete(doc)
        await db.commit()
    log.info("document_deleted", document_id=document_id)


async def reclassify(db: AsyncSession, document_id: str, labels: Labels, tenant_id: str) -> None:
    """Re-labelling requires updating every point's payload.

    Do not be tempted to join against PostgreSQL at query time instead — that is
    post-filtering wearing a disguise.
    """
    labels.validate_against(await known_role_names(db, tenant_id))
    doc = await db.get(Document, document_id)
    if not doc:
        raise LookupError(document_id)
    raise NotImplementedError(
        "Re-index the document's chunks with the new labels, or implement a "
        "payload-update path in the store adapter. Payload updates are cheap in "
        "Qdrant (no re-embedding) — design for this rather than avoiding it."
    )
