"""Stage 5 — post-generation grounding check.

Failure addressed: the model writes a fluent, confident answer containing a
number, name, or date that appears nowhere in the retrieved context. In a
system whose whole premise is "answers come from your documents", an ungrounded
claim is worse than no answer, because the user has no way to tell.

The check is deliberately mechanical rather than a second LLM judging the first.
Entity-level overlap catches the errors that matter most in enterprise Q&A —
fabricated figures, dates, and identifiers — at negligible cost, and it cannot
itself hallucinate. Escalate to a model-based entailment check only for claims
this flags, and only if the eval set shows the cheap check is missing things.

Note the boundary: verification reads the answer and the context that was
already sent to the model. It never retrieves additional evidence, because
"evidence the user isn't allowed to see" is not evidence this system may use.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.vector.base import Chunk

_NUMBER = re.compile(r"\b\d[\d,]*\.?\d*%?\b")
_MONEY = re.compile(r"[$€£]\s?\d[\d,]*\.?\d*")
_DATE = re.compile(r"\b(?:19|20)\d{2}\b|\b(?:Q[1-4])\b", re.IGNORECASE)
_PROPER = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*\b")

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(slots=True)
class GroundingReport:
    grounded: bool
    confidence: float
    unsupported_claims: list[str]
    checked_sentences: int

    def as_dict(self) -> dict:
        return {
            "grounded": self.grounded,
            "confidence": round(self.confidence, 3),
            "unsupported_claims": self.unsupported_claims[:5],
            "checked_sentences": self.checked_sentences,
        }


def _facts(text: str) -> set[str]:
    found: set[str] = set()
    for pattern in (_NUMBER, _MONEY, _DATE):
        found.update(m.group(0).strip().lower().replace(",", "") for m in pattern.finditer(text))
    found.update(m.group(0).strip().lower() for m in _PROPER.finditer(text))
    return {f for f in found if len(f) > 1}


def verify(answer: str, context: list[Chunk], *, threshold: float = 0.75) -> GroundingReport:
    if not answer.strip():
        return GroundingReport(True, 1.0, [], 0)
    if not context:
        # An answer with no context cannot be grounded in company documents,
        # whatever it says.
        return GroundingReport(False, 0.0, ["no retrieved context"], 0)

    supported_facts = set()
    for c in context:
        supported_facts |= _facts(c.text)

    sentences = [s for s in _SENTENCE.split(answer.strip()) if len(s.split()) > 3]
    unsupported: list[str] = []

    for sentence in sentences:
        claims = _facts(sentence)
        if not claims:
            continue                                    # opinion-free connective text
        missing = claims - supported_facts
        # One unmatched proper noun is usually a paraphrase; an unmatched number
        # is usually an invention. Weight accordingly.
        hard_misses = {m for m in missing if _NUMBER.fullmatch(m) or _MONEY.match(m)}
        if hard_misses or len(missing) > len(claims) / 2:
            unsupported.append(sentence.strip()[:200])

    checked = len([s for s in sentences if _facts(s)])
    ratio = 1.0 if checked == 0 else 1.0 - (len(unsupported) / checked)

    return GroundingReport(
        grounded=ratio >= threshold,
        confidence=ratio,
        unsupported_claims=unsupported,
        checked_sentences=checked,
    )


def citation_coverage(answer: str, context: list[Chunk]) -> float:
    """Fraction of provided chunks the answer actually drew on.

    Low coverage with a long answer is the signature of a model answering from
    parametric memory while ignoring the documents — worth alerting on.
    """
    if not context:
        return 0.0
    answer_tokens = set(re.findall(r"\w+", answer.lower()))
    used = sum(
        1 for c in context
        if len(answer_tokens & set(re.findall(r"\w+", c.text.lower()))) >= 5
    )
    return used / len(context)
