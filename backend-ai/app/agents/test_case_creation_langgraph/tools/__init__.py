"""Tool catalogue (§2.3). Grouped by purpose and assigned to the worker that
needs them. Write tools (``persistence_tools``) are guarded — see Phase 4."""

from .analysis_tools import analyze_requirement
from .context_tools import (
    fetch_requirement,
    fetch_test_case,
    get_related_context,
    get_test_template,
    search_existing_tests,
    seed_project_suite,
    vector_search_tests,
)
from .coverage_tools import compare_coverage, extract_scenarios
from .generation_tools import (
    execute_plan_actions,
    generate_test_case,
    generate_test_plan,
    update_test_case,
)
from .persistence_tools import create_test_in_system, update_test_in_system
from .review_tools import (
    analyze_failures,
    check_correctness,
    check_data_coverage,
    generate_review_report,
    validate_completeness,
)
from .shared import build_llm, using_stub

__all__ = [
    # context
    "fetch_requirement", "search_existing_tests", "vector_search_tests",
    "get_related_context", "fetch_test_case", "get_test_template", "seed_project_suite",
    # coverage
    "extract_scenarios", "compare_coverage",
    # analysis
    "analyze_requirement",
    # generation
    "generate_test_plan", "generate_test_case", "update_test_case", "execute_plan_actions",
    # persistence (guarded)
    "create_test_in_system", "update_test_in_system",
    # review
    "validate_completeness", "check_data_coverage", "check_correctness",
    "generate_review_report", "analyze_failures",
    # shared
    "build_llm", "using_stub",
]
