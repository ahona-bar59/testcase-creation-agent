"""Tests for Phase 4 (integrations), Phase 5 (governance), Phase 6 (improvement).

All offline — clients fall back gracefully, no live systems or API key.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend-ai"))
os.environ.setdefault("LLM_OFFLINE_STUB", "true")

import importlib  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.agents.test_case_creation_langgraph.settings import settings  # noqa: E402
from app.agents.test_case_creation_langgraph.tools import seed_project_suite  # noqa: E402
from app.agents.test_case_creation_langgraph.tools.clients import (  # noqa: E402
    requirement_store,
    suite_store,
    test_management,
    vector_index,
)


# ── Phase 4: clients degrade gracefully when unconfigured ─────────────────
def test_clients_unavailable_by_default():
    assert requirement_store.available() is False
    assert suite_store.available() is False
    assert vector_index.available() is False
    assert test_management.available() is False
    # And their calls return the "fall back" sentinel rather than raising.
    assert requirement_store.fetch("PROJ-1", "P") is None
    assert suite_store.search("P", ["login"]) is None
    assert vector_index.search("login", "P") is None
    assert test_management.create({"title": "x"}, "P") is None
    assert test_management.update("TC-1", {}) is False


def test_tools_still_work_via_fallback():
    from app.agents.test_case_creation_langgraph.tools import search_existing_tests

    seed_project_suite("FB1", [
        {"id": "TC-1", "title": "login valid", "description": "access account", "type": "Positive"},
    ])
    out = search_existing_tests("FB1", ["login", "account"])
    assert out["total"] >= 1


# ── Phase 4: Jira webhook mapping ─────────────────────────────────────────
def test_jira_payload_mapping():
    from app.api.webhooks import map_jira_payload

    payload = {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": "PROJ-42",
            "fields": {
                "summary": "Reset password",
                "description": "User resets password.\nAcceptance Criteria:\n- link expires in 30m",
                "project": {"key": "PROJ"},
            },
        },
    }
    mapped = map_jira_payload(payload)
    assert mapped["jiraStoryId"] == "PROJ-42"
    assert mapped["projectId"] == "PROJ"
    assert mapped["trigger_type"] == "webhook"
    assert "Reset password" in mapped["userStory"]
    assert "30m" in mapped["acceptanceCriteria"]


# ── Phase 5: feature flags ────────────────────────────────────────────────
def test_feature_flag_enforced(monkeypatch):
    from app.governance import feature_flags

    monkeypatch.setattr(settings, "default_project_enabled", False)
    monkeypatch.setattr(settings, "enabled_projects", "ALLOWED")
    assert feature_flags.is_enabled("ALLOWED") is True
    assert feature_flags.is_enabled("BLOCKED") is False

    # The REST endpoint returns 403 for a disabled project.
    from app.main import app

    client = TestClient(app)
    resp = client.post("/runs", json={"userStory": "x", "projectId": "BLOCKED"})
    assert resp.status_code == 403


def test_health_exposes_version():
    from app.main import app

    body = TestClient(app).get("/health").json()
    assert body["agent_version"] == settings.agent_version
    assert body["prompt_version"] == settings.prompt_version


# ── Phase 6: feedback store + metrics ─────────────────────────────────────
def test_feedback_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "run_log_path", str(tmp_path / "runs.jsonl"))
    monkeypatch.setattr(settings, "feedback_path", str(tmp_path / "fb.jsonl"))
    # reload module so it re-reads paths lazily (functions read settings live)
    from app.improvement import feedback, metrics

    importlib.reload(feedback)
    importlib.reload(metrics)

    feedback.log_run("r1", "P", {
        "review_results": {"verdict": "PASS", "completeness": 100.0, "correctness": 92.0,
                            "quality_score_pct": 90.0},
        "test_plan": {"work_avoided_pct": 25.0},
        "retry_count": 0,
    })
    feedback.log_run("r2", "P", {
        "review_results": {"verdict": "FAIL", "completeness": 80.0, "correctness": 70.0,
                            "quality_score_pct": 60.0},
        "test_plan": {"work_avoided_pct": 0.0},
        "retry_count": 2, "is_best_effort": True,
    })
    feedback.record_rating("r1", "up", None)
    feedback.record_run_signals("r1",
        [{"id": "TC-001", "title": "old"}],
        [{"id": "TC-001", "title": "new"}])

    s = metrics.summary()
    assert s["runs"] == 2
    assert s["pass_rate_pct"] == 50.0
    assert s["avg_completeness"] == 90.0
    assert s["ratings"]["total"] == 1

    edits = [f for f in feedback.all_feedback() if f["kind"] == "gate2_edits"]
    assert edits and edits[0]["diffs"][0]["fields"]["title"]["to"] == "new"


# ── Phase 6: regression set runs through the agent ────────────────────────
def test_golden_stories_pass():
    from app.improvement.regression import load_golden, run_story

    golden = load_golden()
    assert golden, "expected curated golden stories"
    for story in golden:
        if not story.get("input"):
            continue
        final = run_story(story)
        assert final["review_results"]["verdict"] in story.get(
            "expect_verdict", ["PASS", "ESCALATE", "FAIL"]
        )
