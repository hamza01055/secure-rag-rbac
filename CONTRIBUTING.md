# Contributing

Two rules carry more weight than the rest of this file combined.

## 1. All retrieval goes through `app.retrieval.retrieve()`

If you need chunks, call it. Do not import the vector store, do not open a
client, do not add a "just for this one endpoint" query. `make lint` fails the
build if you do, and that check exists because the most common real breach in
systems like this is a second code path added months after the design review by
someone who had no reason to know.

If `retrieve()` genuinely cannot serve your case, change `retrieve()`. That
change gets reviewed. A new client does not.

## 2. Accuracy work never widens the candidate set

Modules in `app/accuracy/` receive permitted chunks and reorder, trim, or check
them. They do not fetch. If your improvement needs more candidates, raise
`retrieve_candidates` in config — which widens the *filtered* pool — rather than
fetching around the filter.

The tempting versions of this bug all look reasonable in a diff:

- retrieve unfiltered, rerank, then drop what the user can't see
- add a lexical branch without passing the filter
- expand context by fetching `chunk_index ± 1` directly

## Checklist before opening a PR

```bash
make lint      # architectural boundaries
make test      # unit + integration, including isolation tests
make verify    # adversarial permission tests
```

If you touched retrieval, ranking, or ingestion, also run `make eval` and paste
the before/after table. Include the permission leak count — it must be 0, and
seeing it next to your nDCG improvement is the point.

## Adding a permission dimension

1. Add the field to the vector payload in `app/vector/base.py` and both adapters.
2. Add it to `build_filter` in `app/retrieval/filters.py`.
3. Add it to the ingest validation in `app/services/ingest.py`.
4. Add a test in `tests/test_isolation.py` where one user has it and another
   doesn't — with a positive assertion, not only a negative one.
5. Re-index. Payload changes do not apply retroactively.
