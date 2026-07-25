# Accuracy layers

Getting the permissions right does not get the answers right. A correctly
filtered system still retrieves the wrong chunk, ranks the right chunk twelfth,
and produces confident sentences the sources never support.

This document describes the pipeline that addresses each of those, what it
costs, and how to tell whether any of it is working.

**The structural rule, first, because everything else depends on it:** no
accuracy stage fetches anything. Each receives a list of chunks the security
boundary already permitted and reorders, trims, or checks them. Widening the
candidate set is not an accuracy improvement — it is a post-filtering bug, and
it is exactly how well-intentioned reranking becomes a data leak.

---

## The pipeline

```
query
  │
  ├─ 1. rewrite ──────────── normalize, condense follow-ups
  │
  ├─ 2. retrieve ─────────── dense + lexical, BOTH filtered, width ~40
  │
  ├─ 3. fuse ─────────────── reciprocal rank fusion
  │
  ├─ 4. rerank ───────────── cross-encoder, top ~15
  │
  ├─ 5. assemble ─────────── MMR + neighbour merge + token budget → k=5
  │
  ├─ 6. generate ─────────── citation-required prompt
  │
  └─ 7. verify ───────────── entity-level grounding check
```

Widths matter. Retrieving 40 candidates and reranking to 5 is what makes
reranking worth its latency: the cross-encoder needs a pool deep enough to
contain the answer at rank 20 or the stage has nothing to rescue. Retrieving 5
and reranking 5 is theatre.

---

## Stage 1 — query rewriting (`accuracy/query_rewrite.py`)

**Failure:** users don't write queries that embed well. "hey can you tell me the
parental leave policy, thanks" embeds partly as pleasantries. Follow-ups carry
pronouns with no antecedent — "what about their limit?" is meaningless alone.

**Approach:** strip conversational packaging, and fold in the previous turn when
the query contains an unresolved pronoun. String operations, not an LLM call.

**Why conservative:** an aggressive rewriter that invents synonyms drags
retrieval toward documents answering a question nobody asked, and this is very
hard to notice because the answer still reads fluently. Escalate to model-based
rewriting only when the eval harness shows recall is the bottleneck.

**Cost:** microseconds. **Measure with:** recall@20 before and after.

---

## Stage 2 — hybrid retrieval

**Failure:** dense retrieval is excellent at paraphrase and poor at exact
tokens. Search for invoice `INV-2024-8871`, a rare surname, or an error code,
and embeddings return documents that are *about* invoices. BM25 finds it
immediately. Neither approach alone covers enterprise queries, which are a mix
of conceptual questions and identifier lookups.

**Approach:** run both, over the same filtered subset.

**The security note that matters:** both branches carry the filter. A hybrid
pipeline where only the dense side is filtered is a leak with an extra step, and
it is an easy one to introduce because the lexical branch often gets added later
by someone who wasn't in the original design review. `test_isolation.py` asserts
that every search call in a hybrid run carried a non-empty filter.

---

## Stage 3 — fusion (`accuracy/hybrid.py`)

**Failure:** combining two rankings whose scores are incomparable. Cosine
similarity lives in roughly [0, 1]; BM25 is unbounded. Any weighted sum needs
retuning whenever either side changes, and silently rots when the embedding
model is upgraded.

**Approach:** reciprocal rank fusion, which uses only rank position:

```
score(d) = Σ  1 / (k + rank_i(d))        k = 60
```

**Why RRF over weighted score blending:** no tuning, no rot, robust to one
retriever being poor for a given query. The constant `k` damps the influence of
top ranks so a single confident-but-wrong first result cannot dominate.

**Measure with:** nDCG@10 for dense alone, lexical alone, and fused. If fusion
doesn't beat both, your lexical index is misconfigured.

---

## Stage 4 — reranking (`accuracy/rerank.py`)

**Failure:** the chunk that answers the question is at rank 12 and k is 5.

**Approach:** a cross-encoder reads query and chunk *together* and scores the
pair, rather than comparing two independently-computed vectors. Far more
accurate, far too slow for corpus-wide search — which is precisely why it
belongs over a few dozen candidates.

This is usually the largest single accuracy win in a RAG system. It is also the
stage most often implemented as a post-filtering bug, because "retrieve broadly,
rerank, then drop what they can't see" is the natural way to write it. Don't.

**Fallback:** when `sentence-transformers` isn't installed the module scores by
lexical overlap. Weak, but it keeps the pipeline shape identical in CI so the
stage is always exercised, and the eval harness shows plainly what the real
model buys.

**Cost:** 50–200ms for 40 candidates on CPU; much less on GPU. **Measure with:**
nDCG@5 and answer accuracy on the eval set, with the stage on and off.

---

## Stage 5 — context assembly (`accuracy/assembly.py`)

Three failures, three mechanisms:

**Redundancy.** Five chunks from the same page repeat one fact, and the sixth
chunk containing the exception never fits. Maximal marginal relevance picks each
next chunk by trading relevance against dissimilarity to what's already chosen:

```
MMR = λ · relevance(d) − (1 − λ) · max similarity(d, selected)
```

λ = 1.0 is pure relevance and pure redundancy risk; λ = 0.0 drifts off-topic.
0.7 is a reasonable default — tune against the eval set, not intuition.

**Token waste.** Hard budget enforced before the prompt is built, so a long
chunk can't silently evict everything after it.

**Lost neighbours.** A chunk boundary splits a rule from its exception, and the
model reads half a rule confidently. Adjacent chunks of the same document are
kept contiguous and in order. Note the constraint: neighbour merging only
reorders chunks *already in the permitted candidate list*. It never fetches
`chunk_index ± 1` from the store, because that fetch would bypass the filter —
a subtle and very plausible way to reintroduce the leak.

---

## Stage 6 — grounded generation (`services/llm.py`)

**Failure:** fluent answers with no source, and figures quietly rounded.

**Approach:** numbered sources, mandatory citations, an explicit instruction to
say when the sources don't cover it, and an instruction not to convert or round
figures.

**What this is not:** a security control. Never place text in the context and
instruct the model to withhold it. If a chunk reaches the context window, treat
it as disclosed. The prompt is a quality control; the filter is the security
control.

---

## Stage 7 — verification (`accuracy/verification.py`)

**Failure:** the answer contains a number, date, or name that appears nowhere in
the retrieved context. In a system whose premise is "answers come from your
documents", an ungrounded claim is worse than no answer, because the user has no
way to tell.

**Approach:** extract entities (numbers, currency, dates, proper nouns) from
each answer sentence and from the context, and flag sentences whose entities
aren't supported. Unmatched numbers are weighted heavily — one unmatched proper
noun is usually a paraphrase, an unmatched figure is usually an invention.

**Why mechanical rather than an LLM judge:** it costs nothing, adds no latency,
and cannot itself hallucinate. It catches the errors that matter most in
enterprise Q&A. Escalate to model-based entailment only for the claims this
flags, and only if the eval set shows the cheap check is missing things.

**Boundary:** verification reads the answer and the context already sent to the
model. It never retrieves additional evidence — "evidence the user isn't allowed
to see" is not evidence this system may use.

**Action on failure:** annotate the answer and record `grounded=false` in the
audit log. A rising ungrounded rate usually means retrieval quality dropped, not
that the model got worse.

---

## Measuring

`scripts/eval_retrieval.py` runs a labeled eval set and reports:

| Metric | What it tells you | Where it breaks |
|---|---|---|
| recall@20 | did retrieval find it at all | rewriting, chunking, embeddings |
| nDCG@5 | is it ranked usefully | fusion, reranking |
| MRR | how far down the first hit is | reranking |
| groundedness | does the answer match the sources | prompt, assembly |
| citation coverage | is the model using what it was given | assembly, k |
| **permission leak rate** | did any answer cite a forbidden chunk | must be exactly 0 |

That last row belongs in the accuracy suite deliberately. It must be zero at
every configuration, and running it alongside quality metrics means nobody can
trade a point of nDCG for a leak without seeing it.

## Tuning order

Work top-down; each stage is limited by the one above it.

1. **Chunking.** Bad boundaries cap everything downstream. Check that a chunk
   read alone still means what it means in context.
2. **Recall@20.** If the answer isn't in the candidate pool, no reranker saves
   you. Fix embeddings, chunk size, and hybrid search here.
3. **nDCG@5.** Now that it's in the pool, get it to the top. Reranking.
4. **Groundedness.** Now that the model has the right context, get it to use it.
   Prompt and assembly.
5. **Latency.** Only once quality is where you want it. Reranking is the usual
   cost centre; reduce candidate width before weakening the model.

Changing two stages at once and measuring the sum is the most common way teams
conclude "RAG is hard" when one stage was actively hurting.
