# Secure RAG with RBAC

An enterprise retrieval-augmented generation system where authorization is
enforced **inside** the vector search, not after it, and where retrieval quality
is a measured property rather than a hope.

Two invariants hold everywhere in this codebase:

1. **Security** — the authorization filter is an argument to the vector search.
   A chunk the caller may not read is never a candidate, never scored, never
   materialized in process memory.
2. **Accuracy** — every stage that improves answer quality (query rewriting,
   hybrid search, reranking, context assembly, verification) operates on the
   already-filtered candidate set. No accuracy layer is allowed to widen the
   set the filter produced.

Those two sentences explain almost every design decision below.

---

## Module map

```
secure-rag-rbac/
├── docs/                        architecture, security model, accuracy design, ADRs
├── backend/
│   └── app/
│       ├── core/                config, security primitives, deps, errors, logging
│       ├── vector/              store adapters (Qdrant, pgvector) behind one interface
│       ├── retrieval/           THE security boundary — filters + the one retriever
│       ├── accuracy/            query rewriting, fusion, rerank, assembly, verification
│       ├── services/            ingestion, LLM client, audit
│       ├── routers/             HTTP surface
│       └── workers/             async ingestion worker
│   ├── seeds/                   deterministic corpus for the leak tests
│   └── tests/                   isolation, filter, and accuracy tests
├── frontend/                    Next.js — chat + admin dashboard
├── devtools/                    developer console (retrieval inspector)
├── scripts/                     leak-test harness, retrieval eval harness
├── infra/                       nginx, prometheus, deployment notes
└── skill/                       the Claude skill that generates systems like this
```

### Layer responsibilities

| Layer | Owns | Must never |
|---|---|---|
| `core` | identity, config, error taxonomy | make retrieval decisions |
| `vector` | store-specific filter syntax and I/O | be imported outside `retrieval/` |
| `retrieval` | building the filter, running filtered search | expose an unfiltered path |
| `accuracy` | improving what's returned from a permitted set | fetch anything itself |
| `services` | ingestion, LLM calls, audit writes | bypass `retrieval.retrieve()` |
| `routers` | HTTP shape, status codes | derive identity from the request body |

The dependency direction is one-way: `routers → services → accuracy → retrieval
→ vector`. `accuracy` receives candidates; it never holds a vector client.
That single rule is what stops a reranker or a hybrid-search addition from
quietly becoming a post-filtering bug.

---

## Quick start

```bash
cp .env.example .env
# generate a real secret — the app refuses to boot without one
python -c "import secrets; print('JWT_SECRET=' + secrets.token_hex(32))" >> .env

make up          # postgres + qdrant + redis + api + worker + web
make seed        # roles, users, and a deliberately classified test corpus
make verify      # the leak tests — these must pass
make console     # serves devtools/dev-console.html on :5500
```

Seeded users, all with password `devpassword`:

| Email | Role | Clearance |
|---|---|---|
| `admin@acme.test` | Admin | 100 |
| `hr@acme.test` | HR | 60 |
| `eng@acme.test` | Engineering | 40 |
| `intern@acme.test` | Intern | 10 |

The seed corpus contains a compensation document readable only by HR and Admin,
carrying a canary phrase that appears nowhere else. Ask `intern@acme.test` about
executive compensation and the correct result is **zero retrieved chunks** — not
a polite refusal generated from text the model was shown.

---

## The two subsystems

### Security: pre-filtering

Post-filtering (retrieve top-k, then discard what the user can't see) fails
three ways: context collapse when all k are classified, ranking corruption
because the k budget was spent on unreadable documents, and a leak surface
wherever those chunks touch memory, logs, or traces.

Pre-filtering restricts the candidate set by metadata and *then* ranks. See
`docs/02-security-model.md` and `backend/app/retrieval/`.

### Accuracy: the pipeline above the filter

Filtering correctly still leaves the ordinary RAG failure modes — wrong chunks
retrieved, right chunks ranked low, models asserting things the context doesn't
support. `backend/app/accuracy/` addresses each with a named, individually
measurable stage:

| Stage | Module | Failure it addresses |
|---|---|---|
| Query rewriting | `query_rewrite.py` | pronouns and follow-ups that don't embed well |
| Hybrid retrieval | `hybrid.py` | dense search missing exact identifiers and rare terms |
| Fusion (RRF) | `hybrid.py` | combining two rankings without tuning score scales |
| Reranking | `rerank.py` | the right chunk sitting at rank 12 |
| Context assembly | `assembly.py` | redundancy, token waste, lost neighbouring context |
| Grounded generation | `../services/llm.py` | fluent answers with no source |
| Verification | `verification.py` | claims the retrieved context does not support |
| Offline eval | `../../scripts/eval_retrieval.py` | not knowing whether any of it helped |

Every one of these runs on chunks the caller is already permitted to read. See
`docs/03-accuracy-layers.md` for the design, the metrics, and the tuning order.

---

## Testing

```bash
make test        # unit + integration
make verify      # adversarial permission tests (release blocker)
make eval        # retrieval quality against the labeled eval set
```

`make verify` runs the authorized case first on purpose: a filter that blocks
everyone passes every "unauthorized user sees nothing" assertion, so the suite
proves the permitted path works before it trusts a single negative result.

---

## Documentation

- `docs/00-overview.md` — what this is and the decisions behind it
- `docs/01-architecture.md` — components, trust boundaries, data flows, deployment
- `docs/02-security-model.md` — threat model, enforcement points, failure modes
- `docs/03-accuracy-layers.md` — the retrieval quality pipeline and its metrics
- `docs/04-api-reference.md` — endpoints, payloads, status codes
- `docs/adr/` — the decisions worth defending in a review
