"""Test-management system client — GUARDED writes (Phase 4).

Creates/updates test cases in the external system (ADO Test Plans, Zephyr, or a
generic REST target). Returns the external id on create. Returns ``None`` from
``create``/``update`` availability check so the caller falls back to the
in-memory suite (dev) — real writes happen only when configured AND only from
the `persist` node after human approval.
"""

from __future__ import annotations

from ...settings import settings


def available() -> bool:
    return bool(settings.test_mgmt_base_url and settings.test_mgmt_token)


def create(test_case: dict, project_id: str) -> str | None:
    if not available():
        return None
    try:
        import httpx
    except Exception:
        return None
    payload = _to_external(test_case, project_id)
    try:
        resp = httpx.post(
            f"{settings.test_mgmt_base_url}/testcases",
            headers=_headers(),
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        body = resp.json()
        return body.get("id") or body.get("key")
    except Exception as exc:  # surfaced by caller into errors[]
        raise RuntimeError(f"test-management create failed: {exc}") from exc


def update(test_case_id: str | None, updates: dict) -> bool:
    if not available() or not test_case_id:
        return False
    try:
        import httpx
    except Exception:
        return False
    try:
        resp = httpx.put(
            f"{settings.test_mgmt_base_url}/testcases/{test_case_id}",
            headers=_headers(),
            json=_to_external(updates, updates.get("project_id", "")),
            timeout=20,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        raise RuntimeError(f"test-management update failed: {exc}") from exc


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.test_mgmt_token}",
        "Content-Type": "application/json",
    }


def _to_external(tc: dict, project_id: str) -> dict:
    """Map the agent TestCase shape onto a generic external payload."""
    return {
        "project_id": project_id,
        "title": tc.get("title"),
        "description": tc.get("description"),
        "priority": tc.get("priority"),
        "type": tc.get("type"),
        "steps": [
            {"action": s.get("action"), "expected": s.get("expected")}
            for s in tc.get("steps", [])
        ],
    }
