"""Governance (Phase 5): feature flags, version pinning, observability.

Keeps humans in control and makes rollout/rollback a config change:
- `feature_flags` — per-project enable/disable (flip to manual workflow in seconds).
- `observability` — structured logging + optional LangSmith trace per run.
- version pins (`AGENT_VERSION`, `PROMPT_VERSION`) so a rollback is config, not redeploy.
"""

from ..agents.test_case_creation_langgraph.settings import settings

AGENT_VERSION = settings.agent_version
PROMPT_VERSION = settings.prompt_version

__all__ = ["AGENT_VERSION", "PROMPT_VERSION"]
