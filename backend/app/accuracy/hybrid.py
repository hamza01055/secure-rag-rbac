"""Stage 2 — fusing dense and lexical rankings.

Failure addressed: dense retrieval is excellent at paraphrase and terrible at
exact tokens. Ask for invoice "INV-2024-8871" or a rare surname and embeddings
return things that are *about* invoices. Lexical search nails it. Neither alone
is enough.

Reciprocal rank fusion is used instead of score blending because cosine
similarity and BM25 live on incomparable scales, and any weighted sum of them
needs retuning whenever either side changes. RRF uses only rank position, so it
needs no tuning and does not silently rot when the embedding model is upgraded.

    score(d) = sum over rankings of 1 / (k + rank(d))

Both input lists arrive already filtered. This function never widens the set —
it only reorders the union of what the security boundary permitted.
"""
from __future__ import annotations

from app.vector.base import Chunk


def reciprocal_rank_fusion(
    dense: list[Chunk],
    lexical: list[Chunk],
    *,
    k_constant: int = 60,
    dense_weight: float = 1.0,
    lexical_weight: float = 1.0,
) -> list[Chunk]:
    if not lexical:
        return list(dense)
    if not dense:
        return list(lexical)

    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}

    for weight, ranking in ((dense_weight, dense), (lexical_weight, lexical)):
        for rank, chunk in enumerate(ranking, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + weight / (k_constant + rank)
            chunks.setdefault(chunk.id, chunk)

    fused = []
    for chunk_id, score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
        c = chunks[chunk_id]
        c.score = score
        fused.append(c)
    return fused
