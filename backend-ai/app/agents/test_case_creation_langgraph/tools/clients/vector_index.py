"""Vector index client — semantic similarity over the existing suite (Phase 4).

Returns a list of ``{id, title, description, type, similarity}`` or ``None`` when
not configured (caller falls back to the keyword/Jaccard proxy in the tool).

Two backends are sketched behind one surface: Azure AI Search and a generic
pgvector-style HTTP endpoint. Both degrade to ``None`` if the dependency or
config is missing.
"""

from __future__ import annotations

from ...settings import settings


def available() -> bool:
    return bool(settings.vector_backend and settings.vector_url)


def search(query: str, project_id: str, top_k: int = 10) -> list[dict] | None:
    if not available():
        return None
    if settings.vector_backend == "azure_search":
        return _azure_search(query, project_id, top_k)
    return _generic_http(query, project_id, top_k)


def _azure_search(query: str, project_id: str, top_k: int) -> list[dict] | None:
    try:
        import httpx
    except Exception:
        return None
    url = f"{settings.vector_url}/indexes/test-cases/docs/search?api-version=2023-11-01"
    body = {"search": query, "filter": f"project_id eq '{project_id}'", "top": top_k}
    try:
        resp = httpx.post(
            url,
            headers={"api-key": settings.vector_api_key or "", "Content-Type": "application/json"},
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        docs = resp.json().get("value", [])
    except Exception:
        return None
    return [
        {
            "id": d.get("id"),
            "title": d.get("title", ""),
            "description": d.get("description", ""),
            "type": d.get("type", "Positive"),
            "similarity": d.get("@search.score", 0.0),
        }
        for d in docs
    ]


def _generic_http(query: str, project_id: str, top_k: int) -> list[dict] | None:
    try:
        import httpx
    except Exception:
        return None
    try:
        resp = httpx.post(
            settings.vector_url,
            headers={"Authorization": f"Bearer {settings.vector_api_key or ''}"},
            json={"query": query, "project_id": project_id, "top_k": top_k},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("results")
    except Exception:
        return None
