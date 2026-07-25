# Developer console

The security property in this system is invisible by design: a correct filter
and a broken one both return an answer. This console makes it visible.

```bash
make console          # or: cd devtools && python -m http.server 5500
open http://localhost:5500/dev-console.html
```

Sign in as any seeded user, run a query, and it shows:

- the role and clearance resolved from the token
- the exact filter expression sent to the vector database
- the rewritten query, per-stage latency, and candidate count
- the permitted chunks with their labels and scores
- **the count of chunks that were excluded**

That last number is the point. Without it, a working filter and a no-op filter
look identical, because both return an answer. Query the seeded canary as
`intern@acme.test`: zero permitted, non-zero excluded is the system working.
Zero permitted and zero excluded means your corpus is all public and your tests
are proving nothing.

## Why it isn't part of the Next.js app

So the debug surface cannot ship to end users. It is a static file, served
locally, talking to an endpoint that is admin-gated, flag-gated, 404s when
disabled, and whose router is not even registered when `ENV=production`.

## What it will never show you

The text of an excluded chunk. It reports counts and document ids only. A debug
tool that displays what a user was blocked from seeing is the exact
vulnerability the system exists to prevent — it would be a leak with an
authorized-looking wrapper.
