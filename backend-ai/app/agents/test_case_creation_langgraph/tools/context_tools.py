"""Context-retrieval tools (Planner + Executor).

These wrap the *external systems of record* — the requirement store
(Neo4j / Azure DevOps), the existing test suite (MongoDB), and the vector index.
Each tool is written so the real client can be dropped in behind the same
signature; until then they degrade gracefully to synthetic-but-structured data
so the graph runs end to end (Phase 3 §3.5 "missing vector index → graceful
degrade").
"""

from __future__ import annotations

from typing import Any

from .clients import requirement_store, suite_store, vector_index
from .shared import cache_get, cache_set, keywords_from


# ── fetch_requirement (Planner) ───────────────────────────────────────────
def fetch_requirement(jira_story_id: str | None, project_id: str) -> dict:
    """Load story + ACs from Neo4j/ADO. Skipped for `manual` trigger (the
    planner node reads from input instead). Returns a SourceRequirement dict.
    """
    cached = cache_get(f"req:{project_id}:{jira_story_id}")
    if cached:
        return cached
    # Real store first; graceful fallback keeps the contract intact when absent.
    fetched = requirement_store.fetch(jira_story_id, project_id)
    if fetched:
        cache_set(f"req:{project_id}:{jira_story_id}", fetched)
        return fetched
    req = {
        "jira_story_id": jira_story_id,
        "story_title": f"Story {jira_story_id}" if jira_story_id else "Untitled story",
        "story_text": "",
        "acceptance_criteria": [],
        "source_type": "jira" if jira_story_id else "manual",
        "project_id": project_id,
    }
    cache_set(f"req:{project_id}:{jira_story_id}", req)
    return req


# ── search_existing_tests (Planner) ───────────────────────────────────────
def search_existing_tests(project_id: str, keywords: list[str], top_k: int = 20) -> dict:
    """Keyword search of the existing suite (MongoDB text index).

    Returns ``{"matches": [...], "total": int}``. Matches carry enough metadata
    for ``compare_coverage`` to reason about overlap.
    """
    # Real Mongo search first; fall back to the in-memory seed suite.
    real = suite_store.search(project_id, keywords, top_k)
    if real is not None:
        return {"matches": real, "total": len(real)}
    suite = cache_get(f"suite:{project_id}", _seed_suite())
    kw = {k.lower() for k in keywords}
    matches: list[dict] = []
    for tc in suite:
        hay = (tc["title"] + " " + tc["description"]).lower()
        score = sum(1 for k in kw if k in hay)
        if score:
            matches.append({**tc, "match_score": score})
    matches.sort(key=lambda m: -m["match_score"])
    return {"matches": matches[:top_k], "total": len(matches)}


# ── vector_search_tests (Planner) ─────────────────────────────────────────
def vector_search_tests(query: str, project_id: str, top_k: int = 10) -> list[dict]:
    """Semantic similarity search of the existing suite.

    Falls back to keyword overlap scoring when no vector index is wired
    (graceful degrade — never raises).
    """
    real = vector_index.search(query, project_id, top_k)
    if real is not None:
        return real
    suite = cache_get(f"suite:{project_id}", _seed_suite())
    kw = set(keywords_from(query))
    scored = []
    for tc in suite:
        hay = set(keywords_from(tc["title"] + " " + tc["description"]))
        sim = len(kw & hay) / (len(kw | hay) or 1)  # Jaccard proxy for cosine
        scored.append({**tc, "similarity": round(sim, 3)})
    scored.sort(key=lambda m: -m["similarity"])
    return scored[:top_k]


# ── get_related_context (Executor) ────────────────────────────────────────
def get_related_context(project_id: str, top_k: int = 5) -> list[dict]:
    """Glossary, integration docs, and past suites that ground generation."""
    ctx = cache_get(f"context:{project_id}", [])
    return ctx[:top_k]


# ── fetch_test_case (Executor — UPDATE path) ──────────────────────────────
def fetch_test_case(test_case_id: str) -> dict | None:
    """Load a specific existing case (used on the UPDATE path)."""
    real = suite_store.get_by_id(test_case_id)
    if real is not None:
        return real
    for suite in _all_suites():
        for tc in suite:
            if tc["id"] == test_case_id:
                return tc
    return None


# ── get_test_template (Executor) ──────────────────────────────────────────
_TEMPLATES: dict[str, dict] = {
    "Positive": {"intro": "Verify expected behaviour", "step_hint": "perform the action"},
    "Negative": {"intro": "Verify graceful failure", "step_hint": "supply invalid input"},
    "Edge": {"intro": "Verify edge condition", "step_hint": "use an unusual but valid value"},
    "Boundary": {"intro": "Verify boundary", "step_hint": "use min/max boundary values"},
}


def get_test_template(test_case_type: str, project_id: str) -> dict:
    """Return the step template for a given test type."""
    return _TEMPLATES.get(test_case_type, _TEMPLATES["Positive"])


# ── seed data (dev fallback only) ─────────────────────────────────────────
def _seed_suite() -> list[dict]:
    return [
        {
            "id": "TC-EXIST-101",
            "title": "Login with valid credentials",
            "description": "User logs in successfully with a correct username and password.",
            "type": "Positive",
        },
        {
            "id": "TC-EXIST-102",
            "title": "Login with invalid password",
            "description": "Login is rejected when the password is wrong.",
            "type": "Negative",
        },
    ]


def _all_suites() -> list[list[dict]]:
    suites = [v for k, v in _iter_suites()]
    return suites or [_seed_suite()]


def _iter_suites():
    from .shared import _WORKSPACE_CACHE  # noqa: PLC0415

    for k, v in _WORKSPACE_CACHE.items():
        if k.startswith("suite:") and isinstance(v, list):
            yield k, v


def seed_project_suite(project_id: str, suite: list[dict]) -> None:
    """Test/demo helper: preload an existing suite for a project."""
    cache_set(f"suite:{project_id}", suite)
