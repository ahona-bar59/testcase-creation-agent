"""Phase 2 service tests — drive a full run over the WebSocket via TestClient.

Offline-stub mode: no API keys, no network. Verifies the create→stream→gate
→gate→result lifecycle, that each gate is shown exactly once, and that a
Gate-#2 edit is reflected in the final persisted set.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend-ai"))
os.environ.setdefault("LLM_OFFLINE_STUB", "true")

from fastapi.testclient import TestClient  # noqa: E402

from app.agents.test_case_creation_langgraph.tools import seed_project_suite  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

STORY = "As a user I want to log in with email and password so I can access my account."
ACS = "AC-1: Valid credentials grant access.\nAC-2: Invalid password is rejected."


def _create(project: str) -> str:
    resp = client.post("/runs", json={
        "userStory": STORY, "acceptanceCriteria": ACS,
        "projectId": project, "trigger_type": "manual",
        "options": {"priority": "High"},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["stream_url"].endswith("/stream")
    return body["run_id"]


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_full_run_over_websocket():
    seed_project_suite("WS1", [])
    run_id = _create("WS1")

    events: list[dict] = []
    hitl_count = 0
    result = None

    with client.websocket_connect(f"/runs/{run_id}/stream") as ws:
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] == "hitl":
                hitl_count += 1
                # Gate #1 → generate; Gate #2 → approve.
                choice = "Yes, generate the test cases" if ev["gate"] == "plan_review" else "Approve"
                ws.send_json({"type": "hitl_response", "choice": choice})
            elif ev["type"] == "result":
                result = ev["data"]
            elif ev["type"] in ("done",):
                pass
            elif ev["type"] == "error":
                raise AssertionError(f"service error: {ev['message']}")
            if ev["type"] == "result":
                break

    # Each gate shown exactly once (no duplicate from node re-run on resume).
    assert hitl_count == 2
    gates = [e["gate"] for e in events if e["type"] == "hitl"]
    assert gates == ["plan_review", "test_review"]

    assert result is not None
    assert result["verdict"] == "PASS"
    assert result["completeness"] == 100.0
    assert result["test_cases"], "expected generated test cases"
    # trace + genui events streamed during the run
    assert any(e["type"] == "trace" for e in events)
    assert any(e["type"] == "genui" and e["component"] == "test-case-table" for e in events)


def test_gate2_edit_is_reflected_in_result():
    seed_project_suite("WS2", [])
    run_id = _create("WS2")

    result = None
    with client.websocket_connect(f"/runs/{run_id}/stream") as ws:
        while True:
            ev = ws.receive_json()
            if ev["type"] == "hitl":
                if ev["gate"] == "plan_review":
                    ws.send_json({"type": "hitl_response", "choice": "Yes, generate the test cases"})
                else:  # test_review — edit the first case's title, then approve
                    cases = ev["test_cases"]
                    cases[0]["title"] = "EDITED BY REVIEWER"
                    ws.send_json({
                        "type": "hitl_response", "choice": "Approve",
                        "test_cases_edited": cases,
                    })
            elif ev["type"] == "result":
                result = ev["data"]
                break
            elif ev["type"] == "error":
                raise AssertionError(ev["message"])

    titles = [tc["title"] for tc in result["test_cases"]]
    assert "EDITED BY REVIEWER" in titles


def test_unknown_run_id_errors():
    with client.websocket_connect("/runs/run-does-not-exist/stream") as ws:
        ev = ws.receive_json()
        assert ev["type"] == "error"
