#!/usr/bin/env python3
"""Standalone architectural lint, runnable without pytest.

Same rule as tests/test_boundaries.py, available as a pre-commit hook: the
vector store must not be reachable outside the retrieval boundary, and accuracy
modules must not be able to fetch.
"""
from __future__ import annotations

import pathlib
import sys

APP = pathlib.Path(__file__).resolve().parents[1] / "backend" / "app"

ALLOWED = {
    "retrieval/retriever.py", "retrieval/__init__.py",
    "services/ingest.py", "routers/debug.py", "main.py",
}
MARKERS = ("get_store", "app.vector.factory", "QdrantStore", "PgVectorStore")


def main() -> int:
    problems: list[str] = []

    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith("vector/") or rel in ALLOWED:
            continue
        src = path.read_text()
        if any(m in src for m in MARKERS):
            problems.append(f"{rel}: reaches the vector store directly")

    for path in (APP / "accuracy").glob("*.py"):
        src = path.read_text()
        if "dense_search" in src or "keyword_search" in src or "get_store" in src:
            problems.append(f"accuracy/{path.name}: accuracy layers must not fetch")

    if problems:
        print("Architectural boundary violations:\n")
        for p in problems:
            print(f"  {p}")
        print("\nAll retrieval goes through app.retrieval.retrieve().")
        return 1

    print("Boundaries intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
