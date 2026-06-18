"""Node implementations (§2.6).

Each node is an explicit function on the graph, readable and unit-testable in
isolation. Routing lives in `routing.py`; this file is purely the per-node work.

On the *live* path the planner/executor/reviewer are `create_react_agent`
workers (see `react.py`). For reliability and offline/test execution, the nodes
here orchestrate the documented tool sequence deterministically — the spec's
own reasoning ("single-call mega-tool over a fragile loop") applied to routing.
"""

from __future__ import annotations

import re

from langgraph.types import interrupt

from . import events
from .settings import settings
from .state import TestCaseCreationState
from .tools import (
    analyze_requirement,
    check_correctness,
    check_data_coverage,
    compare_coverage,
    create_test_in_system,
    execute_plan_actions,
    extract_scenarios,
    fetch_requirement,
    generate_review_report,
    generate_test_plan,
    search_existing_tests,
    update_test_in_system,
    validate_completeness,
    vector_search_tests,
)
from .tools.review_tools import analyze_failures

# ── PII patterns (input_guard + output redaction) ─────────────────────────
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_NAME = re.compile(r"\b(?:Mr|Mrs|Ms|Dr)\.?\s+[A-Z][a-z]+\b")
_INJECTION = re.compile(
    r"(ignore (all|previous) instructions|disregard the above|system prompt|"
    r"you are now|reveal your prompt|act as)",
    re.I,
)


def _mask_pii(text: str) -> str:
    text = _EMAIL.sub("[EMAIL]", text)
    text = _NAME.sub("[NAME]", text)
    return text


def _parse_acs(raw: str) -> list[dict]:
    """Parse a free-text acceptance-criteria block into structured ACs."""
    if not raw:
        return []
    lines = [ln.strip(" -*\t") for ln in raw.splitlines() if ln.strip()]
    acs = []
    for i, ln in enumerate(lines, start=1):
        ln = re.sub(r"^(AC[-\s]?\d+[:.)]?\s*)", "", ln, flags=re.I)
        acs.append({"criterion_id": f"AC-{i}", "criterion_text": ln})
    return acs


# ── input_guard ────────────────────────────────────────────────────────────
def input_guard_node(state: TestCaseCreationState) -> dict:
    events.emit_trace("input_guard", "validating input")
    story = state.get("user_story", "") or ""
    errors: list[str] = []

    if _INJECTION.search(story):  # prompt-injection guardrail (≥0.85 → block)
        errors.append("guardrail: prompt-injection pattern detected; suspicious text neutralised.")
        story = _INJECTION.sub("[REDACTED-INSTRUCTION]", story)

    approx_tokens = max(len(story) // 4, len(story.split()))  # length-limit guardrail
    if approx_tokens > settings.input_max_tokens:
        errors.append(
            f"guardrail: user_story exceeded {settings.input_max_tokens} tokens; truncated."
        )
        story = story[: settings.input_max_tokens * 4]

    story = _mask_pii(story)  # pii-detection guardrail (mask)
    ac = _mask_pii(state.get("acceptance_criteria", "") or "")

    events.emit_trace("input_guard", "validated", status="complete")
    return {"user_story": story, "acceptance_criteria": ac, "errors": errors}


# ── planner ──────────────────────────────────────────────────────────────
def planner_node(state: TestCaseCreationState) -> dict:
    events.emit_trace("planner", "analysing requirement")
    project_id = state["project_id"]
    story = state["user_story"]
    acs = _parse_acs(state.get("acceptance_criteria", ""))

    # api / webhook: fetch + overwrite from the system of record.
    if state.get("trigger_type") in ("api", "webhook") and state.get("jira_story_id"):
        req = fetch_requirement(state["jira_story_id"], project_id)
        if req.get("story_text"):
            story = req["story_text"]
        if req.get("acceptance_criteria"):
            acs = req["acceptance_criteria"]

    options = state.get("options") or {}
    revision = state.get("hitl_revision")
    details = {"acceptance_criteria": acs, "options": options, "revision": revision}

    # ReAct step 2 — scenarios
    scen_out = extract_scenarios(story, details)
    scenarios = scen_out["scenarios"]

    # honour HITL revisions (reduce scope / add edge cases)
    if revision:
        r = revision.lower()
        if "reduce" in r or "happy" in r:
            scenarios = [s for s in scenarios if s["suggested_test_type"] == "Positive"] or scenarios
        if "edge" in r:
            scenarios.append({
                "scenario_id": f"s{len(scenarios) + 1}",
                "scenario_text": "Verify additional edge / boundary condition requested by reviewer",
                "ac_refs": [],
                "suggested_test_type": "Edge",
            })

    # ReAct step 3 — search existing suite (keyword + vector)
    from .tools.shared import keywords_from  # noqa: PLC0415

    kw = keywords_from(story + " " + " ".join(s["scenario_text"] for s in scenarios))
    kw_hits = search_existing_tests(project_id, kw)["matches"]
    vec_hits = vector_search_tests(story, project_id)
    existing = {t["id"]: t for t in kw_hits + vec_hits}.values()
    existing_tests = list(existing)

    # ReAct step 4 — BATCH coverage comparison
    decisions = compare_coverage(scenarios, existing_tests)
    # merge scenario metadata into the decisions for downstream stages
    priority = options.get("priority", "Medium")
    for sc, cd in zip(scenarios, decisions):
        cd["ac_refs"] = sc.get("ac_refs", [])
        cd["suggested_test_type"] = sc.get("suggested_test_type", "Positive")
        cd["priority"] = priority

    # ReAct step 5 — analysis
    analysis = analyze_requirement(story)

    # ReAct step 6 — plan
    test_plan = generate_test_plan(analysis, decisions)

    events.emit_genui("scenario-list", scenarios)
    events.emit_trace(
        "planner",
        f"{test_plan['to_create']} CREATE · {test_plan['to_update']} UPDATE · "
        f"{test_plan['to_skip']} SKIP · {test_plan['work_avoided_pct']:.0f}% avoided",
        status="complete",
    )

    return {
        "user_story": story,
        "analysis": analysis,
        "scenarios": scenarios,
        "existing_tests": existing_tests,
        "coverage_decisions": decisions,
        "test_plan": test_plan,
        "hitl_revision": None,  # consumed
    }


# ── plan_review — HITL #1 ─────────────────────────────────────────────────
def plan_review_node(state: TestCaseCreationState) -> dict:
    plan = state["test_plan"]
    summary = (
        f"Does this coverage look right? "
        f"({plan['to_update']} UPDATE · {plan['to_create']} CREATE · "
        f"{plan['to_skip']} SKIP · {plan['work_avoided_pct']:.0f}% work avoided)"
    )
    options = [
        "Yes, generate the test cases",
        "Add more edge cases",
        "Reduce scope — happy path only",
    ]
    events.emit_hitl(summary, options, gate="plan_review", plan_summary=plan["plan_summary"])

    reply = interrupt({
        "gate": "plan_review", "prompt": summary, "options": options,
        "plan_summary": plan["plan_summary"], "plan": plan,
    })

    # Normalise the human reply into approve / revise.
    choice = (reply or {}).get("choice", "") if isinstance(reply, dict) else str(reply or "")
    if choice.strip().lower().startswith("yes") or choice.strip().lower() == "approve":
        return {"plan_approved": True}
    # Any revision → clear planner state and re-plan.
    return {
        "plan_approved": False,
        "hitl_revision": choice or "Revise the plan",
        "scenarios": None,
        "coverage_decisions": None,
        "test_plan": None,
    }


# ── executor — single mega-tool ───────────────────────────────────────────
def executor_node(state: TestCaseCreationState) -> dict:
    test_plan = state["test_plan"]
    retry_count = state.get("retry_count", 0)
    out: dict = {}

    # Self-correction pass: the Reviewer returned FAIL.
    if state.get("review_results") and state["review_results"].get("verdict") == "FAIL":
        retry_count += 1
        out["retry_count"] = retry_count
        out["review_results"] = None  # force the Reviewer to re-grade
        test_plan = _apply_corrections(test_plan, state.get("correction_tasks") or [])
        out["test_plan"] = test_plan

    report = execute_plan_actions(test_plan, state["project_id"])
    out["execution_results"] = report
    return out


def _apply_corrections(test_plan: dict, correction_tasks: list[dict]) -> dict:
    """Fold correction tasks back into the plan before re-execution."""
    plan = dict(test_plan)
    scenarios = list(plan.get("scenarios", []))
    for task in correction_tasks:
        if task["task_type"] == "CREATE":
            scenarios.append({
                "scenario_id": f"s{len(scenarios) + 1}",
                "scenario_text": task["scenario"],
                "ac_refs": [],
                "suggested_test_type": "Positive",
                "coverage_decision": {
                    "scenario": task["scenario"], "decision": "CREATE",
                    "matched_tc_id": None, "coverage_pct": 0.0,
                    "reason": "Added during self-correction to close a coverage gap.",
                },
            })
    plan["scenarios"] = scenarios
    plan["to_create"] = sum(
        1 for s in scenarios if s["coverage_decision"]["decision"] == "CREATE"
    )
    plan["total_cases"] = len(scenarios)
    return plan


# ── test_review — HITL #2 ─────────────────────────────────────────────────
def test_review_node(state: TestCaseCreationState) -> dict:
    report = state["execution_results"]
    cases = report.get("test_cases", [])
    prompt = f"Review and approve the generated test cases ({len(cases)} total)."
    options = ["Approve", "Edit then approve"]
    events.emit_hitl(prompt, options, gate="test_review")
    reply = interrupt({
        "gate": "test_review", "prompt": prompt, "options": options,
        "test_cases": cases,
    })

    # The human may return edited cases — grade the EDITED set.
    if isinstance(reply, dict) and reply.get("test_cases_edited"):
        edited = reply["test_cases_edited"]
        report = dict(report)
        report["test_cases"] = edited
        return {"tests_approved": True, "execution_results": report}
    return {"tests_approved": True}


# ── reviewer — two quality gates ──────────────────────────────────────────
def reviewer_node(state: TestCaseCreationState) -> dict:
    events.emit_trace("reviewer", "running quality gates")
    test_plan = state["test_plan"]
    results = state["execution_results"]

    completeness = validate_completeness(test_plan, results)  # Gate 1
    coverage = check_data_coverage(test_plan, results)        # coverage-map
    correctness = check_correctness(test_plan, results)       # Gate 2 (hard)
    report = generate_review_report(completeness, coverage, correctness)

    out: dict = {"review_results": report}
    if report["verdict"] == "FAIL":
        failures = analyze_failures(completeness, correctness, test_plan)
        report["correction_tasks"] = failures["correction_tasks"]
        out["correction_tasks"] = failures["correction_tasks"]

        # Budget exhausted → best-effort finish; structural failure → escalate.
        if state.get("retry_count", 0) >= settings.max_self_corrections:
            out["is_best_effort"] = True
            if len(failures["missing_acs"]) > 0 and not correctness["issues"]:
                report["verdict"] = "ESCALATE"
                report["escalate_diagnostic"] = (
                    "Acceptance criteria remain uncovered after the correction budget "
                    "was exhausted — likely a requirement-clarity issue, not a drafting one."
                )

    events.emit_genui("review-report", report)
    events.emit_trace(
        "reviewer",
        f"Gate1 completeness {report['completeness']:.0f}% · "
        f"Gate2 correctness {report['correctness']:.0f} {report['correctness_gate']} · "
        f"verdict {report['verdict']}",
        status="complete",
    )
    return out


# ── format_output ──────────────────────────────────────────────────────────
def format_output_node(state: TestCaseCreationState) -> dict:
    from .models import TestCase  # noqa: PLC0415

    results = state["execution_results"] or {}
    raw_cases = results.get("test_cases", [])

    validated: list[dict] = []
    errors: list[str] = []
    for rc in raw_cases:
        try:
            tc = TestCase(**rc)
        except Exception as exc:  # output-schema-validation guardrail
            errors.append(f"format_output: dropped malformed test case {rc.get('id')}: {exc}")
            continue
        d = tc.model_dump()
        # output-pii-redaction guardrail
        d["title"] = _mask_pii(d["title"])
        d["description"] = _mask_pii(d["description"])
        for s in d["steps"]:
            s["action"] = _mask_pii(s["action"])
            s["expected"] = _mask_pii(s["expected"])
        validated.append(d)

    results = dict(results)
    results["test_cases"] = validated

    events.emit_genui("coverage-map", check_data_coverage(state["test_plan"], results))
    events.emit_genui("test-case-table", validated)
    events.emit_genui("review-report", state.get("review_results"))

    return {"execution_results": results, "errors": errors}


# ── persist — guarded ──────────────────────────────────────────────────────
def persist_node(state: TestCaseCreationState) -> dict:
    events.emit_trace("persist", "writing approved test cases")
    project_id = state["project_id"]
    results = state["execution_results"] or {}
    errors: list[str] = []
    written = {"created": 0, "updated": 0, "skipped": 0}

    # write-confirmation guardrail: only the human-approved set reaches here.
    for tc in results.get("test_cases", []):
        decision = tc.get("decision")
        try:
            if decision == "CREATE":
                ext_id = create_test_in_system(tc, project_id)
                tc["existing_tc_id"] = ext_id
                written["created"] += 1
            elif decision == "UPDATE":
                update_test_in_system(tc.get("existing_tc_id"), tc)
                written["updated"] += 1
        except Exception as exc:  # failures surface but never abort
            errors.append(f"persist: write failed for {tc.get('id')}: {exc}")

    # SKIP rows are counted only — never written.
    written["skipped"] = results.get("skipped", 0)

    events.emit_trace(
        "persist",
        f"persisted {written['created']} created · {written['updated']} updated "
        f"· {written['skipped']} skipped",
        status="complete",
    )
    events.emit_done(written=written)
    return {"errors": errors}
