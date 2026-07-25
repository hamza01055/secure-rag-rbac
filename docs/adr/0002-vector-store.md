# ADR 0002 — Qdrant as the default store, behind an interface

**Status:** accepted

## Context

Qdrant, Milvus, Pinecone, and pgvector all support filtered search. They differ
in filter semantics, isolation primitives, and operational burden.

## Decision

Qdrant by default. All store access goes through `app/vector/base.py`, and a
pgvector adapter is maintained alongside it to keep the abstraction honest — an
interface with one implementation is an assumption, not an abstraction.

## Rationale

Qdrant's filterable HNSW keeps recall reasonable under selective filters and
falls back to exact search on small filtered subsets. That fallback matters: the
naive alternative elsewhere is to over-fetch and post-filter, which is the exact
bug ADR 0001 exists to prevent.

pgvector is genuinely competitive under a few million chunks and has one real
advantage: authorization data and vectors live in the same system, so there is
no cross-store consistency problem, and row-level security can enforce the
predicate at the database — meaning even a query that forgets the WHERE clause
returns nothing. That is the strongest version of this guarantee available.

## Consequences

Switching stores changes one module. The interface deliberately offers no
`search()` without a filter; the unfiltered call used by the developer console
is a separately named method so it cannot be reached by accident.
