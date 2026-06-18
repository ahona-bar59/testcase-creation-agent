"""Test Case Creation Agent (LangGraph · L2 · Supervised).

Turns a user story + acceptance criteria into reviewed, coverage-aware test
cases. Deterministic routing + two blocking HITL gates; a human approves every
write to the test system.

Public entrypoints:
    build_workflow()        — compile the StateGraph
    build_initial_state()   — map the input contract onto run state
    run()                   — drive a full run, threading HITL interrupts
"""

from .agent import build_initial_state, build_workflow, run
from .state import TestCaseCreationState

__all__ = ["build_workflow", "build_initial_state", "run", "TestCaseCreationState"]

AGENT_ID = "test-case-creation-langgraph"
AUTONOMY_LEVEL = "L2 · Supervised"
