"""End-to-end demo of the Test Case Creation Agent.

Runs the full graph START → END in offline-stub mode (no API keys needed),
auto-answering the two HITL gates, and prints every emitted event plus the
final review verdict and persisted counts.

    python demo.py
"""

from __future__ import annotations

import io
import json
import sys

# Windows consoles default to cp1252; force UTF-8 so symbols print cleanly.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.insert(0, "backend-ai")

from app.agents.test_case_creation_langgraph import run  # noqa: E402
from app.agents.test_case_creation_langgraph.events import CollectingSink  # noqa: E402
from app.agents.test_case_creation_langgraph.tools import seed_project_suite  # noqa: E402

PROJECT = "DEMO-PROJ"

STORY = """As a registered user, I want to reset my password via an email link
so that I can regain access if I forget it."""

ACS = """AC-1: A logged-out user can request a reset by entering a registered email.
AC-2: The reset link expires after 30 minutes.
AC-3: An unregistered email shows a generic message and sends no link.
AC-4: The new password must meet the complexity policy."""


def main() -> None:
    # Preload an existing suite so the planner can find overlap (UPDATE/SKIP).
    seed_project_suite(PROJECT, [
        {"id": "TC-EXIST-201", "title": "Request password reset with valid email",
         "description": "A logged-out user requests a password reset using a registered email.",
         "type": "Positive"},
    ])

    sink = CollectingSink()

    # HITL responder: approve the plan, then approve the generated cases.
    answered = {"plan": False}

    def responder(payload: dict):
        if not answered["plan"]:
            answered["plan"] = True
            return {"choice": "Yes, generate the test cases"}
        return {"choice": "Approve"}

    payload = {
        "userStory": STORY,
        "acceptanceCriteria": ACS,
        "projectId": PROJECT,
        "trigger_type": "manual",
        "options": {"priority": "High", "includeEdgeCases": True},
    }

    final = run(payload, responder, sink=sink)

    print("=" * 78)
    print("EVENT STREAM")
    print("=" * 78)
    for e in sink.events:
        t = e["type"]
        if t == "trace":
            print(f"  ↪ trace  {e['node']}: {e['message']} ({e['status']})")
        elif t == "hitl":
            print(f"  ⏸ hitl   {e['prompt']}")
        elif t == "genui":
            n = len(e["data"]) if isinstance(e["data"], list) else 1
            print(f"  ▣ genui  {e['component']} ({n} item/s)")
        elif t == "done":
            print(f"  ✓ done   {e.get('written')}")

    review = final["review_results"]
    print("\n" + "=" * 78)
    print("RESULT")
    print("=" * 78)
    print(f"  Verdict        : {review['verdict']}  (grade {review['grade']}, "
          f"quality {review['quality_score_pct']}%)")
    print(f"  Completeness   : {review['completeness']}%")
    print(f"  Correctness    : {review['correctness']}  (gate {review['correctness_gate']})")
    print(f"  Plan           : {final['test_plan']['to_create']} CREATE · "
          f"{final['test_plan']['to_update']} UPDATE · {final['test_plan']['to_skip']} SKIP "
          f"· {final['test_plan']['work_avoided_pct']:.0f}% work avoided")
    print(f"  Errors         : {final['errors'] or 'none'}")

    print("\n  Generated test cases:")
    for tc in final["execution_results"]["test_cases"]:
        print(f"    [{tc['decision']}] {tc['id']} ({tc['type']}) — {tc['title']}")

    print("\n  Full review report:")
    print(json.dumps(review, indent=2)[:1200])


if __name__ == "__main__":
    main()
