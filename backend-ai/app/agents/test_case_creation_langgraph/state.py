"""Run state (§2.2 of the agent spec).

The whole run lives in one typed object that every node reads and writes. A
checkpointer keyed by `run_id` (== `thread_id`) persists this across the two
HITL `interrupt()` pauses, so the graph can suspend and resume cleanly.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class TestCaseCreationState(TypedDict):
    # ── Run context ───────────────────────────────────────────────────────
    run_id: str
    project_id: str
    trigger_type: str  # "manual" | "api" | "webhook"

    # ── Input ─────────────────────────────────────────────────────────────
    user_story: str
    acceptance_criteria: str
    jira_story_id: str | None
    hitl_revision: str | None  # free-text plan revision from HITL

    # ── Planner output ────────────────────────────────────────────────────
    analysis: dict | None
    scenarios: list | None  # list[TestScenario dicts]
    existing_tests: list | None  # from search_existing_tests
    coverage_decisions: list | None  # list[CoverageDecision dicts]
    test_plan: dict | None  # TestPlan dict

    # ── HITL gates ────────────────────────────────────────────────────────
    plan_approved: bool
    tests_approved: bool

    # ── Executor / Reviewer output ────────────────────────────────────────
    execution_results: dict | None  # ExecutionReport dict
    review_results: dict | None  # ReviewReport dict

    # ── Control flow ──────────────────────────────────────────────────────
    retry_count: int  # 0 on first pass; max 2 self-corrections
    correction_tasks: list | None  # from analyze_failures
    is_best_effort: bool

    # ── Options / accumulated ─────────────────────────────────────────────
    options: dict[str, Any]
    errors: Annotated[list[str], operator.add]  # any node may append
