# API reference

All endpoints require the `access_token` cookie except `/health` and
`/auth/login`. Every request model forbids unknown fields.

## Auth

**POST `/auth/login`** — `{email, password}` → principal, sets HTTP-only cookies.
401 on bad credentials or a disabled account. Timing is equalized so the response
does not reveal which emails exist.

**POST `/auth/logout`** — clears cookies.

**GET `/auth/me`** — the current principal. Useful for confirming which role a
surprising answer was produced under.

## Chat

**POST `/chat`** — `{query, history?}` → `{answer, citations[], grounded,
confidence, stages}`

Sending `role`, `tenant_id`, or `clearance` returns 422. This is deliberate: a
silent ignore hides client code that thinks it can choose its own permissions.

Zero permitted chunks returns 200 with an honest empty-state answer and no
citations — never 403, which would confirm that a matching classified document
exists.

`stages` carries per-stage latency in milliseconds (filter, rewrite, search,
fusion, rerank, assembly), which is what you want when someone reports the
system feeling slow.

## Documents

**GET `/documents`** — documents the caller may read. Filenames are filtered by
the same predicate as content: `Executive_Compensation_2026.md` in a list is
itself a disclosure.

**POST `/documents`** *(admin)* — multipart: `file`, `allowed_roles`
(comma-separated, required, no default), `min_clearance`. 422 when no role is
supplied.

**DELETE `/documents/{id}`** *(admin)* — vector points first, count verified,
then the relational row. Raises rather than half-deleting.

## Admin

**GET `/admin/roles`**, **GET `/admin/users`**, **POST
`/admin/users/{id}/deactivate`** — takes effect on the user's next request.

**GET `/admin/stats`** — document count, query count, zero-result queries,
ungrounded answers. A spike in zero-result queries usually means a filter bug
rather than a corpus gap; it is the metric worth alerting on.

## Debug *(development only)*

**POST `/api/debug/retrieval-trace`** *(admin, `DEBUG_TRACE=true`, non-production)*

`{query, as_user, k}` → principal, filter expression, rewritten query, per-stage
timings, permitted chunks with previews, excluded count, excluded document ids.

Returns counts and ids for excluded chunks, never their text. 404s rather than
403s when disabled — a 403 tells an attacker the endpoint exists. The router is
not even registered unless the flag is on, and the app refuses to start with the
flag on in production.
