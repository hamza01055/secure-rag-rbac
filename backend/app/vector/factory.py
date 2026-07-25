from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.vector.base import VectorStore


@lru_cache
def get_store() -> VectorStore:
    if settings.vector_backend == "qdrant":
        from app.vector.qdrant_store import QdrantStore
        return QdrantStore()
    if settings.vector_backend == "pgvector":
        from app.vector.pgvector_store import PgVectorStore
        return PgVectorStore()
    raise RuntimeError(f"unknown vector backend: {settings.vector_backend}")
