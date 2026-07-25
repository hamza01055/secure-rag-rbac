"""Generation.

The prompt is a quality control, not a security control. Never put text in the
context and instruct the model to withhold it — if a chunk reaches the context
window, treat it as disclosed. Everything the model sees here has already passed
the authorization filter, which is why the prompt can be about accuracy alone.
"""
from __future__ import annotations

from app.core.config import settings
from app.vector.base import Chunk

SYSTEM_PROMPT = """You answer questions using only the numbered sources provided.

Rules:
- Every factual claim must come from a source. Cite it as [1], [2], and so on.
- If the sources do not contain the answer, say so plainly. Do not fill the gap
  from general knowledge — the user is asking about their own documents, and a
  plausible invention is worse for them than an admission.
- If sources disagree, say that they disagree and cite both.
- Quote figures, dates, and names exactly as they appear. Do not round, convert,
  or infer them.
- Be concise. Do not restate the question."""


def build_prompt(query: str, chunks: list[Chunk]) -> tuple[str, str]:
    sources = "\n\n".join(
        f"[{i}] (from {c.filename}"
        + (f", page {c.source_page}" if c.source_page else "")
        + f")\n{c.text}"
        for i, c in enumerate(chunks, start=1)
    )
    user = f"Sources:\n\n{sources}\n\nQuestion: {query}"
    return SYSTEM_PROMPT, user


class AnthropicLLM:
    def __init__(self) -> None:
        from anthropic import AsyncAnthropic
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete(self, system: str, user: str) -> str:
        msg = await self._client.messages.create(
            model=settings.llm_model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


class EchoLLM:
    """Offline stand-in. Lets the permission tests run without an API key."""

    async def complete(self, system: str, user: str) -> str:
        body = user.split("Question:")[0]
        first = next((ln for ln in body.splitlines() if ln.strip() and not ln.startswith("[")), "")
        return f"Based on the provided sources: {first.strip()[:400]} [1]"


def get_llm():
    if settings.anthropic_api_key:
        return AnthropicLLM()
    return EchoLLM()
