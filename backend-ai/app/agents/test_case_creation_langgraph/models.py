"""Pydantic data models (Appendix A of the agent spec).

These are the typed contracts that flow between tools and nodes. They are the
single source of truth for the *shape* of planner / executor / reviewer output,
and they back the output-schema-validation guardrail in `format_output`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Priority = Literal["High", "Medium", "Low"]
TestType = Literal["Positive", "Negative", "Edge", "Boundary"]
Decision = Literal["CREATE", "UPDATE", "SKIP"]


# ── Requirement / scenario inputs ─────────────────────────────────────────
class AcceptanceCriterion(BaseModel):
    criterion_id: str  # "AC-1", ...
    criterion_text: str


class SourceRequirement(BaseModel):
    jira_story_id: str | None = None
    story_title: str
    story_text: str
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    source_type: Literal["manual", "jira", "confluence", "file"] = "manual"
    project_id: str


# ── Coverage analysis ─────────────────────────────────────────────────────
class CoverageDecision(BaseModel):
    scenario: str
    decision: Decision
    matched_tc_id: str | None = None
    coverage_pct: float = 0.0  # 0–100
    reason: str = ""


class TestScenario(BaseModel):
    scenario_id: str  # "s1", ...
    scenario_text: str
    ac_refs: list[str] = Field(default_factory=list)  # ["AC-1", "AC-2"]
    suggested_test_type: TestType = "Positive"
    coverage_decision: CoverageDecision


class TestPlan(BaseModel):
    scenarios: list[TestScenario] = Field(default_factory=list)
    plan_summary: str = ""  # markdown, streamed to chat
    total_cases: int = 0
    to_create: int = 0
    to_update: int = 0
    to_skip: int = 0
    work_avoided_pct: float = 0.0


# ── Generated test cases ──────────────────────────────────────────────────
class TestStep(BaseModel):
    step: int
    action: str
    expected: str


class TestCase(BaseModel):
    id: str
    title: str
    description: str
    priority: Priority
    type: TestType
    steps: list[TestStep] = Field(default_factory=list)
    decision: Decision
    existing_tc_id: str | None = None
    decision_reason: str = ""


# ── Execution report ──────────────────────────────────────────────────────
class ExecutionResult(BaseModel):
    tc_id: str
    action: Literal["created", "updated", "skipped"]
    status: Literal["pass", "fail", "skipped"]
    duration_ms: int = 0
    existing_tc_id: str | None = None
    reason: str = ""


class ExecutionReport(BaseModel):
    results: list[ExecutionResult] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    total_executed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    passed: int = 0
    failed: int = 0


# ── Review report ─────────────────────────────────────────────────────────
class CorrectionTask(BaseModel):
    task_type: Literal["CREATE", "UPDATE"]
    tc_id: str | None = None
    scenario: str
    required_changes: str


class ReviewReport(BaseModel):
    quality_score_pct: float = 0.0  # 0–100
    grade: Literal["A", "B", "C", "D"] = "D"
    verdict: Literal["PASS", "FAIL", "ESCALATE"] = "FAIL"
    completeness: float = 0.0
    coverage: float = 0.0
    correctness: float = 0.0
    correctness_gate: Literal["PASS", "FAIL"] = "FAIL"
    correction_tasks: list[CorrectionTask] = Field(default_factory=list)  # empty when PASS
    recommendations: list[str] = Field(default_factory=list)
    escalate_diagnostic: str | None = None  # set only on ESCALATE
