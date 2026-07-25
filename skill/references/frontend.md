# Frontend — Next.js

Contents: 1. Structure · 2. Auth and cookies · 3. Chat interface · 4. Admin
dashboard · 5. What the UI must not do

---

## 1. Structure

```
app/
  layout.tsx
  login/page.tsx
  chat/page.tsx
  admin/
    page.tsx              overview
    documents/page.tsx    upload + classification
    users/page.tsx        users and role assignment
    roles/page.tsx        roles and clearance levels
  api/
    proxy/[...path]/route.ts   server-side proxy to FastAPI
middleware.ts                  route protection
components/
  ChatWindow.tsx  CitationList.tsx  DocumentUpload.tsx  RoleBadge.tsx
lib/
  api.ts  session.ts
```

## 2. Auth and cookies

The JWT lives in an HTTP-only cookie set by FastAPI. The browser JavaScript
never reads it, which removes token theft via XSS from the threat model.

Login posts to the proxy route, which forwards to FastAPI and passes the
`Set-Cookie` back:

```ts
// app/api/proxy/[...path]/route.ts
export async function POST(req: Request, { params }: { params: { path: string[] } }) {
  const res = await fetch(`${process.env.API_URL}/${params.path.join("/")}`, {
    method: "POST",
    headers: { "content-type": "application/json", cookie: req.headers.get("cookie") ?? "" },
    body: await req.text(),
  });
  const out = new Response(res.body, { status: res.status, headers: res.headers });
  return out;
}
```

Cookie flags on the FastAPI side: `httponly=True`, `secure=True`,
`samesite="strict"`, `max_age=900`. Refresh on a separate path so the refresh
token isn't sent with every request.

`middleware.ts` redirects unauthenticated users away from `/chat` and `/admin`.
This is convenience, not security — the server enforces on every endpoint
regardless of what the middleware allows through.

## 3. Chat interface

Three things distinguish this from a generic chat UI, and all three are about
making the permission model legible to the person using it:

**Show the acting role.** A persistent badge with the user's role and clearance.
When someone is surprised by an answer, the first question is "as whom did I
ask this?" and the UI should already have answered it.

**Citations that link to sources the user can actually open.** Each citation
carries `document_id`, filename, and page. Clicking fetches the document through
an endpoint that re-checks authorization — never a signed URL minted at chat
time, because the user's role can change between the answer and the click.

**An honest empty state.** When retrieval returns nothing, say so plainly:
"No documents you have access to cover this." Do not say "access denied" (which
confirms a classified document exists and matched the query — an inference leak)
and do not let the model answer from parametric knowledge dressed up as a
company source. The empty state is a designed screen, not a fallback.

Streaming: server-sent events from FastAPI. Render citations only after
retrieval resolves, so a user never sees a citation flash for a chunk that
wasn't actually used.

## 4. Admin dashboard

**Documents.** Upload with a required classification step — the form cannot
submit without at least one role selected. Default the selector to nothing, not
to "All". A default of All is how documents become accidentally public, and a
required field costs the admin two seconds.

Show per-document: filename, uploader, classification, indexing status, chunk
count, and last re-index time. Status matters because a document stuck in
`pending` is invisible to search and users will report it as missing data.

**Users.** List, invite, assign role, deactivate. Deactivation should take effect
immediately — which it does if the backend re-reads the principal per request
(see `references/backend.md`).

**Roles.** Name, clearance level, and a count of documents visible at that level.
That count is the sanity check: if a newly created role with clearance 1 can see
900 of 900 documents, something is labeled wrong.

**Re-classification.** Changing a document's classification triggers a payload
update across its points. Show it as an async job with status, because it isn't
instant and an admin who assumes it is will report a bug.

## 5. What the UI must not do

- **Never send a role, tenant, or clearance to the API.** Not in a header, not
  in a body field, not "for convenience". The server derives all of it.
- **Never rely on hidden UI for authorization.** Hiding the admin nav is
  cosmetic; the admin endpoints check the role themselves. Assume every route
  is called directly with curl, because eventually it will be.
- **Never render an "N results hidden" badge to non-admins.** The count itself
  is information about the classified corpus.
- **Never cache chat responses in a shared client-side store** keyed on query
  text alone. Same leak as server-side caching, harder to notice.

The developer console in `assets/dev-console.html` is deliberately *not* part of
this app. It is a separate static file, run locally, so there is no path by
which the debug trace UI ships to end users.
