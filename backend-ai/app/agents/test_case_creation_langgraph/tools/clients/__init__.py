"""External system clients (Phase 4).

Each client wraps one system of record behind a small, stable surface:

    available() -> bool      # is it configured + its driver importable?
    <operation>(...)         # the real call; raises on genuine failure

Tools call ``available()`` first and fall back to their synthetic stub when a
client is not configured — so the agent can be implemented and tested with no
live systems and no API key. The systems "play their role" only at run time,
exactly as specified.
"""

from . import requirement_store, suite_store, test_management, vector_index

__all__ = ["requirement_store", "suite_store", "vector_index", "test_management"]
