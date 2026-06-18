"""Webhook ingress (Phase 4 — trigger: webhook).

Maps a Jira issue webhook payload onto the agent input contract and registers a
run. The response carries the `stream_url`; an automated consumer (or the UI)
connects the WebSocket to drive the run and answer the two HITL gates.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter

from ..governance.feature_flags import ensure_enabled
from .runs import register_run
from .schemas import RunCreated

router = APIRouter()


def map_jira_payload(payload: dict[str, Any]) -> dict:
    """Translate a Jira issue webhook into a TestCaseCreationInput payload."""
    issue = payload.get("issue", {}) or {}
    fields = issue.get("fields", {}) or {}
    summary = fields.get("summary", "") or ""
    description = _strip_html(_jira_text(fields.get("description")))
    project_key = (fields.get("project") or {}).get("key") or payload.get("projectId") or "UNKNOWN"

    # Acceptance criteria: prefer a configured custom field, else parse the body.
    ac_field = fields.get("customfield_10100")  # common AC field id; adjust per instance
    acceptance = _strip_html(_jira_text(ac_field)) if ac_field else _extract_acs(description)

    return {
        "userStory": f"{summary}\n\n{description}".strip(),
        "acceptanceCriteria": acceptance,
        "projectId": project_key,
        "jiraStoryId": issue.get("key"),
        "trigger_type": "webhook",
        "options": {},
    }


@router.post("/webhooks/jira", response_model=RunCreated)
def jira_webhook(payload: dict[str, Any]) -> RunCreated:
    mapped = map_jira_payload(payload)
    ensure_enabled(mapped["projectId"])
    run_id = register_run(mapped)
    return RunCreated(run_id=run_id, stream_url=f"/runs/{run_id}/stream")


# ── helpers ───────────────────────────────────────────────────────────────
def _jira_text(value: Any) -> str:
    """Jira Cloud descriptions can be ADF (dict) or plain text."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):  # Atlassian Document Format — flatten text nodes
        out: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("type") == "text" and "text" in node:
                    out.append(node["text"])
                for child in node.get("content", []) or []:
                    walk(child)
                if node.get("type") in ("paragraph", "listItem"):
                    out.append("\n")
            elif isinstance(node, list):
                for n in node:
                    walk(n)

        walk(value)
        return "".join(out)
    return ""


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _extract_acs(body: str) -> str:
    """Pull an 'Acceptance Criteria' section out of a story body, if present."""
    m = re.search(r"acceptance criteria[:\s]*(.+)", body, flags=re.I | re.S)
    return m.group(1).strip() if m else ""
