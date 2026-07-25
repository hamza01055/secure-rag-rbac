from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.accuracy import verification
from app.core.config import settings
from app.core.deps import get_principal
from app.core.principal import Principal
from app.db import get_session
from app.retrieval import retrieve
from app.schemas import ChatRequest, ChatResponse, Citation
from app.services import audit
from app.services.llm import build_prompt, get_llm

router = APIRouter(tags=["chat"])

NO_CONTEXT = (
    "I couldn't find any documents you have access to that cover this. "
    "If you believe this document exists, ask an administrator to check its "
    "classification."
)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    p: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
):
    result = await retrieve(body.query, principal=p)

    if result.is_empty:
        # An honest empty state. Not "access denied" — that confirms a matching
        # classified document exists, which is an inference leak. And never a
        # fallback to unfiltered search or to the model's own knowledge dressed
        # up as a company source.
        await audit.record_query(db, p, body.query, [], grounded=None)
        return ChatResponse(answer=NO_CONTEXT, citations=[], grounded=None,
                            stages=result.stage_ms)

    system, user = build_prompt(body.query, result.chunks)
    answer = await get_llm().complete(system, user)

    report = None
    if settings.enable_verification:
        report = verification.verify(answer, result.chunks)
        if not report.grounded:
            # Surface it rather than silently serving it. Downgrading a confident
            # wrong answer to a flagged one is the whole value of this stage.
            answer += ("\n\n_Note: parts of this answer could not be matched to "
                       "the retrieved sources. Verify against the citations._")

    await audit.record_query(db, p, body.query, result.chunks,
                             grounded=report.grounded if report else None)

    return ChatResponse(
        answer=answer,
        citations=[
            Citation(chunk_id=c.id, document_id=c.document_id, filename=c.filename,
                     source_page=c.source_page, score=round(c.score, 4))
            for c in result.chunks
        ],
        grounded=report.grounded if report else None,
        confidence=report.confidence if report else None,
        stages=result.stage_ms,
    )
