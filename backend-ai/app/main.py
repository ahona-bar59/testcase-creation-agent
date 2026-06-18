"""FastAPI application entrypoint (Build Plan — Phase 2).

Run locally:
    cd backend-ai
    uvicorn app.main:app --reload --port 8000

Then:
    POST /runs                  -> { run_id, stream_url }
    WS   /runs/{run_id}/stream  -> drive the run, answer the two HITL gates
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agents.test_case_creation_langgraph import AGENT_ID, AUTONOMY_LEVEL
from .agents.test_case_creation_langgraph.settings import settings
from .api.feedback import router as feedback_router
from .api.runs import router as runs_router
from .api.webhooks import router as webhooks_router
from .governance.observability import configure_logging

configure_logging()

app = FastAPI(
    title="Test Case Creation Agent",
    version=settings.agent_version,
    description="LangGraph agent that drafts reviewed, coverage-aware test cases (L2 · Supervised).",
)

# CORS — the Phase 3 frontend (Vite dev server) connects from a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the frontend origin in deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router, tags=["runs"])
app.include_router(webhooks_router, tags=["webhooks"])
app.include_router(feedback_router, tags=["feedback"])


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "agent": AGENT_ID,
        "autonomy": AUTONOMY_LEVEL,
        "agent_version": settings.agent_version,
        "prompt_version": settings.prompt_version,
        "llm_provider": settings.llm_provider,
        "offline_stub": settings.llm_offline_stub,
    }


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "agent": AGENT_ID,
        "docs": "/docs",
        "create_run": "POST /runs",
        "stream": "WS /runs/{run_id}/stream",
    }
