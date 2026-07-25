"""Permission isolation through the full retrieval pipeline.

These use a fake store so they run in CI with no services. The fake implements
filtering honestly — if the pipeline ever stops passing a filter, these fail.
"""
from __future__ import annotations

import pytest

from app.core.principal import Principal
from app.vector.base import Chunk, SearchFilter, VectorStore
from tests.conftest import make_chunk, make_principal

CANARY = "Project Nightingale severance multiplier is 2.4"


class FakeStore(VectorStore):
    def __init__(self, chunks: list[Chunk]):
        self.all = chunks
        self.calls: list[SearchFilter | None] = []

    def _apply(self, flt: SearchFilter) -> list[Chunk]:
        self.calls.append(flt)
        return [
            c for c in self.all
            if c.tenant_id == flt.tenant_id
            and set(c.allowed_roles) & set(flt.roles)
            and c.min_clearance <= flt.clearance
        ]

    async def ensure_ready(self, dim): ...
    async def dense_search(self, vector, *, flt, limit): return self._apply(flt)[:limit]
    async def keyword_search(self, text, *, flt, limit): return self._apply(flt)[:limit]
    async def upsert(self, chunks, vectors): ...
    async def delete_document(self, document_id): return 0
    async def count_document(self, document_id): return 0
    async def unfiltered_count_for_debug(self, vector, *, tenant_id, limit):
        return [c.document_id for c in self.all if c.tenant_id == tenant_id][:limit]


@pytest.fixture
def store(monkeypatch):
    chunks = [
        make_chunk("c1", CANARY, roles=["HR", "Admin"], clearance=60, doc="secret-doc"),
        make_chunk("c2", "The office coffee machine is on floor two.",
                   roles=["Intern", "Engineering", "HR", "Admin"], clearance=0, doc="public-doc"),
    ]
    fake = FakeStore(chunks)
    monkeypatch.setattr("app.retrieval.retriever.get_store", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_authorized_user_reaches_the_canary(store, hr):
    """Run this assertion first. A filter that blocks everyone passes every
    negative test below, so the positive case is what makes them meaningful."""
    from app.retrieval import retrieve
    res = await retrieve("severance multiplier", principal=hr)
    assert any(c.id == "c1" for c in res.chunks)


@pytest.mark.asyncio
async def test_unauthorized_user_gets_zero_classified_chunks(store, intern):
    from app.retrieval import retrieve
    res = await retrieve("severance multiplier", principal=intern)
    assert all(c.id != "c1" for c in res.chunks)
    assert all(CANARY not in c.text for c in res.chunks)


@pytest.mark.asyncio
async def test_every_search_call_carried_a_filter(store, intern):
    from app.retrieval import retrieve
    await retrieve("anything at all", principal=intern)
    assert store.calls, "no search was performed"
    assert all(f is not None and not f.is_empty() for f in store.calls)


@pytest.mark.asyncio
async def test_cross_tenant_isolation(store):
    from app.retrieval import retrieve
    other = make_principal("HR", 60, tenant="tenant-b")
    res = await retrieve("severance multiplier", principal=other)
    assert res.chunks == []


@pytest.mark.asyncio
async def test_hybrid_branch_is_also_filtered(store, intern, monkeypatch):
    """Both retrieval branches must carry the filter. A hybrid pipeline where
    only the dense side is filtered is a leak with an extra step."""
    from app.core.config import settings
    from app.retrieval import retrieve
    monkeypatch.setattr(settings, "enable_hybrid_search", True)
    await retrieve("severance", principal=intern)
    assert len(store.calls) >= 2
    assert all(set(f.roles) == {"Intern"} for f in store.calls)
