"""pgvector adapter.

Worth serious consideration when the corpus fits in PostgreSQL: authorization
data and vectors live in one system, so there is no cross-store consistency
problem at all. Row-level security can enforce the predicate at the database,
which means even a query that forgets the WHERE clause returns nothing — the
strongest version of this guarantee available in any of these backends.
"""
from __future__ import annotations

from sqlalchemy import text

from app.core.errors import VectorStoreError
from app.db import SessionLocal
from app.vector.base import Chunk, SearchFilter, VectorStore

DENSE_SQL = text("""
    SELECT id::text, document_id::text, text_content, filename, chunk_index,
           source_page, allowed_roles, min_clearance, tenant_id::text,
           1 - (embedding <=> :qvec) AS score
    FROM chunks
    WHERE tenant_id = :tenant
      AND allowed_roles && :roles
      AND min_clearance <= :clearance
    ORDER BY embedding <=> :qvec
    LIMIT :limit
""")

KEYWORD_SQL = text("""
    SELECT id::text, document_id::text, text_content, filename, chunk_index,
           source_page, allowed_roles, min_clearance, tenant_id::text,
           ts_rank(tsv, websearch_to_tsquery('english', :q)) AS score
    FROM chunks
    WHERE tenant_id = :tenant
      AND allowed_roles && :roles
      AND min_clearance <= :clearance
      AND tsv @@ websearch_to_tsquery('english', :q)
    ORDER BY score DESC
    LIMIT :limit
""")


def _row_to_chunk(r) -> Chunk:
    return Chunk(
        id=r.id, document_id=r.document_id, text=r.text_content, score=float(r.score),
        allowed_roles=list(r.allowed_roles), min_clearance=r.min_clearance,
        tenant_id=r.tenant_id, chunk_index=r.chunk_index, source_page=r.source_page,
        filename=r.filename,
    )


class PgVectorStore(VectorStore):
    async def ensure_ready(self, dim: int) -> None:
        async with SessionLocal() as s:
            await s.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await s.execute(text(f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    id UUID PRIMARY KEY,
                    document_id UUID NOT NULL,
                    tenant_id UUID NOT NULL,
                    chunk_index INT NOT NULL,
                    text_content TEXT NOT NULL,
                    filename TEXT NOT NULL DEFAULT '',
                    source_page INT,
                    allowed_roles TEXT[] NOT NULL,
                    min_clearance INT NOT NULL DEFAULT 0,
                    embedding vector({dim}) NOT NULL,
                    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text_content)) STORED
                )"""))
            for ddl in (
                "CREATE INDEX IF NOT EXISTS chunks_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)",
                "CREATE INDEX IF NOT EXISTS chunks_roles ON chunks USING gin (allowed_roles)",
                "CREATE INDEX IF NOT EXISTS chunks_tsv ON chunks USING gin (tsv)",
                "CREATE INDEX IF NOT EXISTS chunks_scope ON chunks (tenant_id, min_clearance)",
                "CREATE INDEX IF NOT EXISTS chunks_doc ON chunks (document_id)",
            ):
                await s.execute(text(ddl))
            await s.commit()

    async def _run(self, sql, params) -> list[Chunk]:
        try:
            async with SessionLocal() as s:
                rows = (await s.execute(sql, params)).fetchall()
        except Exception as exc:
            raise VectorStoreError(str(exc)) from exc
        return [_row_to_chunk(r) for r in rows]

    async def dense_search(self, vector, *, flt: SearchFilter, limit: int) -> list[Chunk]:
        return await self._run(DENSE_SQL, {
            "qvec": str(vector), "tenant": flt.tenant_id,
            "roles": flt.roles, "clearance": flt.clearance, "limit": limit,
        })

    async def keyword_search(self, text_query: str, *, flt: SearchFilter, limit: int) -> list[Chunk]:
        return await self._run(KEYWORD_SQL, {
            "q": text_query, "tenant": flt.tenant_id,
            "roles": flt.roles, "clearance": flt.clearance, "limit": limit,
        })

    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        async with SessionLocal() as s:
            for c, v in zip(chunks, vectors, strict=True):
                await s.execute(text("""
                    INSERT INTO chunks (id, document_id, tenant_id, chunk_index, text_content,
                                        filename, source_page, allowed_roles, min_clearance, embedding)
                    VALUES (:id, :doc, :tenant, :idx, :txt, :fn, :page, :roles, :clr, :emb)
                    ON CONFLICT (id) DO UPDATE SET
                        text_content = EXCLUDED.text_content,
                        allowed_roles = EXCLUDED.allowed_roles,
                        min_clearance = EXCLUDED.min_clearance,
                        embedding = EXCLUDED.embedding
                """), {
                    "id": c.id, "doc": c.document_id, "tenant": c.tenant_id,
                    "idx": c.chunk_index, "txt": c.text, "fn": c.filename,
                    "page": c.source_page, "roles": c.allowed_roles,
                    "clr": c.min_clearance, "emb": str(v),
                })
            await s.commit()

    async def delete_document(self, document_id: str) -> int:
        async with SessionLocal() as s:
            res = await s.execute(text("DELETE FROM chunks WHERE document_id = :d"), {"d": document_id})
            await s.commit()
            return res.rowcount or 0

    async def count_document(self, document_id: str) -> int:
        async with SessionLocal() as s:
            return (await s.execute(
                text("SELECT count(*) FROM chunks WHERE document_id = :d"), {"d": document_id}
            )).scalar_one()

    async def unfiltered_count_for_debug(self, vector, *, tenant_id: str, limit: int) -> list[str]:
        async with SessionLocal() as s:
            rows = (await s.execute(text("""
                SELECT document_id::text FROM chunks WHERE tenant_id = :t
                ORDER BY embedding <=> :qvec LIMIT :limit
            """), {"t": tenant_id, "qvec": str(vector), "limit": limit})).fetchall()
        return [r[0] for r in rows]
