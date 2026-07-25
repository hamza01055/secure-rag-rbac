"""Stage 1 — query understanding.

Failure addressed: users write queries that embed badly. Follow-ups carry
pronouns ("what about his?"), real questions carry filler ("hey can you tell me
roughly what our"), and acronyms appear expanded in documents but abbreviated in
questions.

Deliberately conservative. An aggressive rewriter that invents terms will drag
retrieval toward documents that answer a question nobody asked, and it is very
hard to notice because the answer still reads fluently.
"""
from __future__ import annotations

import re

from app.core.config import settings

_FILLER = re.compile(
    r"^\s*(hey|hi|hello|please|could you|can you|i want to know|tell me|"
    r"i'?m wondering|quick question[,:]?)\s+",
    re.IGNORECASE,
)
_TRAILING = re.compile(
    r"[\s,;.]*\b(thanks|thank you|pls|please)\b[.!?]*\s*$", re.IGNORECASE
)


def normalize(query: str) -> str:
    """Strip conversational packaging without touching content words.

    Applied repeatedly because filler stacks: "hey can you tell me ..." is three
    prefixes, and a single pass leaves two of them in the embedded text.
    """
    q = query.strip()
    previous = None
    while previous != q:
        previous = q
        q = _FILLER.sub("", q)
    q = _TRAILING.sub("", q)
    return re.sub(r"\s+", " ", q).strip()


def needs_context(query: str) -> bool:
    """True when the query cannot stand alone — pronouns with no antecedent."""
    return bool(re.search(r"\b(it|they|them|that|those|this|his|her|their)\b",
                          query, re.IGNORECASE))


def condense(query: str, history: list[str]) -> str:
    """Fold the last turn in when the query is a dangling follow-up.

    String concatenation, not an LLM call. It handles the common case at zero
    latency and zero cost; swap in a model here only after the eval harness
    shows the simple version is what's limiting recall.
    """
    if not history or not needs_context(query):
        return query
    return f"{history[-1].strip()} {query.strip()}"


async def rewrite(query: str, history: list[str] | None = None) -> str:
    if not settings.enable_query_rewrite:
        return query
    return normalize(condense(query, history or []))
