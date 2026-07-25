# Overview

## What this is

A retrieval-augmented generation system for documents that are not all readable
by everyone. An intern and the head of HR ask the same question and get
different answers, because they are searching different corpora — not because a
filter ran afterward, and not because the model was told to be discreet.

## The problem, stated precisely

Given a corpus where each document has an access classification, and a user with
a role, answer questions using only the documents that user may read, such that:

1. A document the user cannot read is never a retrieval candidate.
2. Answer quality for the documents they *can* read is as good as an unrestricted
   system would give.
3. Both properties are testable, and tested.

Property 1 is the security subsystem (`docs/02-security-model.md`). Property 2 is
the accuracy subsystem (`docs/03-accuracy-layers.md`). Property 3 is why
`scripts/verify_rbac.py` and `scripts/eval_retrieval.py` exist and why they run
in CI.

## The central decision

Authorization is an argument to the vector search, not a step after it.

The naive alternative — retrieve the top 5 by similarity, then discard what the
user can't see — fails three ways:

- **Context collapse.** If all 5 are classified, the model gets nothing and the
  app looks broken, invisibly, in any log that only counts "retrieval succeeded".
- **Ranking corruption.** The k budget was spent on unreadable documents. A
  permitted chunk at rank 8 that would have answered the question is never
  considered.
- **Leak surface.** Classified text existed in process memory, and therefore
  potentially in a log line, a trace span, an error payload, or a cache.

Pre-filtering restricts the candidate set by metadata and then ranks, so the
user always gets the best k chunks they are permitted to see, and forbidden text
never crosses the process boundary.

## What makes it hold over time

The design is not the hard part; keeping it is. Systems like this leak because
someone adds a `/search` endpoint eight months later and opens their own vector
client. So the architecture is enforced mechanically:

- One retrieval function, `principal` required and non-defaultable.
- `tests/test_boundaries.py` fails the build if any module outside the boundary
  can reach the store.
- `accuracy/` modules are structurally incapable of fetching — they only reorder
  what they are handed.
- `scripts/verify_rbac.py` runs adversarial permission tests in CI.

## Reading order

New to the codebase: this file → `01-architecture.md` → `backend/app/retrieval/`
→ `02-security-model.md`.

Working on answer quality: `03-accuracy-layers.md` → `backend/app/accuracy/` →
`scripts/eval_retrieval.py`.

Reviewing before a deployment: `05-security-checklist.md`.
