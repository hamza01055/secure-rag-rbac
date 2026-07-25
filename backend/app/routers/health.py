from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    # No retrieval here, and no vector client import. Health endpoints are a
    # classic place for a second, unfiltered code path to appear.
    return {"status": "ok", "env": settings.env, "vector_backend": settings.vector_backend}
