"""Store-agnostic interface.

The abstraction exists so that switching Qdrant for pgvector changes one module
rather than the security boundary. Note what the interface does NOT offer: there
is no `search()` overload without a filter. The unfiltered count used by the
debug console is a separate, explicitly named method so it cannot be reached by
accident.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class Chunk:
    id: str
    document_id: str
    text: str
    score: float = 0.0
    allowed_roles: list[str] = field(default_factory=list)
    min_clearance: int = 0
    tenant_id: str = ""
    chunk_index: int = 0
    source_page: int | None = None
    filename: str = ""
    vector: list[float] | None = None

    def redacted(self) -> dict[str, Any]:
        """Safe for logs and the debug console: no text."""
        return {
            "id": self.id,
            "document_id": self.document_id,
            "score": round(self.score, 5),
            "allowed_roles": self.allowed_roles,
            "min_clearance": self.min_clearance,
        }


@dataclass(slots=True)
class SearchFilter:
    """A concrete authorization predicate, built only by app.retrieval.filters."""

    tenant_id: str
    roles: list[str]
    clearance: int

    def is_empty(self) -> bool:
        return not self.tenant_id or not self.roles

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "allowed_roles_any_of": self.roles,
            "min_clearance_lte": self.clearance,
        }


class Embedder(Protocol):
    async def embed_query(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(ABC):
    @abstractmethod
    async def ensure_ready(self, dim: int) -> None:
        """Create the collection and the payload indexes.

        The payload indexes are not an optimization. Without them the filter is
        a linear scan, which makes someone eventually propose removing it.
        """

    @abstractmethod
    async def dense_search(
        self, vector: list[float], *, flt: SearchFilter, limit: int
    ) -> list[Chunk]: ...

    @abstractmethod
    async def keyword_search(
        self, text: str, *, flt: SearchFilter, limit: int
    ) -> list[Chunk]:
        """Lexical search over the SAME filtered subset as dense_search.

        A hybrid pipeline where only one branch is filtered is a leak with an
        extra step.
        """

    @abstractmethod
    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...

    @abstractmethod
    async def delete_document(self, document_id: str) -> int: ...

    @abstractmethod
    async def count_document(self, document_id: str) -> int: ...

    @abstractmethod
    async def unfiltered_count_for_debug(
        self, vector: list[float], *, tenant_id: str, limit: int
    ) -> list[str]:
        """Document ids matching WITHOUT the authorization predicate.

        The only unfiltered path in the system. It exists solely so the
        developer console can display an excluded count, it returns ids rather
        than text, and it is reachable only from the admin-gated, flag-gated,
        production-disabled debug router.
        """
