"""Dependency graph store (Day 5). The only module that knows Neo4j exists."""

from learnarken.graph.store import GraphError, GraphFacts, facts, is_up, sync

__all__ = ["GraphError", "GraphFacts", "facts", "is_up", "sync"]
