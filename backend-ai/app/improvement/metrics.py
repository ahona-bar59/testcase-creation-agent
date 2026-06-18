"""Drift metrics (Phase 6 §5.1).

Aggregates the run log into the signals we watch monthly:
- AC coverage (completeness) & correctness score distributions,
- pass rate and Gate-#2 approval rate (a falling rate is an early drift signal),
- `work_avoided_pct` (a sudden drop can mean existing-test search is failing).

Pure functions over the feedback store — no live dependency.
"""

from __future__ import annotations

from . import feedback


def _avg(xs: list[float]) -> float:
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 2) if xs else 0.0


def summary() -> dict:
    runs = feedback.all_runs()
    total = len(runs)
    if total == 0:
        return {"runs": 0, "note": "no runs logged yet"}

    passed = sum(1 for r in runs if r.get("verdict") == "PASS")
    escalated = sum(1 for r in runs if r.get("verdict") == "ESCALATE")
    best_effort = sum(1 for r in runs if r.get("is_best_effort"))
    gate2_edited = sum(1 for r in runs if r.get("gate2_edited"))

    fb = feedback.all_feedback()
    ratings = [f for f in fb if f.get("kind") == "rating"]
    thumbs_up = sum(1 for f in ratings if f.get("rating") == "up")

    return {
        "runs": total,
        "pass_rate_pct": round(100.0 * passed / total, 1),
        "escalate_rate_pct": round(100.0 * escalated / total, 1),
        "best_effort_rate_pct": round(100.0 * best_effort / total, 1),
        "gate2_edit_rate_pct": round(100.0 * gate2_edited / total, 1),
        "avg_completeness": _avg([r.get("completeness") for r in runs]),
        "avg_correctness": _avg([r.get("correctness") for r in runs]),
        "avg_quality_pct": _avg([r.get("quality_score_pct") for r in runs]),
        "avg_work_avoided_pct": _avg([r.get("work_avoided_pct") for r in runs]),
        "ratings": {
            "total": len(ratings),
            "approval_pct": round(100.0 * thumbs_up / len(ratings), 1) if ratings else None,
        },
    }
