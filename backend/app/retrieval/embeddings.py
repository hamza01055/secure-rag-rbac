"""Embedding provider.

Ingest and query must use the same model and the same normalization. A mismatch
degrades relevance quietly and gets misdiagnosed as a filter bug for days, so
the model name is pinned in config and recorded with every indexed document.
"""
from __future__ import annotations

import hashlib
import math

from app.core.config import settings


class OpenAIEmbedder:
    def __init__(self) -> None:
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.embedding_model

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        res = await self._client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in res.data]


class DeterministicEmbedder:
    """Offline stand-in for tests and CI.

    Deterministic and dependency-free. Retrieval quality is meaningless here —
    that is fine, because the tests that use it assert on *permission* behaviour,
    which must hold regardless of ranking.
    """

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim or settings.embedding_dim
        self.model = "deterministic-test"

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            seed = hashlib.sha256(t.lower().encode()).digest()
            vals = [((seed[i % len(seed)] + i) % 255) / 255.0 - 0.5 for i in range(self.dim)]
            norm = math.sqrt(sum(v * v for v in vals)) or 1.0
            out.append([v / norm for v in vals])
        return out


def get_embedder():
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        return OpenAIEmbedder()
    return DeterministicEmbedder()
