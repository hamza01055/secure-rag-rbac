"""Request and response models.

Every request model forbids extra fields. A client that sends `role` or
`tenant_id` gets a 422, not a silent ignore — surfacing client code that thinks
it can choose its own permissions is more useful than quietly overriding it.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class PrincipalOut(BaseModel):
    user_id: str
    email: str
    role: str
    clearance: int
    tenant_id: str


class ChatRequest(Strict):
    query: str = Field(min_length=1, max_length=4000)
    history: list[str] = Field(default_factory=list, max_length=10)
    # Deliberately absent: role, tenant_id, clearance, filter, collection.


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    source_page: int | None = None
    score: float


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    grounded: bool | None = None
    confidence: float | None = None
    stages: dict[str, float] | None = None   # per-stage latency, ms


class DocumentCreate(Strict):
    filename: str
    allowed_roles: list[str] = Field(min_length=1)   # no default; empty is rejected
    min_clearance: int = Field(ge=0, le=100)


class TraceRequest(Strict):
    query: str
    as_user: EmailStr
    k: int = Field(default=5, ge=1, le=50)
