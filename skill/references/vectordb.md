# Vector database — filtering by authorization metadata

Every one of these databases supports filtered search where the filter is
applied during, not after, the search. The syntax differs; the property is the
same. Pick one, and record in the ADR what would change if you switched.

Contents: 1. Payload schema · 2. Qdrant · 3. Milvus · 4. Pinecone · 5. pgvector
· 6. Choosing · 7. Gotchas that cause silent leaks

---

## 1. Payload schema (identical across backends)

| Field | Type | Notes |
|---|---|---|
| `id` | string/uuid | point id |
| `document_id` | uuid | joins to PostgreSQL `documents`; used for delete |
| `tenant_id` | uuid | ANDed into every filter in multi-tenant deployments |
| `chunk_index` | int | ordering within document |
| `text_content` | string | the chunk passed to the LLM |
| `source_page` | int | citations |
| `allowed_roles` | list[string] | explicit allowlist |
| `min_clearance` | int | hierarchical threshold |

Store both `allowed_roles` and `min_clearance` even if you only use one today.
Adding a payload field later is fine in Qdrant and Milvus but means a full
re-upsert in some managed services, and re-upsert means re-embedding cost.

## 2. Qdrant

Recommended default: filtering is a first-class feature, payload indexes are
explicit, and it handles the low-selectivity case well.

```python
from qdrant_client.models import (
    Filter, FieldCondition, MatchValue, MatchAny, Range,
)

flt = Filter(must=[
    FieldCondition(key="tenant_id",     match=MatchValue(value=p.tenant_id)),
    FieldCondition(key="allowed_roles", match=MatchAny(any=[p.role])),
    FieldCondition(key="min_clearance", range=Range(lte=p.clearance)),
])

hits = client.search(
    collection_name="chunks",
    query_vector=vec,
    query_filter=flt,
    limit=k,
    with_payload=True,
)
```

`MatchAny` against a list field is set intersection — the point matches if the
role appears anywhere in `allowed_roles`. If the user holds several roles, pass
them all: `MatchAny(any=p.roles)`.

**Create payload indexes or the filter is a scan:**

```python
client.create_payload_index("chunks", "allowed_roles", field_schema="keyword")
client.create_payload_index("chunks", "tenant_id",     field_schema="keyword")
client.create_payload_index("chunks", "min_clearance", field_schema="integer")
```

Qdrant's filterable HNSW keeps recall reasonable under selective filters and
falls back to exact search when the filtered subset is small. That fallback is
why Qdrant is the safe default here — the naive alternative in other systems is
to over-fetch and post-filter, which is the bug this whole design avoids.

Deletion by document:

```python
client.delete("chunks", points_selector=Filter(must=[
    FieldCondition(key="document_id", match=MatchValue(value=doc_id))]))
```

## 3. Milvus

Boolean expression string, evaluated during search.

```python
expr = (
    f'tenant_id == "{p.tenant_id}" '
    f'and array_contains(allowed_roles, "{p.role}") '
    f'and min_clearance <= {p.clearance}'
)
res = collection.search(
    data=[vec], anns_field="vector", param={"metric_type": "COSINE", "params": {"ef": 64}},
    limit=k, expr=expr, output_fields=["text_content", "document_id", "allowed_roles"],
)
```

Build the expression with parameterized values or strict validation — `p.role`
must come from your roles table, never free text. String interpolation into a
filter expression is injectable the same way SQL is. Whitelist role names
against the database and reject anything else before it reaches this line.

Requires `allowed_roles` declared as an ARRAY field with a defined `max_capacity`
at collection creation. Add a scalar index on `tenant_id`.

## 4. Pinecone

Metadata filter dict, applied during the query.

```python
res = index.query(
    vector=vec, top_k=k, include_metadata=True,
    filter={
        "tenant_id":     {"$eq":  p.tenant_id},
        "allowed_roles": {"$in":  [p.role]},
        "min_clearance": {"$lte": p.clearance},
    },
)
```

Note the asymmetry: for a list-valued metadata field, `$in` tests whether the
stored array intersects the supplied values. Verify this against a test case
rather than assuming — it is the single most common place teams get list
semantics backwards and ship a filter that matches everything.

For strict tenant isolation, Pinecone namespaces give harder separation than a
metadata field: a query to namespace A cannot return vectors from namespace B
even if the filter is wrong. When isolation is contractual, use namespaces
*and* the metadata filter.

## 5. pgvector

Worth serious consideration when the corpus is modest (under a few million
chunks) and you already run PostgreSQL: the authorization data and the vectors
live in one system, so there is no cross-store consistency problem at all.

```sql
SELECT c.id, c.text_content, c.document_id,
       c.embedding <=> $1 AS distance
FROM chunks c
WHERE c.tenant_id = $2
  AND c.allowed_roles && $3::text[]     -- array overlap
  AND c.min_clearance <= $4
ORDER BY c.embedding <=> $1
LIMIT $5;
```

The planner decides between using the HNSW index and filtering, or filtering
first and doing an exact scan. For selective filters the latter is often both
faster and more accurate. Help it:

```sql
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON chunks USING gin (allowed_roles);
CREATE INDEX ON chunks (tenant_id, min_clearance);
```

Then verify with `EXPLAIN ANALYZE` on a realistic corpus. Also consider
PostgreSQL row-level security here — an RLS policy on `chunks` enforces the
predicate at the database, so even a query that forgets the `WHERE` clause
returns nothing. That is the strongest version of this guarantee available in
any of these four options.

## 6. Choosing

| | Qdrant | Milvus | Pinecone | pgvector |
|---|---|---|---|---|
| Filter quality under high selectivity | very good | good | good | excellent (exact) |
| Ops burden | low (self-host) | higher | none (managed) | none extra |
| Hard isolation primitive | collections | partitions | namespaces | RLS |
| Scale ceiling | high | very high | very high | moderate |
| Consistency with your auth data | separate store | separate store | separate store | same store |

Default recommendation: **Qdrant** for a purpose-built store, **pgvector** if
the corpus fits and you value having one source of truth. Both are defensible
in an interview; what matters is that you can say why.

## 7. Gotchas that cause silent leaks

- **An empty filter matches everything.** If `build_filter` can return `None`,
  `{}`, or `Filter(must=[])`, one bad branch searches the whole corpus. Assert
  non-empty before the call, and unit-test the assertion.
- **List semantics backwards.** `$in`, `MatchAny`, `array_contains`, and `&&`
  each mean something slightly different. Test with a fixture where a chunk is
  labeled `["HR"]` and the querying user is `Engineering` — it must not match.
- **Filter on the reranker but not the retriever.** If you add a reranking stage,
  the filter belongs on the initial retrieval. Reranking a forbidden candidate
  set is post-filtering.
- **Hybrid/keyword search path.** Adding BM25 or full-text search later means a
  second retrieval path that also needs the filter. Route it through the same
  `retrieve()` function.
- **Embedding drift.** Ingest and query must use the same model and the same
  normalization. A mismatch degrades relevance quietly and gets misdiagnosed as
  a filter problem for days.
- **Payload index missing.** Not a correctness bug but a latency cliff that
  tempts someone to "optimize" by removing the filter.
- **`allowed_roles` written as a string instead of a list.** `"HR"` versus
  `["HR"]` — depending on backend this either matches nothing or matches by
  substring. Validate the type at ingest.
