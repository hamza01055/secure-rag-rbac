"""The security boundary.

Import rule enforced by scripts/lint_boundaries.py in CI: `app.vector` may be
imported here and nowhere else in the application. If a new feature needs
retrieval, it calls retrieve() — it does not open its own client.
"""
from app.retrieval.filters import build_filter
from app.retrieval.retriever import RetrievalResult, retrieve

__all__ = ["build_filter", "retrieve", "RetrievalResult"]
