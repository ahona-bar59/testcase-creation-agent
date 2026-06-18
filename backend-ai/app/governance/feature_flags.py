"""Per-project feature flag (Phase 5 — gradual rollout & rollback).

Resolution order for a project:
1. JSON override file (`FEATURE_FLAGS_FILE`) — `{ "PROJECT": true|false }`
2. CSV allowlist (`ENABLED_PROJECTS`)
3. `DEFAULT_PROJECT_ENABLED`

Flip a project off → its runs are rejected and traffic returns to the manual
workflow in seconds, with no redeploy.
"""

from __future__ import annotations

import json
import os

from fastapi import HTTPException

from ..agents.test_case_creation_langgraph.settings import settings


def _file_overrides() -> dict[str, bool]:
    path = settings.feature_flags_file
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k): bool(v) for k, v in data.items()}
    except Exception:
        return {}


def is_enabled(project_id: str) -> bool:
    overrides = _file_overrides()
    if project_id in overrides:
        return overrides[project_id]
    allow = settings.enabled_project_set()
    if allow:
        return project_id in allow or settings.default_project_enabled
    return settings.default_project_enabled


def ensure_enabled(project_id: str) -> None:
    """Raise 403 if the agent is disabled for this project."""
    if not is_enabled(project_id):
        raise HTTPException(
            status_code=403,
            detail=f"Test Case Creation Agent is disabled for project '{project_id}'. "
            "Falling back to the manual workflow.",
        )
