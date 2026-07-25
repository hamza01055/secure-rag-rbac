# Security model

## Enforcement points

Authorization is enforced in exactly one place and asserted in several others.

| Point | Mechanism | File |
|---|---|---|
| Identity | JWT validated, then role re-read from PostgreSQL | `core/deps.py` |
| Filter construction | raises rather than returning permissive | `retrieval/filters.py` |
| Search | filter passed to both dense and lexical branches | `retrieval/retriever.py` |
| Post-search assertion | tenant re-checked on returned chunks | `retrieval/retriever.py` |
| Ingest | unlabeled chunk rejected before upsert | `services/ingest.py` |
| Architecture | store unreachable outside the boundary | `tests/test_boundaries.py` |

The post-search assertion should be unreachable — the store already filtered.
It is there because a future adapter bug would otherwise be a silent leak, and
this converts it into a loud failure. It has caught real regressions in systems
built this way.

## Identity rules

**Role comes from the token plus a database read. Never from the request.**
`ChatRequest` uses `extra="forbid"`, so a client sending `role: "Admin"` gets a
422 rather than a silent ignore — surfacing client code that believes it can
choose its own permissions is more useful than quietly overriding it.

**Principal is frozen.** Nothing downstream can widen its own permissions
mid-request. This removes the entire class of "I only meant to change it for
this one call" bug.

**Deactivation is immediate.** Because `get_principal` re-reads the user rather
than trusting claims, an offboarded employee's next request fails rather than
succeeding until token expiry. This costs one indexed lookup per request. If
that is too expensive at your volume, use a `role_version` claim checked against
a cached map — but do not simply trust a long-lived claim.

## Permission models

Both are implemented and ANDed together:

- `allowed_roles` — explicit allowlist. Categorical, overlapping access: Legal
  and Finance both see a contract, neither is above the other.
- `min_clearance` — numeric threshold. Strict hierarchy: seniority.

Multi-tenant deployments add `tenant_id`, which is not optional and is added
inside `retrieve()` rather than by callers. Consider separate collections or
namespaces when isolation is contractual rather than merely correct.

**Admin has no bypass branch.** Admin is a role added to every document's
allowlist at ingest. Same effect, one fewer code path that skips the check —
and code paths that skip the check are what get reused by accident.

## Threat model

| Threat | Vector | Mitigation |
|---|---|---|
| Role escalation | `role` in request body | Derived server-side; `extra="forbid"` rejects it |
| Stale privilege | Demoted user, valid token | Per-request principal read; 15-minute TTL |
| Second code path | New endpoint opens its own client | Boundary test in CI |
| Hybrid half-filter | Lexical branch added without filter | Isolation test asserts every call filtered |
| Neighbour expansion | Assembly fetches chunk_index±1 | Assembly cannot fetch; boundary test enforces |
| Cache bleed | Retrieval cached on query text alone | Cache key must include tenant and role |
| Prompt injection | Malicious document instructs disclosure | Filter is upstream; model never holds other docs |
| Inference via empty state | "Access denied" confirms a doc exists | Empty state says no *accessible* documents |
| Inference via filenames | Document list leaks titles | List filtered by the same predicate |
| Debug endpoint leak | Trace returns excluded text | Counts and ids only; admin + flag gated; 404s |
| Debug in production | Flag set in shared env file | Startup assertion exits the process |
| Deletion that isn't | PG row deleted, points remain | Vector delete first, count verified, then row |
| Embedding inversion | Vector read access reconstructs text | Treat vectors as sensitive as source text |

## Fail-closed inventory

Every one of these raises rather than degrading:

- Filter cannot be built → 503, no search attempted.
- Filter is empty → 503, refuse.
- Vector store errors → 503, no retry without the filter, no fallback path.
- Chunk without labels at ingest → rejected before upsert.
- Unknown role name at ingest → rejected (a typo must not become a filter that
  matches unexpectedly).
- Points survive deletion → raise, leave the relational row in place so the
  inconsistency stays visible.

Note what is *not* on this list: returning an empty result. An empty result is
indistinguishable from "you have no access to matching documents", and conflating
an outage with a legitimate empty state hides failures behind plausible answers.

## Known failure modes

**The no-op filter.** Every chunk is labeled with every role in testing, so the
filter passes everything and the tests pass too. This is why the seed corpus
contains a document exactly one role can read, and why the leak tests assert the
authorized case *first*.

**The second code path.** The most common real breach. Enforced by CI, not by
memory.

**The generous default.** A classification selector defaulting to "All", or an
ingest path treating a missing label as public. There is no default in the
upload form and no default in `Labels`.

**Inference through the empty state.** "Access denied" tells the user a matching
classified document exists. "No accessible documents cover this" does not. Small
in code, large in what it discloses.
