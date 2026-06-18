"""Feedback + run-log store (Phase 6).

Every run records an outcome (`log_run`). Humans add a thumbs-up/down
(`record_rating`). Gate-#2 edits and missed ACs are captured automatically at
the end of a run (`record_run_signals`). This is the single most valuable
improvement dataset — it tells us not just *that* a draft was wrong but *what
the human changed*.

Storage is append-only JSONL (path from settings); thread-safe via a lock.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from ..agents.test_case_creation_langgraph.settings import settings

_LOCK = threading.Lock()


def _append(path: str, record: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with _LOCK, open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out: list[dict] = []
    with _LOCK, open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


# ── run outcome log (feeds metrics/drift) ─────────────────────────────────
def log_run(run_id: str, project_id: str, final_state: dict, ts: str | None = None) -> None:
    review = final_state.get("review_results") or {}
    plan = final_state.get("test_plan") or {}
    _append(
        settings.run_log_path,
        {
            "kind": "run",
            "run_id": run_id,
            "project_id": project_id,
            "ts": ts,
            "agent_version": settings.agent_version,
            "prompt_version": settings.prompt_version,
            "verdict": review.get("verdict"),
            "completeness": review.get("completeness"),
            "correctness": review.get("correctness"),
            "quality_score_pct": review.get("quality_score_pct"),
            "work_avoided_pct": plan.get("work_avoided_pct"),
            "retry_count": final_state.get("retry_count", 0),
            "is_best_effort": final_state.get("is_best_effort", False),
            "gate2_edited": final_state.get("_gate2_edited", False),
        },
    )


# ── human rating (thumbs up/down on the final table) ──────────────────────
def record_rating(run_id: str, rating: str, comment: str | None, ts: str | None = None) -> None:
    _append(
        settings.feedback_path,
        {"kind": "rating", "run_id": run_id, "rating": rating, "comment": comment, "ts": ts},
    )


# ── automatic signals: Gate-#2 edits + missed ACs ─────────────────────────
def record_run_signals(run_id: str, original: list[dict], edited: list[dict], ts: str | None = None) -> None:
    """Capture the diff between what the agent drafted and what the human kept."""
    by_id = {tc.get("id"): tc for tc in original}
    diffs = []
    for e in edited:
        o = by_id.get(e.get("id"))
        if not o:
            diffs.append({"tc_id": e.get("id"), "change": "added"})
            continue
        changed = {
            k: {"from": o.get(k), "to": e.get(k)}
            for k in ("title", "description", "priority", "type", "decision")
            if o.get(k) != e.get(k)
        }
        if o.get("steps") != e.get("steps"):
            changed["steps"] = {"from": o.get("steps"), "to": e.get("steps")}
        if changed:
            diffs.append({"tc_id": e.get("id"), "change": "edited", "fields": changed})
    if diffs:
        _append(
            settings.feedback_path,
            {"kind": "gate2_edits", "run_id": run_id, "diffs": diffs, "ts": ts},
        )


def record_missed_acs(run_id: str, missed_acs: list[str], ts: str | None = None) -> None:
    if missed_acs:
        _append(
            settings.feedback_path,
            {"kind": "missed_acs", "run_id": run_id, "missed_acs": missed_acs, "ts": ts},
        )


# ── readers (used by metrics + tests) ─────────────────────────────────────
def all_runs() -> list[dict]:
    return [r for r in _read(settings.run_log_path) if r.get("kind") == "run"]


def all_feedback() -> list[dict]:
    return _read(settings.feedback_path)
