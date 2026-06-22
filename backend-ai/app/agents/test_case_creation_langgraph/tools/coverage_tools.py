"""Coverage-analysis tools (Planner).

``extract_scenarios`` derives testable scenarios from the requirement.
``compare_coverage`` is a single BATCH LLM call that classifies every scenario
against the existing suite using the decision rule:

    SKIP   if coverage ≥ 90%
    UPDATE if 30% ≤ coverage < 90%
    CREATE if coverage < 30%
"""

from __future__ import annotations

from ..prompts import COMPARE_COVERAGE_PROMPT, EXTRACT_SCENARIOS_PROMPT
from ..settings import settings
from .shared import call_llm, keywords_from, parse_json, using_stub

_TYPE_CYCLE = ["Positive", "Negative", "Edge", "Boundary"]


# ── extract_scenarios ─────────────────────────────────────────────────────
def extract_scenarios(requirement: str, details: dict | None = None) -> dict:
    """Derive 5–10 distinct, testable scenarios. Returns ``{"scenarios": [...]}``."""
    details = details or {}
    slot = settings.llm_planner
    revision = details.get("revision")
    if not using_stub(slot):
        user = f"REQUIREMENT:\n{requirement}\n\nDETAILS:\n{details}"
        if revision:
            # Free-text reviewer instruction (e.g. "focus on negative cases",
            # "reduce to happy path"). The model adjusts the scenario set to it.
            user += (
                f"\n\nREVIEWER REVISION — regenerate the scenarios to satisfy this "
                f"instruction exactly: {revision}"
            )
        parsed = parse_json(call_llm(slot, EXTRACT_SCENARIOS_PROMPT, user))
        if isinstance(parsed, dict) and parsed.get("scenarios"):
            return parsed

    # Offline heuristic: one positive scenario per AC, plus negative/edge spread.
    acs: list[dict] = details.get("acceptance_criteria") or []
    scenarios: list[dict] = []
    idx = 1
    for ac in acs:
        ac_id = ac.get("criterion_id", f"AC-{idx}")
        text = ac.get("criterion_text", "")
        scenarios.append(_mk(idx, f"Verify: {text}", [ac_id], "Positive"))
        idx += 1
        scenarios.append(
            _mk(idx, f"Verify rejection / failure path for: {text}", [ac_id], "Negative")
        )
        idx += 1
    if not scenarios:  # no ACs — fall back to the story text
        scenarios.append(_mk(1, f"Verify primary behaviour: {requirement[:120]}", [], "Positive"))
        scenarios.append(_mk(2, "Verify invalid-input handling", [], "Negative"))
        scenarios.append(_mk(3, "Verify boundary values are handled", [], "Boundary"))
    # Cap at 10
    return {"scenarios": scenarios[:10]}


def _mk(idx: int, text: str, ac_refs: list[str], ttype: str) -> dict:
    return {
        "scenario_id": f"s{idx}",
        "scenario_text": text,
        "ac_refs": ac_refs,
        "suggested_test_type": ttype,
    }


# ── compare_coverage (BATCH — one call for ALL scenarios) ─────────────────
def compare_coverage(scenarios: list[dict], existing_tests: list[dict]) -> list[dict]:
    """Classify every scenario CREATE / UPDATE / SKIP in a single batch call."""
    slot = settings.llm_planner
    if not using_stub(slot):
        user = f"SCENARIOS:\n{scenarios}\n\nEXISTING_TESTS:\n{existing_tests}"
        parsed = parse_json(call_llm(slot, COMPARE_COVERAGE_PROMPT, user))
        if isinstance(parsed, list) and parsed:
            return parsed

    decisions: list[dict] = []
    for sc in scenarios:
        cov, matched = _best_overlap(sc["scenario_text"], existing_tests)
        if cov >= 90:
            decision, reason = "SKIP", f"Already covered by {matched} ({cov:.0f}% overlap)."
        elif cov >= 30:
            decision, reason = "UPDATE", f"Partial coverage by {matched} ({cov:.0f}%); extend it."
        else:
            decision, reason = "CREATE", f"No meaningful existing coverage ({cov:.0f}%)."
        decisions.append(
            {
                "scenario": sc["scenario_text"],
                "decision": decision,
                "matched_tc_id": matched if decision != "CREATE" else None,
                "coverage_pct": round(cov, 1),
                "reason": reason,
            }
        )
    return decisions


def _best_overlap(text: str, existing: list[dict]) -> tuple[float, str | None]:
    kw = set(keywords_from(text))
    best, best_id = 0.0, None
    for tc in existing or []:
        hay = set(keywords_from(tc.get("title", "") + " " + tc.get("description", "")))
        if not kw:
            continue
        overlap = 100.0 * len(kw & hay) / len(kw)
        if overlap > best:
            best, best_id = overlap, tc.get("id")
    return best, best_id
