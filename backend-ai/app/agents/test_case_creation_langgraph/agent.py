"""Graph assembly + entrypoints (§2.5, Phase 3 §3.3).

``build_workflow()`` wires the StateGraph exactly as the spec describes.
``build_initial_state()`` maps the input contract onto the run state.
``run()`` is the ws.py entry: it drives the graph, threading the two HITL
interrupts through a caller-supplied responder, with an optional LangSmith trace.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from . import events
from .nodes import (
    executor_node,
    format_output_node,
    input_guard_node,
    persist_node,
    plan_review_node,
    planner_node,
    reviewer_node,
    test_review_node,
)
from .routing import route_after_executor, route_after_plan_review, route_after_review
from .settings import settings
from .state import TestCaseCreationState


# ── Graph wiring ──────────────────────────────────────────────────────────
def build_workflow(checkpointer: Any | None = None):
    g = StateGraph(TestCaseCreationState)

    g.add_node("input_guard", input_guard_node)
    g.add_node("planner", planner_node)
    g.add_node("plan_review", plan_review_node)  # interrupt() inside
    g.add_node("executor", executor_node)
    g.add_node("test_review", test_review_node)  # interrupt() inside
    g.add_node("reviewer", reviewer_node)
    g.add_node("format_output", format_output_node)
    g.add_node("persist", persist_node)

    g.add_edge(START, "input_guard")
    g.add_edge("input_guard", "planner")
    g.add_edge("planner", "plan_review")

    # HITL #1 — approve plan or send back to planner with a revision
    g.add_conditional_edges(
        "plan_review", route_after_plan_review,
        {"executor": "executor", "planner": "planner"},
    )

    # HITL #2 fires only on the first pass — self-correction retries skip it
    g.add_conditional_edges(
        "executor", route_after_executor,
        {"test_review": "test_review", "reviewer": "reviewer"},
    )
    g.add_edge("test_review", "reviewer")

    # Reviewer verdict — finish or self-correct
    g.add_conditional_edges(
        "reviewer", route_after_review,
        {"format_output": "format_output", "executor": "executor"},
    )

    g.add_edge("format_output", "persist")
    g.add_edge("persist", END)

    return g.compile(checkpointer=checkpointer or _default_checkpointer())


def _default_checkpointer():
    if settings.checkpointer == "postgres" and settings.postgres_url:
        from langgraph.checkpoint.postgres import PostgresSaver

        return PostgresSaver.from_conn_string(settings.postgres_url)
    return InMemorySaver()


# ── Initial state ─────────────────────────────────────────────────────────
def build_initial_state(payload: dict) -> TestCaseCreationState:
    """Map TestCaseCreationInput (§1.4) onto the run state."""
    return {
        "run_id": payload.get("run_id") or f"run-{uuid.uuid4().hex[:12]}",
        "project_id": payload["projectId"],
        "trigger_type": payload.get("trigger_type", "manual"),
        "user_story": payload["userStory"],
        "acceptance_criteria": payload.get("acceptanceCriteria", "") or "",
        "jira_story_id": payload.get("jiraStoryId"),
        "hitl_revision": None,
        "analysis": None,
        "scenarios": None,
        "existing_tests": None,
        "coverage_decisions": None,
        "test_plan": None,
        "plan_approved": False,
        "tests_approved": False,
        "execution_results": None,
        "review_results": None,
        "retry_count": 0,
        "correction_tasks": None,
        "is_best_effort": False,
        "options": payload.get("options") or {},
        "errors": [],
    }


# ── Runner (ws.py entry) ──────────────────────────────────────────────────
def run(
    payload: dict,
    responder: Callable[[dict], Any],
    *,
    sink: Callable[[dict], None] | None = None,
    graph=None,
) -> TestCaseCreationState:
    """Drive a full run to completion.

    ``responder(interrupt_payload) -> reply`` answers each HITL gate (in
    production this round-trips to the UI over WebSocket; in tests it is a
    function). ``sink`` receives every emitted event.
    """
    if sink is not None:
        events.set_sink(sink)

    graph = graph or build_workflow()
    state = build_initial_state(payload)
    config = {"configurable": {"thread_id": state["run_id"]}}

    def _drive(invoke_input):
        result = _maybe_trace(graph, invoke_input, config, state["run_id"])
        # Resolve every interrupt the graph raises until it runs to the end.
        while "__interrupt__" in result:
            intr = result["__interrupt__"][0]
            reply = responder(intr.value)
            result = _maybe_trace(graph, Command(resume=reply), config, state["run_id"])
        return result

    return _drive(state)


def _maybe_trace(graph, invoke_input, config, run_id):
    if settings.langchain_tracing_v2 and settings.langsmith_api_key:
        import langsmith

        with langsmith.trace(
            "test-case-creation", run_type="chain",
            project_name=settings.langsmith_project, metadata={"thread_id": run_id},
        ):
            return graph.invoke(invoke_input, config=config)
    return graph.invoke(invoke_input, config=config)
