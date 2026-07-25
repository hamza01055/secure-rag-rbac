# Backend — FastAPI

Contents:
1. Layout
2. Principal and auth dependencies
3. The retrieval function
4. Chat endpoint
5. Ingestion
6. Debug trace endpoint
7. Fail-closed patterns

---

## 1. Layout

```
app/
  main.py            FastAPI app, router registration, startup guards
  config.py          pydantic-settings; refuses to boot on bad config
  db.py              async SQLAlchemy session
  models.py          User, Role, Document, AuditLog
  security.py        hashing, JWT encode/decode
  deps.py            get_principal, require_admin
  retrieval.py       THE retrieval function — one entry point
  vector.py          vector client wrapper, filter builders
  routers/
    auth.py  chat.py  documents.py  admin.py  debug.py
  workers/
    ingest.py
```

`retrieval.py` is the security-critical file. Keep it small, keep it reviewed,
and don't let vector client calls appear anywhere else in the codebase. A grep
for the vector client import should return `vector.py` and `retrieval.py` only —
that grep is worth putting in CI as a lint rule.

## 2. Principal and auth dependencies

```python
# deps.py
from dataclasses import dataclass
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    role: str
    clearance: int
    tenant_id: str

async def get_principal(request: Request, db=Depends(get_db)) -> Principal:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    try:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"],
            audience=settings.jwt_audience, issuer=settings.jwt_issuer,
        )
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")

    # Re-read the role from the database rather than trusting the claim alone.
    # Costs one indexed lookup; buys immediate revocation when someone is
    # demoted or offboarded mid-session.
    user = await db.get(User, claims["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown principal")

    return Principal(
        user_id=str(user.id), email=user.email,
        role=user.role.name, clearance=user.role.clearance_level,
        tenant_id=str(user.tenant_id),
    )

async def require_admin(p: Principal = Depends(get_principal)) -> Principal:
    if p.role != "Admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return p
```

`Principal` is frozen. Nothing downstream can mutate a role mid-request, which
removes an entire class of "I only meant to change it for this one call" bug.

If the per-request database read is too expensive at your volume, the fallback
is a `role_version` integer in the claims compared against a cached version map,
with a short TTL. Do not simply trust a long-lived claim — a 24-hour token means
a fired employee has 24 hours of access.

Token issuance: 15-minute access token, HTTP-only + `Secure` + `SameSite=Strict`
cookie, separate refresh token with rotation. Hash passwords with argon2id or
bcrypt (cost ≥ 12). Rate-limit `/auth/login` by IP and by account.

## 3. The retrieval function

This is the whole system. Everything else is plumbing.

```python
# retrieval.py
class FilterError(RuntimeError):
    """Raised when an authorization filter cannot be constructed."""

async def retrieve(query: str, *, principal: Principal, k: int = 5) -> list[Chunk]:
    if not query.strip():
        return []

    flt = build_filter(principal)          # raises FilterError if it can't
    if flt is None or flt.is_empty():      # defensive: never search unfiltered
        raise FilterError("refusing to search without an authorization filter")

    vector = await embed_query(query)      # same model as ingest, always

    try:
        hits = await vclient.search(
            collection=settings.collection,
            query_vector=vector,
            query_filter=flt,              # <-- the entire point
            limit=k,
            with_payload=True,
        )
    except VectorDBError as exc:
        # Fail closed. No fallback, no retry without the filter.
        raise HTTPException(503, "retrieval unavailable") from exc

    return [Chunk.from_hit(h) for h in hits]
```

`build_filter` is where the two permission models live:

```python
def build_filter(p: Principal) -> Filter:
    if not p.role or not p.tenant_id:
        raise FilterError("principal missing role or tenant")
    return Filter(must=[
        FieldCondition(key="tenant_id", match=MatchValue(value=p.tenant_id)),
        FieldCondition(key="allowed_roles", match=MatchAny(any=[p.role])),
        FieldCondition(key="min_clearance", range=Range(lte=p.clearance)),
    ])
```

The three conditions are ANDed: right tenant, role on the allowlist, clearance
high enough. Admin does not get a bypass branch here — give Admin a role that
appears in every `allowed_roles` array instead. A code path that skips the
filter for "trusted" callers is the code path that gets reused by accident.

See `references/vectordb.md` for the equivalent syntax in Milvus, Pinecone, and
pgvector, and for the payload-index requirements that make this fast.

## 4. Chat endpoint

```python
@router.post("/chat")
async def chat(body: ChatRequest, p: Principal = Depends(get_principal), db=...):
    chunks = await retrieve(body.query, principal=p, k=5)

    if not chunks:
        # Honest empty state. Never fall back to unfiltered retrieval, and never
        # let the model answer from its own knowledge as though it were sourced
        # from company documents.
        return ChatResponse(
            answer="I couldn't find any documents you have access to that cover this.",
            citations=[],
        )

    answer = await llm.complete(build_prompt(body.query, chunks))

    await db.execute(insert(AuditLog).values(
        user_id=p.user_id, role=p.role, query=body.query,
        chunk_ids=[c.id for c in chunks],   # ids, never text
        returned=len(chunks),
    ))
    return ChatResponse(answer=answer, citations=[c.citation() for c in chunks])
```

`ChatRequest` must not contain a role, tenant, or filter field. If a client sends
one, pydantic with `model_config = ConfigDict(extra="forbid")` rejects the
request outright — better than silently ignoring it, because it surfaces client
code that thinks it can choose its own permissions.

## 5. Ingestion

```python
async def ingest(doc_id: str, path: str, labels: Labels, tenant_id: str):
    if not labels.allowed_roles:
        raise ValueError("refusing to index a document with no role labels")

    chunks = chunk_text(extract_text(path), size=600, overlap=80)
    vectors = await embed_batch([c.text for c in chunks])

    points = [
        Point(
            id=str(uuid4()),
            vector=v,
            payload={
                "document_id": doc_id,
                "tenant_id": tenant_id,
                "chunk_index": i,
                "text_content": c.text,
                "allowed_roles": labels.allowed_roles,
                "min_clearance": labels.min_clearance,
                "source_page": c.page,
            },
        )
        for i, (c, v) in enumerate(zip(chunks, vectors))
    ]

    try:
        await vclient.upsert(settings.collection, points)
        await db.execute(update(Document).where(...).values(
            status="indexed", chunk_count=len(points)))
    except Exception:
        await vclient.delete(settings.collection, filter_by_document(doc_id))
        await db.execute(update(Document).where(...).values(status="failed"))
        raise
```

The guard on the first line is deliberate: an empty `allowed_roles` is the
default-public failure, and it should be impossible to reach the upsert with one.

Deletion, in this order every time:

```python
await vclient.delete(collection, filter_by_document(doc_id))
remaining = await vclient.count(collection, filter_by_document(doc_id))
if remaining:
    raise RuntimeError(f"{remaining} points survived deletion")
await db.delete(document)
```

## 6. Debug trace endpoint

This backs the developer console. It exists so a human can see the filter work.

```python
@router.post("/api/debug/retrieval-trace")
async def trace(body: TraceRequest, admin: Principal = Depends(require_admin)):
    if not settings.debug_trace or settings.env == "production":
        raise HTTPException(404)

    subject = await load_principal_by_email(body.as_user)  # impersonate for testing
    flt = build_filter(subject)

    permitted = await vclient.search(collection, vec, query_filter=flt, limit=body.k)
    total     = await vclient.search(collection, vec, query_filter=None, limit=body.k)

    return {
        "principal": {"email": subject.email, "role": subject.role,
                      "clearance": subject.clearance, "tenant": subject.tenant_id},
        "filter": flt.model_dump(),          # the expression, verbatim
        "permitted": [
            {"id": h.id, "score": h.score, "document_id": h.payload["document_id"],
             "allowed_roles": h.payload["allowed_roles"],
             "preview": h.payload["text_content"][:240]}
            for h in permitted
        ],
        "excluded_count": len(total) - len(permitted),   # count only
        "excluded_document_ids": sorted({h.payload["document_id"] for h in total}
                                        - {h.payload["document_id"] for h in permitted}),
    }
```

Three constraints on this endpoint, all load-bearing:

1. **Counts and ids, never excluded text.** The moment it returns the text a
   user was blocked from seeing, it is the vulnerability, not the diagnostic.
2. **Admin-gated and flag-gated**, and it 404s (not 403s) when disabled — a 403
   tells an attacker the endpoint exists.
3. **Refuses production.** Add a startup assertion: if `ENV=production` and
   `DEBUG_TRACE=true`, the app exits rather than starts. Configuration mistakes
   should be loud at boot, not quiet at runtime.

The unfiltered search inside it is the one place in the system that runs without
a filter, and it exists solely to compute the excluded count. Keep it in this
file, behind these guards, and nowhere else.

## 7. Fail-closed patterns

```python
# Startup guard — bad config should prevent boot, not degrade silently.
@app.on_event("startup")
async def guard():
    if settings.env == "production" and settings.debug_trace:
        raise SystemExit("DEBUG_TRACE must be off in production")
    if len(settings.jwt_secret) < 32:
        raise SystemExit("JWT secret too short")
    await vclient.ensure_payload_index("allowed_roles")
    await vclient.ensure_payload_index("tenant_id")
```

Rules to hold to throughout:

- Every `except` around retrieval re-raises or returns an error. None returns `[]`.
- No endpoint imports the vector client directly except `retrieval.py`.
- No function signature has a defaultable principal.
- Log chunk ids, scores, and counts. Never log `text_content`.
