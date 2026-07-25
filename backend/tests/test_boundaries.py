"""Architectural constraints, enforced as tests rather than as documentation."""
from __future__ import annotations

import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

# Importing the Chunk and SearchFilter *types* is fine anywhere — they are inert
# dataclasses. What must stay inside the boundary is the ability to reach the
# store and run a search. These are the modules allowed to do that.
ALLOWED_STORE_ACCESS = {
    "retrieval/retriever.py", "retrieval/__init__.py",
    "services/ingest.py", "routers/debug.py", "main.py",
}

STORE_ACCESS_MARKERS = (
    "get_store", "app.vector.factory", "app.vector.qdrant_store",
    "app.vector.pgvector_store", "QdrantStore", "PgVectorStore",
)


def test_store_is_not_reachable_outside_the_boundary():
    """The most common real-world breach in systems like this is a second code
    path added months later that opens its own client and skips retrieve().

    Types are exempt; reach is not. A module that can call dense_search can
    search without a filter, and that is the property being protected.
    """
    offenders = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith("vector/") or rel in ALLOWED_STORE_ACCESS:
            continue
        src = path.read_text()
        if any(marker in src for marker in STORE_ACCESS_MARKERS):
            offenders.append(rel)
    assert not offenders, f"modules reaching the vector store directly: {offenders}"


def test_accuracy_modules_never_fetch():
    """Accuracy layers reorder what they are given. Widening the candidate set
    is not an accuracy improvement, it is a post-filtering bug."""
    offenders = []
    for path in (APP / "accuracy").glob("*.py"):
        src = path.read_text()
        if "get_store" in src or "dense_search" in src or "keyword_search" in src:
            offenders.append(path.name)
    assert not offenders, f"accuracy modules performing retrieval: {offenders}"


def test_retrieve_has_no_default_principal():
    src = (APP / "retrieval" / "retriever.py").read_text()
    assert "principal: Principal," in src
    assert "principal=None" not in src
    assert "principal: Principal | None" not in src
