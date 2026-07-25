# ADR 0003 — Accuracy layers operate only on permitted candidates

**Status:** accepted

## Context

Hybrid search, reranking, and neighbour expansion all improve answer quality.
Each has a natural implementation that breaks the security model:

- Retrieve unfiltered, rerank, then drop what the user can't see.
- Add a lexical branch without the filter.
- Expand context by fetching `chunk_index ± 1` directly from the store.

Each is a reasonable-looking change that a reviewer without this context would
approve.

## Decision

`app/accuracy/` modules receive candidates and return a reordered or trimmed
subset. They import no store, hold no client, and cannot fetch. Enforced by
`tests/test_boundaries.py`.

## Consequences

**Gained:** the security property survives future accuracy work by people who
weren't in this design review. That is the actual goal — the design is easy, and
keeping it is the hard part.

**Cost:** neighbour expansion is limited to chunks already in the candidate
list, so retrieval width must be wide enough (40) for adjacency to appear
naturally. This is a real quality cost, and it is the right trade.

**Also decided:** reciprocal rank fusion over weighted score blending, because
cosine and BM25 scales are incomparable and any weighting rots silently when the
embedding model is upgraded.
