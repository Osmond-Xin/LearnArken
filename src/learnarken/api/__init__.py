"""Day 6 HTTP layer: the only module that serves LearnArken over the wire."""

from learnarken.api.app import create_app

__all__ = ["create_app"]
