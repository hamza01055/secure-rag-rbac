---
name: secure-rag-rbac
description: Build enterprise RAG systems where retrieval itself is access-controlled — FastAPI + PostgreSQL + a vector DB (Qdrant/Milvus/Pinecone) + Next.js, using metadata pre-filtering so unauthorized chunks are excluded before similarity scoring rather than filtered out afterward. Use this skill whenever the user mentions RAG with permissions, RBAC, multi-tenant retrieval, document-level or row-level security in a vector database, "the intern shouldn't see the CEO's salary", clearance levels, tenant isolation in embeddings, or asks for a chatbot over internal/confidential company documents — even if they never say the words "RBAC" or "pre-filtering". Also use it when reviewing an existing RAG pipeline for permission leaks.
---

# Secure RAG with role-based access control

The hard part of this system is not generation. It is guaranteeing that a query
issued by an unauthorized user cannot surface a classified chunk — not "surfaces
it and then we drop it", but never retrieves it at all.

Everything in this skill follows from one rule:

> **The authorization filter is an argument to the vector search, never a step after it.**

## Why post-filtering is a real bug, not a style preference

Post-filtering means: retrieve top-k by similarity, then discard what the user
can't see. Three things go wrong, and they get worse in production:

1. **Silent context collapse.** If all k results are classified, you hand the LLM
   zero context. The app appears broken, and the failure is invisible in logs
   that only count "retrieval succeeded".
2. **Ranking corruption.** Even when some results survive, you've spent the k
   budget on documents the user can't read. A permitted-but-rank-8 chunk that
   would have answered the question never gets considered.
3. **Leak surface.** Every place the classified text exists in process memory,
   in a log line, in a trace span, in a debug payload, is a place it can escape.
   Chunks the user can't read should never be materialized in the first place.

Pre-filtering fixes all three: the vector DB restricts the candidate set by
metadata, *then* ranks. You always get the best k chunks the user is allowed to
see, and forbidden text never crosses the process boundary.

## Build order

Work in this sequence. Each step is verifiable before the next one exists,
which matters because a security property you can't test is a security property
you don't have.

1. **Data model first** — PostgreSQL schema (`assets/schema.sql`). Roles and
   clearance levels are the vocabulary everything else speaks.
2. **Auth** — OAuth2 password flow, bcrypt/argon2 hashing, short-lived JWTs
   carrying `sub` and `role`. See `references/backend.md`.
3. **Ingestion with labels** — chunk, embed, and write `allowed_roles` into
   vector payload at write time. Never backfill labels later.
4. **Filtered retrieval** — the one function that must be right. See
   `references/vectordb.md` for the exact filter syntax per database.
5. **Frontend** — Next.js admin dashboard + chat. See `references/frontend.md`.
6. **Developer console** — ship `assets/dev-console.html` so a human can watch
   the filter work. See "The human developer UI" below.
7. **Leak tests** — `scripts/verify_rbac.py` must pass before anyone calls this
   done. See `references/security-checklist.md`.

Read `references/architecture.md` before writing code — it covers the trust
boundaries, the threat model, and where each decision gets enforced.

## Non-negotiables

These are the things that turn a demo into something you'd let a real company
put HR documents into. Deviating from any of them reintroduces the class of bug
the whole design exists to prevent.

**Derive the role server-side, from the token, on every request.** Never accept
a role, tenant id, or clearance level from a request body, query string, or
client-set header. The only trusted source is the validated JWT (or a fresh
lookup keyed by `sub`). A role that arrives in the payload is an authorization
bypass with extra steps.

**One retrieval function, no bypass path.** All retrieval goes through a single
function that takes the caller's identity as a required, non-defaulted argument:

```python
async def retrieve(query: str, *, principal: Principal, k: int = 5) -> list[Chunk]:
```

No default value, no `principal=None`, no "admin mode" flag that skips the
filter. If a caller can forget to pass identity, someone eventually will. Make
it a type error instead of a code review question.

**Fail closed.** If the token is malformed, the role lookup misses, the filter
fails to build, or the vector DB returns an error — return no context and an
error. Never fall back to an unfiltered search. Write this down in the code as
an explicit `except` that raises, not an implicit path that returns `[]` and
looks like "no results found".

**Label at ingest, in the same transaction as the metadata row.** The document's
`min_role_id` in PostgreSQL and the `allowed_roles` array in every one of its
vector points must be written atomically-enough that a crash can't leave chunks
searchable with no labels. Practical approach: write vector points *first* with
labels, then commit the PostgreSQL row; on failure, delete points by
`document_id`. An orphaned labeled point is invisible; an unlabeled point is a
breach.

**Deletion is a two-phase problem.** Deleting a document means deleting every
point with that `document_id` from the vector store *and* the PostgreSQL row.
Do vector deletion first. A dangling PostgreSQL row is a cleanup task; a
dangling vector point is a document you believe is deleted and isn't.

**Re-labeling requires re-indexing the affected points.** When a document's
classification changes, update every point's `allowed_roles`. Don't rely on a
join at query time — that's post-filtering wearing a disguise.

**The LLM is not a security control.** Never put text in the prompt and instruct
the model not to reveal it. Prompt-level instructions are a suggestion; the
retrieval filter is the control. If a chunk reaches the context window, treat it
as disclosed.

## Two models for permission checks

Pick one deliberately and say why in the architecture doc — they behave
differently at scale.

**Role list (`allowed_roles: ["Admin", "HR"]`)** — an explicit allowlist on each
chunk. Best when access is categorical and overlapping: Legal and Finance both
see a contract, neither is "above" the other. Filter is a set-membership test.
Cost: re-index on org changes.

**Clearance level (`min_clearance: 3`)** — a numeric threshold, user passes if
`user.clearance >= chunk.min_clearance`. Best when access is a strict hierarchy.
Filter is a range query. Cost: it can't express "HR sees this, Engineering
doesn't" between peers.

Most real systems want both: `allowed_roles` for departmental scoping plus
`min_clearance` for seniority, ANDed together. When in doubt, implement both
fields from day one — adding a payload field later means re-indexing everything.

Multi-tenant systems add a third, and it is not optional: `tenant_id` on every
point, ANDed into every filter, with tenant derived from the token. Consider
separate collections per tenant when the isolation requirement is contractual.

## The human developer UI

The security property here is invisible by design — a correct system and a
broken one both return an answer. So the build isn't finished until a human can
*see* the filter working. Ship two things:

**The admin dashboard** (Next.js, `references/frontend.md`) — upload documents,
assign classification, manage users and roles. Real product surface.

**The developer console** (`assets/dev-console.html`) — a single self-contained
HTML file, no build step, that a developer opens against a running backend. It
logs in as any seeded user, fires a query, and displays the retrieval trace side
by side: the role resolved from the token, the exact filter expression sent to
the vector DB, the chunks returned with their labels, and — from an admin-only
debug endpoint — the *count* of chunks that were excluded.

That last number is the whole point. It is the difference between "the filter is
working" and "the filter is a no-op and every chunk happens to be public." Copy
this file into the project and wire the `/api/debug/retrieval-trace` endpoint
described in `references/backend.md`.

The debug endpoint returns counts and filter expressions — never excluded chunk
text. Gate it behind an admin role and an environment flag, and make it refuse
to start in production. A debug endpoint that returns what a user was blocked
from seeing is the exact vulnerability this system exists to prevent.

## Verification is part of the build

A permission system without adversarial tests is a permission system that works
until it doesn't. `scripts/verify_rbac.py` runs the tests that matter:

- A low-clearance user querying text that appears *only* in a classified
  document gets zero chunks — not "a refusal", zero chunks.
- The same query as an authorized user returns the chunk. (This catches the
  filter that blocks everything and looks secure.)
- Role supplied in the request body is ignored in favor of the token.
- An expired or tampered token returns 401 with no retrieval attempted.
- Deleting a document removes its points — the same query returns nothing for
  everyone afterward.

Run it in CI. Treat a failure as a release blocker.

`references/security-checklist.md` has the full list, including the failure
modes that are easy to ship: embedding drift between ingest and query, filters
applied to the reranker but not the retriever, chunk text landing in trace spans,
and the classic — a `/health` or `/search` endpoint added later that calls the
vector client directly and skips `retrieve()` entirely.

## Reference files

Read these as needed rather than all at once:

- `references/architecture.md` — component boundaries, trust boundaries, data
  flow, threat model, deployment topology, scaling notes
- `references/backend.md` — FastAPI: auth, dependencies, ingestion, retrieval,
  the debug trace endpoint, code you can lift
- `references/vectordb.md` — filter syntax for Qdrant, Milvus, Pinecone, and
  pgvector, with the tradeoffs and index gotchas for each
- `references/frontend.md` — Next.js structure, cookie/JWT handling, admin
  dashboard, chat interface
- `references/security-checklist.md` — pre-launch checklist and known failure
  modes

## Assets

- `assets/docker-compose.yml` — full local stack
- `assets/schema.sql` — PostgreSQL schema with constraints that matter
- `assets/dev-console.html` — the developer console described above
- `assets/env.example` — required configuration
- `scripts/verify_rbac.py` — the leak test harness

## When explaining this system

The interesting claim is not "we built RAG with auth." It is: *authorization is
enforced inside the retrieval operation, so unauthorized data is never a
candidate.* Lead with the post-filtering failure — context collapse, ranking
corruption, leak surface — then show the filter as the argument to the search,
then show the leak test that proves it. That sequence is what distinguishes an
engineer who understands the system from one who assembled it.
