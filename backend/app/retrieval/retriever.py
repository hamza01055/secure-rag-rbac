"""The one retrieval entry point.

Read this file alongside `docs/02-security-model.md` and
`docs/03-accuracy-layers.md`. It is where the two subsystems meet, and the order
of operations is the whole design:

    1. build the authorization filter          (security — mandatory)
    2. rewrite the query                       (accuracy  — optional)
    3. dense + keyword search, both filtered   (security applies to BOTH branches)
    4. fuse the two rankings                   (accuracy)
    5. rerank the fused candidates             (accuracy)
    6. assemble a context window               (accuracy)

Steps 2-6 can be switched off individually and the system remains *correct*,
only less accurate. Step 1 cannot be switched off at all — there is no argument,
flag, or environment variable that disables it, by construction.

Every accuracy stage operates on a list of chunks that was already permitted.
None of them holds a vector client. That is what stops a future reranker or
hybrid-search change from quietly becoming a post-filtering bug.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.accuracy import assembly, hybrid, query_rewrite, rerank
from app.core.config import settings
from app.core.errors import FilterError, VectorStoreError, retrieval_unavailable
from app.core.logging import get_logger
from app.core.principal import Principal
from app.retrieval.embeddings import get_embedder
from app.retrieval.filters import build_filter
from app.vector import Chunk, get_store

log = get_logger("retrieval")


@dataclass(slots=True)
class RetrievalResult:
    chunks: list[Chunk]
    filter_applied: dict
    stage_ms: dict[str, float] = field(default_factory=dict)
    candidates_considered: int = 0
    rewritten_query: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.chunks


async def retrieve(
    query: str,
    *,
    principal: Principal,
    k: int | None = None,
) -> RetrievalResult:
    """Retrieve the best k chunks this principal is permitted to read.

    `principal` is keyword-only and has no default. Making it impossible to
    forget is worth more than a comment asking people to remember.
    """
    k = k or settings.top_k
    timings: dict[str, float] = {}

    if not query.strip():
        return RetrievalResult(chunks=[], filter_applied={}, stage_ms=timings)

    # ---- 1. Authorization filter. Fail closed on any problem. --------------
    t = time.perf_counter()
    try:
        flt = build_filter(principal)
    except FilterError as exc:
        log.error("filter_construction_failed", reason=str(exc), **principal.audit_dict())
        raise retrieval_unavailable() from exc

    if flt.is_empty():                      # belt and braces; build_filter also checks
        log.error("empty_filter_refused", **principal.audit_dict())
        raise retrieval_unavailable()
    timings["filter"] = _ms(t)

    store = get_store()
    embedder = get_embedder()

    # ---- 2. Query rewriting (accuracy) -------------------------------------
    t = time.perf_counter()
    search_query = query
    if settings.enable_query_rewrite:
        search_query = await query_rewrite.rewrite(query)
    timings["rewrite"] = _ms(t)

    # ---- 3. Retrieval. Both branches carry the same filter. ----------------
    t = time.perf_counter()
    width = max(settings.retrieve_candidates, k)
    try:
        vector = await embedder.embed_query(search_query)
        dense = await store.dense_search(vector, flt=flt, limit=width)

        lexical: list[Chunk] = []
        if settings.enable_hybrid_search:
            lexical = await store.keyword_search(search_query, flt=flt, limit=width)
    except VectorStoreError as exc:
        # No retry, no fallback, no degraded unfiltered path.
        log.error("vector_store_failed", error=str(exc), **principal.audit_dict())
        raise retrieval_unavailable() from exc
    timings["search"] = _ms(t)

    # ---- 4. Fusion (accuracy) ---------------------------------------------
    t = time.perf_counter()
    candidates = hybrid.reciprocal_rank_fusion(dense, lexical, k_constant=settings.rrf_k)
    timings["fusion"] = _ms(t)
    considered = len(candidates)

    # ---- 5. Reranking (accuracy) ------------------------------------------
    t = time.perf_counter()
    if settings.enable_rerank and candidates:
        candidates = await rerank.rerank(search_query, candidates, top_n=k * 3)
        candidates = [c for c in candidates if c.score >= settings.min_rerank_score]
    timings["rerank"] = _ms(t)

    # ---- 6. Context assembly (accuracy) -----------------------------------
    t = time.perf_counter()
    selected = assembly.assemble(
        candidates,
        k=k,
        mmr_lambda=settings.mmr_lambda,
        token_budget=settings.context_token_budget,
    )
    timings["assembly"] = _ms(t)

    # Defence in depth. This should be unreachable — the store filtered already —
    # but an assertion here converts a future adapter bug from a silent leak into
    # a loud failure. Cheap, and it has caught real regressions.
    for c in selected:
        if c.tenant_id and c.tenant_id != principal.tenant_id:
            log.error("post_filter_violation", chunk=c.redacted(), **principal.audit_dict())
            raise retrieval_unavailable()

    log.info(
        "retrieval_complete",
        role=principal.role,
        considered=considered,
        returned=len(selected),
        stage_ms=timings,
    )

    return RetrievalResult(
        chunks=selected,
        filter_applied=flt.as_dict(),
        stage_ms=timings,
        candidates_considered=considered,
        rewritten_query=search_query if search_query != query else None,
    )


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
