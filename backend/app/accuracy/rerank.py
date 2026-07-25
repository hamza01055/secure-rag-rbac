"""Stage 3 — cross-encoder reranking.

Failure addressed: the chunk that actually answers the question sits at rank 12,
and k is 5. Bi-encoder retrieval compares two independently-computed vectors; a
cross-encoder reads the query and the chunk together and scores the pair. It is
far more accurate and far too slow to run over a corpus — which is exactly why
it belongs here, over a few dozen candidates, rather than at search time.

This is usually the single largest accuracy win in a RAG system, and it is also
the stage most likely to be implemented as a post-filtering bug: it is tempting
to retrieve unfiltered, rerank, then drop what the user can't see. Do not. The
candidates handed to this module are already permitted; reranking a forbidden
candidate set is post-filtering in a costume.
"""
from __future__ import annotations

import asyncio
import re
from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.vector.base import Chunk

log = get_logger("rerank")


@lru_cache(maxsize=1)
def _load_cross_encoder():
    try:
        from sentence_transformers import CrossEncoder
        return CrossEncoder(settings.rerank_model, max_length=512)
    except Exception as exc:                       # noqa: BLE001
        log.warning("cross_encoder_unavailable", error=str(exc))
        return None


def _lexical_overlap_score(query: str, text: str) -> float:
    """Fallback scorer when no cross-encoder is installed.

    Weak, but honest and dependency-free: it keeps the pipeline shape identical
    in CI so the stage is always exercised, and the eval harness will show
    plainly how much the real model is buying you.
    """
    q = set(re.findall(r"\w+", query.lower()))
    t = set(re.findall(r"\w+", text.lower()))
    if not q or not t:
        return 0.0
    return len(q & t) / len(q)


async def rerank(query: str, candidates: list[Chunk], *, top_n: int = 15) -> list[Chunk]:
    if not candidates:
        return []

    model = _load_cross_encoder()
    if model is None:
        for c in candidates:
            c.score = _lexical_overlap_score(query, c.text)
    else:
        pairs = [(query, c.text) for c in candidates]
        scores = await asyncio.to_thread(model.predict, pairs)
        for c, s in zip(candidates, scores, strict=True):
            c.score = float(s)

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_n]
