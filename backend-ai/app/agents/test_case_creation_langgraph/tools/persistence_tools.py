"""Persistence tools (Executor) — GUARDED.

These are the only tools that write to the external test-management system.
They run **exclusively from the `persist` node**, which executes only after
both HITL gates have approved the work (the write-confirmation guardrail, §4.4).
A write failure is appended to `errors` by the caller and surfaced as a trace
event — it never aborts the run.
"""

from __future__ import annotations

from .clients import test_management
from .shared import cache_get, cache_set


def create_test_in_system(test_case: dict, project_id: str) -> str:
    """Write a new test case. GUARDED — runs only after human approval.

    Returns the external id assigned by the test-management system. The dev
    fallback appends to the in-memory project suite and mints a synthetic id.
    """
    # Real test-management write first (only when configured).
    external = test_management.create(test_case, project_id)
    if external:
        return external
    suite = cache_get(f"suite:{project_id}", [])
    external_id = f"TMS-{project_id}-{len(suite) + 1:04d}"
    suite = suite + [{
        "id": external_id,
        "title": test_case.get("title", ""),
        "description": test_case.get("description", ""),
        "type": test_case.get("type", "Positive"),
    }]
    cache_set(f"suite:{project_id}", suite)
    return external_id


def update_test_in_system(test_case_id: str, updates: dict) -> None:
    """Update an existing test case in place. GUARDED.

    The agent never deletes (Phase 1 boundary) — updates are additive.
    """
    if test_management.update(test_case_id, updates):
        return
    for key in list(_suite_keys()):
        suite = cache_get(key, [])
        changed = False
        for tc in suite:
            if tc["id"] == test_case_id:
                tc.update({k: v for k, v in updates.items() if k in tc})
                changed = True
        if changed:
            cache_set(key, suite)
            return


def _suite_keys():
    from .shared import _WORKSPACE_CACHE  # noqa: PLC0415

    return [k for k in _WORKSPACE_CACHE if k.startswith("suite:")]
