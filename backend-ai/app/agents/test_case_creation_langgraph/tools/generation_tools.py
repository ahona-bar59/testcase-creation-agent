"""Generation tools (Planner + Executor).

- ``generate_test_plan`` — decision-tagged plan + ``work_avoided_pct`` (Planner).
- ``generate_test_case`` / ``update_test_case`` — single-case writers (Executor).
- ``execute_plan_actions`` — the Executor **mega-tool**: one call, three paths
  (CREATE / UPDATE / SKIP). Chosen over a fragile per-scenario loop for
  reliability. Emits the ``test-case-table`` GenUI.
"""

from __future__ import annotations

import time

from ..events import emit_genui, emit_trace
from ..prompts import GENERATE_CASE_PROMPT, UPDATE_CASE_PROMPT
from ..settings import settings
from .context_tools import fetch_test_case, get_test_template
from .shared import call_llm, parse_json, using_stub


def _stringify(value) -> str:
    """Coerce a value to a readable string. Live LLMs sometimes return list
    items as objects (e.g. {"risk": "..."}) where a string is expected."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for k in ("risk", "description", "name", "text", "title", "value"):
            if isinstance(value.get(k), str):
                return value[k]
        return "; ".join(f"{k}: {v}" for k, v in value.items())
    return str(value)


# ── generate_test_plan (Planner) ──────────────────────────────────────────
def generate_test_plan(analysis: dict, coverage_decisions: list[dict]) -> dict:
    """Assemble a decision-tagged TestPlan dict from analysis + coverage."""
    scenarios: list[dict] = []
    type_cycle = ["Positive", "Negative", "Edge", "Boundary"]
    for i, cd in enumerate(coverage_decisions, start=1):
        scenarios.append(
            {
                "scenario_id": f"s{i}",
                "scenario_text": cd["scenario"],
                "ac_refs": cd.get("ac_refs", []),
                "suggested_test_type": cd.get("suggested_test_type", type_cycle[(i - 1) % 4]),
                "coverage_decision": cd,
            }
        )

    to_create = sum(1 for c in coverage_decisions if c["decision"] == "CREATE")
    to_update = sum(1 for c in coverage_decisions if c["decision"] == "UPDATE")
    to_skip = sum(1 for c in coverage_decisions if c["decision"] == "SKIP")
    total = len(coverage_decisions)
    work_avoided = round(100.0 * (to_skip + 0.5 * to_update) / total, 1) if total else 0.0

    summary = (
        f"**Coverage plan** — {to_create} CREATE · {to_update} UPDATE · {to_skip} SKIP "
        f"· {work_avoided:.0f}% work avoided.\n\n"
        f"Priority: {_stringify(analysis.get('priority', 'Medium'))} · "
        f"Complexity: {_stringify(analysis.get('complexity', 'Medium'))} · "
        f"Risks: {', '.join(_stringify(r) for r in analysis.get('risks', []))}."
    )

    return {
        "scenarios": scenarios,
        "plan_summary": summary,
        "total_cases": total,
        "to_create": to_create,
        "to_update": to_update,
        "to_skip": to_skip,
        "work_avoided_pct": work_avoided,
    }


# ── generate_test_case (Executor — CREATE) ────────────────────────────────
def generate_test_case(scenario: dict, project_id: str, tc_id: str) -> dict:
    slot = settings.llm_executor
    cd = scenario.get("coverage_decision", {})
    ttype = scenario.get("suggested_test_type", "Positive")
    if not using_stub(slot):
        user = f"SCENARIO:\n{scenario}\nTYPE: {ttype}\nID: {tc_id}"
        parsed = parse_json(call_llm(slot, GENERATE_CASE_PROMPT, user))
        if isinstance(parsed, dict) and parsed.get("steps"):
            parsed.setdefault("id", tc_id)
            return parsed

    tmpl = get_test_template(ttype, project_id)
    text = scenario["scenario_text"]
    return {
        "id": tc_id,
        "title": text if len(text) <= 80 else text[:77] + "...",
        "description": f"{tmpl['intro']}: {text}",
        "priority": cd.get("priority", "Medium"),
        "type": ttype,
        "steps": [
            {"step": 1, "action": "Set up the preconditions and open the relevant screen.",
             "expected": "The system is in a valid starting state."},
            {"step": 2, "action": f"Execute the scenario — {tmpl['step_hint']}.",
             "expected": "The action is accepted and processed."},
            {"step": 3, "action": "Observe the system response.",
             "expected": f"Result matches the requirement for: {text}"},
        ],
        "decision": "CREATE",
        "existing_tc_id": None,
        "decision_reason": cd.get("reason", "No existing coverage."),
    }


# ── update_test_case (Executor — UPDATE) ──────────────────────────────────
def update_test_case(scenario: dict, project_id: str, tc_id: str) -> dict:
    cd = scenario.get("coverage_decision", {})
    existing_id = cd.get("matched_tc_id")
    existing = fetch_test_case(existing_id) if existing_id else None
    slot = settings.llm_executor
    ttype = scenario.get("suggested_test_type", "Positive")
    if not using_stub(slot):
        user = f"SCENARIO:\n{scenario}\nEXISTING:\n{existing}\nID: {tc_id}"
        parsed = parse_json(call_llm(slot, UPDATE_CASE_PROMPT, user))
        if isinstance(parsed, dict) and parsed.get("steps"):
            parsed.setdefault("id", tc_id)
            parsed["existing_tc_id"] = existing_id
            return parsed

    base_title = existing["title"] if existing else scenario["scenario_text"]
    return {
        "id": tc_id,
        "title": f"{base_title} (extended)",
        "description": f"Extend existing case {existing_id} to also cover: {scenario['scenario_text']}",
        "priority": cd.get("priority", "Medium"),
        "type": ttype,
        "steps": [
            {"step": 1, "action": "Run the existing case as documented.",
             "expected": "Existing behaviour still holds (regression safe)."},
            {"step": 2, "action": f"Add the new condition — {scenario['scenario_text']}.",
             "expected": "The new condition is handled correctly."},
        ],
        "decision": "UPDATE",
        "existing_tc_id": existing_id,
        "decision_reason": cd.get("reason", "Partial existing coverage extended."),
    }


# ── execute_plan_actions (Executor MEGA-TOOL) ─────────────────────────────
def execute_plan_actions(test_plan: dict, project_id: str) -> dict:
    """One call, three paths. Builds CREATE/UPDATE cases, records SKIP, and
    emits the ``test-case-table`` GenUI. Returns an ExecutionReport dict
    (including the realised ``test_cases``)."""
    emit_trace("executor", f"processing {test_plan.get('total_cases', 0)} test cases")
    results: list[dict] = []
    test_cases: list[dict] = []
    created = updated = skipped = passed = failed = 0

    seq = 1
    for sc in test_plan.get("scenarios", []):
        cd = sc.get("coverage_decision", {})
        decision = cd.get("decision", "CREATE")
        tc_id = f"TC-{seq:03d}"
        seq += 1
        t0 = time.monotonic()

        if decision == "SKIP":
            skipped += 1
            results.append({
                "tc_id": tc_id, "action": "skipped", "status": "skipped",
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "existing_tc_id": cd.get("matched_tc_id"),
                "reason": cd.get("reason", "Already covered."),
            })
            continue

        if decision == "UPDATE":
            tc = update_test_case(sc, project_id, tc_id)
            updated += 1
            action = "updated"
        else:  # CREATE
            tc = generate_test_case(sc, project_id, tc_id)
            created += 1
            action = "created"

        ok = bool(tc.get("steps"))
        passed += int(ok)
        failed += int(not ok)
        test_cases.append(tc)
        results.append({
            "tc_id": tc_id, "action": action, "status": "pass" if ok else "fail",
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "existing_tc_id": tc.get("existing_tc_id"),
            "reason": tc.get("decision_reason", ""),
        })

    report = {
        "results": results,
        "test_cases": test_cases,
        "total_executed": created + updated + skipped,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "passed": passed,
        "failed": failed,
    }
    emit_genui("test-case-table", test_cases)
    emit_trace("executor", f"{created} created · {updated} updated · {skipped} skipped",
               status="complete")
    return report
