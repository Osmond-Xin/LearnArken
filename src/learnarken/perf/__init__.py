"""Performance-engineering experiments (Day 13, docs/specs/day13.md).

Two disjoint concurrency tools, kept strictly apart (Decision 7a):
- `shard`      — multiprocessing for CPU-bound work (per-DM validation/chunking).
- `orchestrate`— asyncio for I/O-bound orchestration (concurrent ToT candidate
  evaluation). No `async def` ever wraps a CPU hotspot (Decision 7e).
"""
