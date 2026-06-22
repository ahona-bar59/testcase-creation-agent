"""Show, in full detail, the test cases the agent generates for a given input.

Run:  python show_testcases.py

Prints the INPUT (story + acceptance criteria) and then every generated
TestCase with its decision (CREATE/UPDATE/SKIP), type, priority, and the full
numbered steps (action + expected result). Also tells you whether the run used
the offline stub or a live LLM.
"""

from __future__ import annotations

import io
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.insert(0, "backend-ai")

from app.agents.test_case_creation_langgraph import run  # noqa: E402
from app.agents.test_case_creation_langgraph.settings import settings  # noqa: E402
from app.agents.test_case_creation_langgraph.tools import seed_project_suite  # noqa: E402

# ── THE INPUT (this is what a tester provides) ────────────────────────────
STORY = "As a registered user, I want to reset my password via an email link so that I can regain access if I forget it."
ACCEPTANCE_CRITERIA = """AC-1: A logged-out user can request a reset by entering a registered email.
AC-2: The reset link expires after 30 minutes.
AC-3: An unregistered email shows a generic message and sends no link.
AC-4: The new password must meet the complexity policy."""
PROJECT = "SHOWCASE"


def main() -> None:
    seed_project_suite(PROJECT, [])  # empty existing suite → all CREATE

    def responder(_payload):  # auto-approve both gates
        return {"choice": "Yes, generate the test cases"}

    final = run(
        {
            "userStory": STORY,
            "acceptanceCriteria": ACCEPTANCE_CRITERIA,
            "projectId": PROJECT,
            "trigger_type": "manual",
            "options": {"priority": "High", "includeEdgeCases": True},
        },
        responder,
    )

    mode = "OFFLINE STUB (templated)" if settings.llm_planner.offline_stub else f"LIVE LLM ({settings.llm_provider})"

    print("=" * 80)
    print("INPUT")
    print("=" * 80)
    print(f"User story:\n  {STORY}\n")
    print("Acceptance criteria:")
    for line in ACCEPTANCE_CRITERIA.splitlines():
        print(f"  {line}")
    print(f"\nGeneration mode: {mode}")

    cases = final["execution_results"]["test_cases"]
    print("\n" + "=" * 80)
    print(f"GENERATED TEST CASES  ({len(cases)} total)")
    print("=" * 80)
    for tc in cases:
        print(f"\n┌─ {tc['id']}  [{tc['decision']}]  type={tc['type']}  priority={tc['priority']}")
        print(f"│  Title      : {tc['title']}")
        print(f"│  Description: {tc['description']}")
        if tc.get("existing_tc_id"):
            print(f"│  Updates    : {tc['existing_tc_id']}")
        print("│  Steps:")
        for s in tc["steps"]:
            print(f"│    {s['step']}. ACTION  : {s['action']}")
            print(f"│       EXPECTED: {s['expected']}")
        print(f"└─ Why: {tc['decision_reason']}")

    r = final["review_results"]
    print("\n" + "=" * 80)
    print("QUALITY CHECK (the Reviewer's two gates)")
    print("=" * 80)
    print(f"  Completeness (all ACs covered?) : {r['completeness']}%")
    print(f"  Correctness (steps verifiable?) : {r['correctness']}  (gate {r['correctness_gate']})")
    print(f"  Verdict                         : {r['verdict']}  (grade {r['grade']})")


if __name__ == "__main__":
    main()
