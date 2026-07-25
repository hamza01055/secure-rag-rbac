"""Vector store package.

`base` is import-light on purpose — it pulls in no configuration — so tests and
tools can work with Chunk and SearchFilter without booting the whole app. The
concrete store is resolved lazily through get_store().
"""
from app.vector.base import Chunk, SearchFilter, VectorStore

__all__ = ["Chunk", "SearchFilter", "VectorStore", "get_store"]


def __getattr__(name: str):
    if name == "get_store":
        from app.vector.factory import get_store as _get_store
        return _get_store
    raise AttributeError(name)
