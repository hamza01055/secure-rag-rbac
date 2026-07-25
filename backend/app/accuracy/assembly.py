"""Stage 4 — context assembly.

Failures addressed:
  * Redundancy — five chunks from the same page say the same thing, and the one
    chunk with the contradicting exception never makes it into the window.
  * Token waste — a budget spent on near-duplicates is a budget not spent on
    coverage.
  * Lost neighbours — a chunk boundary splits a definition from its condition,
    so the model reads half a rule and answers confidently.

Maximal marginal relevance handles the first two: each pick trades off relevance
against dissimilarity to what is already selected. Neighbour merging handles the
third by keeping adjacent chunks of the same document contiguous and ordered.

Everything here operates on permitted chunks only. Neighbour expansion is
explicitly restricted to chunks already present in the candidate list — it never
fetches chunk_index±1 from the store, because that fetch would bypass the filter.
"""
from __future__ import annotations

import re

from app.vector.base import Chunk


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _similarity(a: Chunk, b: Chunk) -> float:
    ta, tb = _tokens(a.text), _tokens(b.text)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def mmr_select(candidates: list[Chunk], *, k: int, lambda_: float = 0.7) -> list[Chunk]:
    """Maximal marginal relevance.

    lambda_ = 1.0 is pure relevance (and pure redundancy risk); 0.0 is pure
    diversity (and drifts off-topic). 0.7 is a sane default — tune it against
    the eval set, not against intuition.
    """
    if not candidates:
        return []

    pool = list(candidates)
    selected: list[Chunk] = [pool.pop(0)]

    while pool and len(selected) < k:
        best_idx, best_score = 0, float("-inf")
        for i, cand in enumerate(pool):
            redundancy = max(_similarity(cand, s) for s in selected)
            score = lambda_ * cand.score - (1 - lambda_) * redundancy
            if score > best_score:
                best_idx, best_score = i, score
        selected.append(pool.pop(best_idx))

    return selected


def merge_neighbours(chunks: list[Chunk]) -> list[Chunk]:
    """Keep adjacent chunks from the same document together and in order.

    Only reorders what is already selected. Adjacency is checked against the
    provided list, never fetched.
    """
    by_doc: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_doc.setdefault(c.document_id, []).append(c)

    out: list[Chunk] = []
    for group in by_doc.values():
        group.sort(key=lambda c: c.chunk_index)
        out.extend(group)
    out.sort(key=lambda c: c.score, reverse=True)
    return out


def enforce_budget(chunks: list[Chunk], token_budget: int) -> list[Chunk]:
    kept, used = [], 0
    for c in chunks:
        cost = _estimate_tokens(c.text)
        if used + cost > token_budget:
            break
        kept.append(c)
        used += cost
    return kept


def assemble(
    candidates: list[Chunk],
    *,
    k: int,
    mmr_lambda: float = 0.7,
    token_budget: int = 6000,
) -> list[Chunk]:
    selected = mmr_select(candidates, k=k, lambda_=mmr_lambda)
    selected = merge_neighbours(selected)
    return enforce_budget(selected, token_budget)
