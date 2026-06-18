"""Regression set (Phase 6 §5.2).

A small library of golden stories the agent must keep handling well, plus a
builder that grows the set from real stories that previously failed (harvested
from the run log). `run_story()` drives one story to completion offline.
"""

from __future__ import annotations

import json
import os

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden_stories.json")


def load_golden() -> list[dict]:
    if not os.path.exists(GOLDEN_PATH):
        return []
    with open(GOLDEN_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def run_story(story: dict) -> dict:
    """Drive one golden story through the agent (offline). Returns final state."""
    from ..agents.test_case_creation_langgraph import run

    answered = {"n": 0}

    def responder(_payload: dict) -> dict:
        answered["n"] += 1
        return {"choice": "Yes, generate the test cases" if answered["n"] == 1 else "Approve"}

    return run(story["input"], responder)


def harvest_failures(run_log_path: str, out_path: str = GOLDEN_PATH) -> int:
    """Append run-log FAIL/ESCALATE runs to the golden set as regression seeds.

    Returns the number of new entries added. (Inputs are not stored in the run
    log for privacy, so this records the run_id + verdict as a stub to be fleshed
    out with the real story by a maintainer — the mechanism, per the spec.)
    """
    if not os.path.exists(run_log_path):
        return 0
    existing = load_golden()
    known = {g.get("id") for g in existing}
    added = 0
    with open(run_log_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("kind") == "run" and rec.get("verdict") in ("FAIL", "ESCALATE"):
                rid = rec.get("run_id")
                if rid and rid not in known:
                    existing.append({
                        "id": rid,
                        "source": "harvested",
                        "verdict_at_capture": rec.get("verdict"),
                        "input": None,  # maintainer fills the reproducing story
                    })
                    known.add(rid)
                    added += 1
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2)
    return added
