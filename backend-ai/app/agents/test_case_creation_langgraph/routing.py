"""Deterministic routing functions (§2.5).

There is NO LLM coordinator. Every routing decision is an explicit, testable
function over state. This is what makes the agent L2 · Supervised: control flow
is predictable, and the two HITL gates can reliably block writes.
"""

from __future__ import annotations

from .settings import settings
from .state import TestCaseCreationState


def route_after_plan_review(state: TestCaseCreationState) -> str:
    """HITL #1: approve the plan → executor; otherwise back to the planner."""
    return "executor" if state.get("plan_approved") else "planner"


def route_after_executor(state: TestCaseCreationState) -> str:
    """First pass (retry_count == 0) → human reviews at HITL #2.
    Self-correction retries (retry_count > 0) skip the gate → straight to Reviewer."""
    return "test_review" if state.get("retry_count", 0) == 0 else "reviewer"


def route_after_review(state: TestCaseCreationState) -> str:
    """Reviewer verdict → finish or self-correct."""
    verdict = (state.get("review_results") or {}).get("verdict", "FAIL")
    if verdict in ("PASS", "ESCALATE"):
        return "format_output"
    if verdict == "FAIL" and state.get("retry_count", 0) < settings.max_self_corrections:
        return "executor"  # self-correct (executor increments retry_count)
    return "format_output"  # best-effort: correction budget exhausted
