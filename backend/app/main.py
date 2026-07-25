from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.routers import admin, auth, chat, debug, documents, health
from app.vector import get_store

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # Configuration mistakes should be loud at boot, not quiet at runtime.
    settings.assert_safe_for_env()
    await get_store().ensure_ready(settings.embedding_dim)
    log.info("startup", env=settings.env, backend=settings.vector_backend,
             debug_trace=settings.debug_trace)
    yield


app = FastAPI(
    title="Secure RAG with RBAC",
    version="1.0.0",
    description="Retrieval-augmented generation with authorization enforced inside the search.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (health.router, auth.router, chat.router, documents.router, admin.router):
    app.include_router(r)

# Registered only when explicitly enabled, so it cannot exist in production even
# by accident.
if settings.debug_trace and settings.env != "production":
    app.include_router(debug.router)
