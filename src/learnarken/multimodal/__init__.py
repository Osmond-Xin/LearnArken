"""Multimodal ingest & QA (Day 12, docs/specs/day12.md).

Synthetic ICN illustrations are described by a Vision-Language Model into a
controlled, schema-constrained structure, bound to the image by SHA-256, and
indexed at chunk level so figure content is retrievable and citable. Because the
VLM channel is empirically unstable (docs/specs/day12.md Probe finding), every
read is fail-closed; the query-time second-look is a multi-sample consensus read,
never a single trusted call.
"""
