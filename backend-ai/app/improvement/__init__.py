"""Continuous improvement (Phase 6).

- `feedback` — append-only store for thumbs-up/down, Gate-#2 edits, and missed ACs.
- `metrics` — drift summary computed from the run log (coverage, correctness,
  Gate-#2 approval rate, work_avoided_pct over time).

Both write JSONL files (paths in settings) so the loop works with no database;
swap the sink for Mongo/Postgres in production by editing one module.
"""

from . import feedback, metrics

__all__ = ["feedback", "metrics"]
