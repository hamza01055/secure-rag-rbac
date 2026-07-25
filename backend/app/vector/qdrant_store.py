"""Qdrant adapter."""
from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchAny, MatchText, MatchValue,
    PointStruct, Range, VectorParams,
)

from app.core.config import settings
from app.core.errors import VectorStoreError
from app.vector.base import Chunk, SearchFilter, VectorStore


def _to_qdrant(flt: SearchFilter) -> Filter:
    """Tenant AND role-membership AND clearance-threshold. All three, always."""
    return Filter(
        must=[
            FieldCondition(key="tenant_id", match=MatchValue(value=flt.tenant_id)),
            FieldCondition(key="allowed_roles", match=MatchAny(any=flt.roles)),
            FieldCondition(key="min_clearance", range=Range(lte=flt.clearance)),
        ]
    )


def _to_chunk(point) -> Chunk:
    p = point.payload or {}
    return Chunk(
        id=str(point.id),
        document_id=p.get("document_id", ""),
        text=p.get("text_content", ""),
        score=float(getattr(point, "score", 0.0) or 0.0),
        allowed_roles=p.get("allowed_roles", []),
        min_clearance=p.get("min_clearance", 0),
        tenant_id=p.get("tenant_id", ""),
        chunk_index=p.get("chunk_index", 0),
        source_page=p.get("source_page"),
        filename=p.get("filename", ""),
    )


class QdrantStore(VectorStore):
    def __init__(self, url: str | None = None, collection: str | None = None):
        self.client = AsyncQdrantClient(url=url or settings.qdrant_url)
        self.collection = collection or settings.qdrant_collection

    async def ensure_ready(self, dim: int) -> None:
        existing = {c.name for c in (await self.client.get_collections()).collections}
        if self.collection not in existing:
            await self.client.create_collection(
                self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
        for field, schema in (
            ("tenant_id", "keyword"),
            ("allowed_roles", "keyword"),
            ("min_clearance", "integer"),
            ("document_id", "keyword"),
            ("text_content", "text"),
        ):
            try:
                await self.client.create_payload_index(self.collection, field, field_schema=schema)
            except Exception:
                pass  # already exists

    async def dense_search(self, vector, *, flt: SearchFilter, limit: int) -> list[Chunk]:
        try:
            hits = await self.client.search(
                collection_name=self.collection,
                query_vector=vector,
                query_filter=_to_qdrant(flt),
                limit=limit,
                with_payload=True,
            )
        except Exception as exc:
            raise VectorStoreError(str(exc)) from exc
        return [_to_chunk(h) for h in hits]

    async def keyword_search(self, text: str, *, flt: SearchFilter, limit: int) -> list[Chunk]:
        base = _to_qdrant(flt)
        base.must.append(FieldCondition(key="text_content", match=MatchText(text=text)))
        try:
            points, _ = await self.client.scroll(
                collection_name=self.collection,
                scroll_filter=base,
                limit=limit,
                with_payload=True,
            )
        except Exception as exc:
            raise VectorStoreError(str(exc)) from exc
        return [_to_chunk(p) for p in points]

    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        points = [
            PointStruct(
                id=c.id,
                vector=v,
                payload={
                    "document_id": c.document_id,
                    "tenant_id": c.tenant_id,
                    "chunk_index": c.chunk_index,
                    "text_content": c.text,
                    "allowed_roles": c.allowed_roles,
                    "min_clearance": c.min_clearance,
                    "source_page": c.source_page,
                    "filename": c.filename,
                },
            )
            for c, v in zip(chunks, vectors, strict=True)
        ]
        await self.client.upsert(self.collection, points=points, wait=True)

    def _doc_filter(self, document_id: str) -> Filter:
        return Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))])

    async def delete_document(self, document_id: str) -> int:
        before = await self.count_document(document_id)
        await self.client.delete(self.collection, points_selector=self._doc_filter(document_id), wait=True)
        return before

    async def count_document(self, document_id: str) -> int:
        res = await self.client.count(self.collection, count_filter=self._doc_filter(document_id), exact=True)
        return res.count

    async def unfiltered_count_for_debug(self, vector, *, tenant_id: str, limit: int) -> list[str]:
        hits = await self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            query_filter=Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]),
            limit=limit,
            with_payload=["document_id"],
        )
        return [(h.payload or {}).get("document_id", "") for h in hits]
