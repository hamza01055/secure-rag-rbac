"""Async ingestion worker.

Separate process on purpose: embedding a large document takes minutes, and a
request thread that blocks that long produces timeouts that get "fixed" by
raising limits rather than by fixing the architecture. The worker also cannot
serve HTTP, which keeps it off the list of things that could accidentally expose
an unfiltered search.
"""
from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db import SessionLocal
from app.services.ingest import Labels, ingest_document

log = get_logger("worker")
QUEUE = "ingest:jobs"


async def handle(job: dict) -> None:
    async with SessionLocal() as db:
        await ingest_document(
            db,
            document_id=job["document_id"],
            tenant_id=job["tenant_id"],
            filename=job["filename"],
            raw_text=job["raw_text"],
            labels=Labels(job["allowed_roles"], job["min_clearance"]),
        )


async def main() -> None:
    configure_logging()
    redis = aioredis.from_url(settings.redis_url)
    log.info("worker_started", queue=QUEUE)
    while True:
        item = await redis.blpop(QUEUE, timeout=5)
        if not item:
            continue
        try:
            await handle(json.loads(item[1]))
        except Exception as exc:                      # noqa: BLE001
            log.error("job_failed", error=str(exc))


if __name__ == "__main__":
    asyncio.run(main())
