"""Error taxonomy.

Every one of these is a fail-closed signal. None of them has a handler that
falls back to an unfiltered search or an empty result that reads as "no match".
"""
from __future__ import annotations

from fastapi import HTTPException, status


class FilterError(RuntimeError):
    """The authorization filter could not be constructed. Never proceed."""


class VectorStoreError(RuntimeError):
    """The vector store failed. Never retry without the filter."""


class UnlabeledChunkError(ValueError):
    """An ingest batch contained a chunk with no authorization labels."""


def unauthorized(detail: str = "not authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail)


def forbidden(detail: str = "insufficient privileges") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail)


def retrieval_unavailable() -> HTTPException:
    # 503, not an empty result set. An empty result is indistinguishable from
    # "you have no access to matching documents", and conflating the two hides
    # outages behind a plausible-looking answer.
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "retrieval unavailable")
