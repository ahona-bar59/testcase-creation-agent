"""Grow the regression set from real failures (Phase 6 §5.2).

Reads the run log and appends FAIL/ESCALATE runs to the golden set as seeds for
a maintainer to flesh out with the reproducing story.

    python scripts/build_regression_set.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "backend-ai")

from app.agents.test_case_creation_langgraph.settings import settings  # noqa: E402
from app.improvement.regression import harvest_failures  # noqa: E402


def main() -> None:
    added = harvest_failures(settings.run_log_path)
    print(f"Added {added} regression seed(s) from {settings.run_log_path}.")
    if added:
        print("Fill in each new entry's `input` with the reproducing story, then commit.")


if __name__ == "__main__":
    main()
