"""Accuracy layers.

Filtering correctly still leaves every ordinary RAG failure mode: the wrong
chunk retrieved, the right chunk ranked low, a fluent answer the context does
not support. Each module here targets one named failure and is independently
switchable so its contribution can be measured rather than assumed.

The structural rule for this package: **no module here fetches anything.** They
receive candidates that the security boundary already permitted, and they
reorder, trim, or check them. None of them imports app.vector. Widening the
candidate set is not an accuracy improvement — it is a post-filtering bug.
"""
from app.accuracy import assembly, hybrid, query_rewrite, rerank, verification

__all__ = ["assembly", "hybrid", "query_rewrite", "rerank", "verification"]
