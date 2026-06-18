"""Review tools (Reviewer) — the two quality gates + reporting.

Gate 1 — completeness (target: 100% AC coverage)
Gate 2 — correctness (target: score ≥ 80; HARD gate → FAIL below threshold)

``generate_review_report`` produces the Grade + Verdict (PASS / FAIL / ESCALATE).
``analyze_failures`` turns a FAIL into concrete correction tasks for the Executor.
"""

from __future__ import annotations

import re

from ..events import emit_genui
from ..settings import settings

_AMBIGUOUS = re.compile(r"\b(etc|should work|somehow|appropriate|as expected|tbd|maybe)\b", re.I)


def _all_acs(test_plan: dict) -> set[str]:
    acs: set[str] = set()
    for sc in test_plan.get("scenarios", []):
        acs.update(sc.get("ac_refs", []))
    return acs


def _covered_acs(test_plan: dict) -> set[str]:
    """An AC is covered if at least one scenario referencing it is CREATE,
    UPDATE, or SKIP (SKIP means existing suite already covers it)."""
    covered: set[str] = set()
    for sc in test_plan.get("scenarios", []):
        decision = sc.get("coverage_decision", {}).get("decision", "CREATE")
        if decision in ("CREATE", "UPDATE", "SKIP"):
            covered.update(sc.get("ac_refs", []))
    return covered


# ── Gate 1 — completeness ─────────────────────────────────────────────────
def validate_completeness(test_plan: dict, results: dict) -> dict:
    total = _all_acs(test_plan)
    covered = _covered_acs(test_plan)
    missing = sorted(total - covered)
    pct = 100.0 if not total else round(100.0 * len(covered) / len(total), 1)
    return {
        "completeness_pct": pct,
        "total_acs": len(total),
        "covered_acs": len(covered),
        "missing_acs": missing,
        "gate": "PASS" if pct >= 100.0 else "FAIL",
    }


# ── coverage map (by test type) ───────────────────────────────────────────
def check_data_coverage(test_plan: dict, results: dict) -> dict:
    by_type: dict[str, int] = {"Positive": 0, "Negative": 0, "Edge": 0, "Boundary": 0}
    for tc in results.get("test_cases", []):
        by_type[tc.get("type", "Positive")] = by_type.get(tc.get("type", "Positive"), 0) + 1
    present = sum(1 for v in by_type.values() if v > 0)
    coverage_pct = round(100.0 * present / 4, 1)
    coverage_map = {"by_type": by_type, "type_diversity_pct": coverage_pct}
    emit_genui("coverage-map", coverage_map)
    return coverage_map


# ── Gate 2 — correctness (HARD gate) ──────────────────────────────────────
def check_correctness(test_plan: dict, results: dict) -> dict:
    cases = [tc for tc in results.get("test_cases", []) if tc.get("decision") != "SKIP"]
    if not cases:
        return {"correctness_pct": 100.0, "issues": [], "gate": "PASS"}

    issues: list[str] = []
    total_points = 0
    earned = 0.0
    for tc in cases:
        steps = tc.get("steps", [])
        total_points += 1
        # executable: every step has a concrete action + verifiable expected
        if steps and all(s.get("action") and s.get("expected") for s in steps):
            earned += 0.6
        else:
            issues.append(f"{tc['id']}: a step is missing an action or expected result.")
        # unambiguous language
        blob = " ".join(s.get("action", "") + " " + s.get("expected", "") for s in steps)
        if not _AMBIGUOUS.search(blob):
            earned += 0.4
        else:
            issues.append(f"{tc['id']}: contains ambiguous / non-verifiable wording.")

    pct = round(100.0 * earned / total_points, 1) if total_points else 100.0
    gate = "PASS" if pct >= settings.correctness_hard_gate else "FAIL"
    return {"correctness_pct": pct, "issues": issues, "gate": gate}


# ── Review report ─────────────────────────────────────────────────────────
def generate_review_report(completeness: dict, coverage: dict, correctness: dict) -> dict:
    comp = completeness["completeness_pct"]
    corr = correctness["correctness_pct"]
    cov = coverage["type_diversity_pct"]
    quality = round(0.4 * comp + 0.4 * corr + 0.2 * cov, 1)

    correctness_gate = correctness["gate"]
    completeness_gate = completeness["gate"]

    # Hard gate: correctness below threshold → FAIL regardless of quality.
    if correctness_gate == "FAIL" or completeness_gate == "FAIL":
        verdict = "FAIL"
    else:
        verdict = "PASS"

    grade = "A" if quality >= 90 else "B" if quality >= 80 else "C" if quality >= 70 else "D"

    recommendations: list[str] = []
    if completeness_gate == "FAIL":
        recommendations.append(f"Cover missing acceptance criteria: {completeness['missing_acs']}.")
    recommendations.extend(correctness.get("issues", [])[:5])
    if cov < 100:
        recommendations.append("Increase test-type diversity (add Negative/Edge/Boundary cases).")

    return {
        "quality_score_pct": quality,
        "grade": grade,
        "verdict": verdict,
        "completeness": comp,
        "coverage": cov,
        "correctness": corr,
        "correctness_gate": correctness_gate,
        "correction_tasks": [],  # filled by analyze_failures on FAIL
        "recommendations": recommendations,
        "escalate_diagnostic": None,
        "missing_acs": completeness.get("missing_acs", []),  # Phase 6 signal
    }


# ── Failure analysis → correction tasks for the Executor ──────────────────
def analyze_failures(completeness: dict, correctness: dict, test_plan: dict) -> dict:
    correction_tasks: list[dict] = []
    affected: list[str] = []

    # Missing ACs → CREATE tasks
    for ac in completeness.get("missing_acs", []):
        correction_tasks.append({
            "task_type": "CREATE",
            "tc_id": None,
            "scenario": f"Add coverage for {ac}",
            "required_changes": f"Author a test case that verifies {ac}.",
        })

    # Correctness issues → UPDATE tasks against the offending tc_id
    for issue in correctness.get("issues", []):
        tc_id = issue.split(":", 1)[0].strip()
        affected.append(tc_id)
        correction_tasks.append({
            "task_type": "UPDATE",
            "tc_id": tc_id,
            "scenario": issue,
            "required_changes": "Make each step concrete and its expected result verifiable; "
                                "remove ambiguous wording.",
        })

    return {
        "correction_tasks": correction_tasks,
        "missing_acs": completeness.get("missing_acs", []),
        "affected_tc_ids": sorted(set(affected)),
    }
