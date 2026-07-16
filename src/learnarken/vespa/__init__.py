"""Vespa dense-vector store (Day 4a). The only module that knows Vespa exists."""

from learnarken.vespa.store import (
    VespaError,
    clear,
    count,
    deploy,
    feed,
    is_up,
    list_doc_ids,
    search,
)

__all__ = ["VespaError", "clear", "count", "deploy", "feed", "is_up", "list_doc_ids", "search"]
