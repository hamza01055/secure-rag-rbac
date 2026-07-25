# ADR 0001 — Authorization as a search argument, not a post-filter

**Status:** accepted

## Context

Documents carry access classifications. Users have roles. A query must only
surface chunks the user may read.

The obvious implementation retrieves top-k by similarity and discards what the
user cannot see.

## Decision

The authorization predicate is passed into the vector search. Unauthorized
chunks are never candidates.

## Consequences

**Gained:** no context collapse when all top-k are classified; the k budget is
spent entirely on readable documents, so ranking is correct; forbidden text
never enters process memory, logs, or traces.

**Cost:** the vector store must support filtered search with acceptable recall
under selective filters — which constrains the choice of store and requires
payload indexes. Re-classification requires updating point payloads rather than
a query-time join.

**Rejected alternative — query-time join against PostgreSQL:** post-filtering
wearing a disguise. Same three failures.

**Rejected alternative — one collection per role:** duplicates chunks for
overlapping access and makes re-classification a migration.
