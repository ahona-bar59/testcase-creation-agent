"""Observability (Phase 5 §4 / Build Plan): structured logging + LangSmith trace.

`configure_logging()` is called once at app startup. `run_trace(run_id)` is a
context manager wrapping a run so every node/tool/LLM call is captured in
LangSmith when tracing is enabled; otherwise it is a no-op.
"""

from __future__ import annotations

import contextlib
import logging

from ..agents.test_case_creation_langgraph.settings import settings

logger = logging.getLogger("test_case_agent")


def configure_logging() -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s :: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


@contextlib.contextmanager
def run_trace(run_id: str):
    if settings.langchain_tracing_v2 and settings.langsmith_api_key:
        try:
            import langsmith

            with langsmith.trace(
                "test-case-creation",
                run_type="chain",
                project_name=settings.langsmith_project,
                metadata={
                    "thread_id": run_id,
                    "agent_version": settings.agent_version,
                    "prompt_version": settings.prompt_version,
                },
            ):
                yield
                return
        except Exception:  # tracing must never break a run
            logger.warning("LangSmith tracing unavailable; continuing untraced")
    yield
