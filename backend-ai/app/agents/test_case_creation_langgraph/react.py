"""ReAct worker builders (§2.1, §2.6).

The spec's three workers are `create_react_agent` agents. This module wraps the
tool catalogue as LangChain tools and assembles each worker with its own model
slot. The deterministic node orchestration in `nodes.py` is the default for
reliability and offline execution; when a live model is configured these ReAct
workers can be invoked from inside the corresponding node instead.
"""

from __future__ import annotations

from langchain_core.tools import tool

from .prompts import EXECUTOR_SYSTEM, PLANNER_SYSTEM, REVIEWER_SYSTEM
from .settings import settings
from .tools import (
    analyze_requirement,
    check_correctness,
    check_data_coverage,
    compare_coverage,
    execute_plan_actions,
    extract_scenarios,
    fetch_requirement,
    generate_review_report,
    generate_test_plan,
    get_related_context,
    search_existing_tests,
    validate_completeness,
    vector_search_tests,
)
from .tools.shared import build_llm

# ── Planner tools ─────────────────────────────────────────────────────────
_PLANNER_TOOLS = [
    tool(fetch_requirement),
    tool(extract_scenarios),
    tool(search_existing_tests),
    tool(vector_search_tests),
    tool(compare_coverage),
    tool(analyze_requirement),
    tool(generate_test_plan),
]
_EXECUTOR_TOOLS = [tool(get_related_context), tool(execute_plan_actions)]
_REVIEWER_TOOLS = [
    tool(validate_completeness),
    tool(check_data_coverage),
    tool(check_correctness),
    tool(generate_review_report),
]


def _make(slot, tools, system):
    from langgraph.prebuilt import create_react_agent

    return create_react_agent(build_llm(slot), tools, prompt=system)


def make_planner_agent():
    return _make(settings.llm_planner, _PLANNER_TOOLS, PLANNER_SYSTEM)


def make_executor_agent():
    return _make(settings.llm_executor, _EXECUTOR_TOOLS, EXECUTOR_SYSTEM)


def make_reviewer_agent():
    return _make(settings.llm_reviewer, _REVIEWER_TOOLS, REVIEWER_SYSTEM)
