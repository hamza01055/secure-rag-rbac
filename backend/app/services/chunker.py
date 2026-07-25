"""Chunking.

Chunk boundaries are an accuracy decision that people mistake for plumbing. A
boundary that splits a rule from its exception produces a chunk that is
confidently wrong on its own, and no amount of reranking recovers it.

Strategy: split on structure first (headings, blank lines), pack to a target
size, overlap slightly so a sentence spanning a boundary survives in one piece.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_PARAGRAPH = re.compile(r"\n\s*\n")
_HEADING = re.compile(r"^\s{0,3}(#{1,6}\s|\d+\.\s+[A-Z]|[A-Z][A-Z \-]{6,}$)")


@dataclass(slots=True)
class TextChunk:
    text: str
    index: int
    page: int | None = None


def _tok(text: str) -> int:
    return max(1, len(text) // 4)


def chunk_text(
    text: str,
    *,
    size_tokens: int = 600,
    overlap_tokens: int = 80,
    page: int | None = None,
) -> list[TextChunk]:
    blocks = [b.strip() for b in _PARAGRAPH.split(text) if b.strip()]
    chunks: list[TextChunk] = []
    buf: list[str] = []
    used = 0

    def flush() -> None:
        nonlocal buf, used
        if buf:
            chunks.append(TextChunk("\n\n".join(buf), len(chunks), page))
            buf, used = [], 0

    for block in blocks:
        cost = _tok(block)
        # A heading starts a new chunk: it belongs with what follows it, not
        # with the section that just ended.
        if buf and (_HEADING.match(block) or used + cost > size_tokens):
            tail = buf[-1] if overlap_tokens and _tok(buf[-1]) <= overlap_tokens else None
            flush()
            if tail:
                buf, used = [tail], _tok(tail)
        buf.append(block)
        used += cost

    flush()
    return chunks
