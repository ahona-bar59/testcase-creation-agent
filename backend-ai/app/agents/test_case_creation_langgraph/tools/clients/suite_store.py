"""Existing test-suite store client — MongoDB (Phase 4).

Keyword search over the existing test suite for a project. Returns a list of
test-case dicts ``{id, title, description, type}`` or ``None`` when not
configured (caller falls back to the synthetic seed suite).
"""

from __future__ import annotations

from ...settings import settings

_client = None  # cached MongoClient


def available() -> bool:
    return bool(settings.mongodb_uri)


def _collection():
    global _client
    if not available():
        return None
    try:
        from pymongo import MongoClient  # type: ignore
    except Exception:
        return None
    if _client is None:
        _client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)
    return _client[settings.mongodb_db][settings.mongodb_collection]


def search(project_id: str, keywords: list[str], top_k: int = 20) -> list[dict] | None:
    coll = _collection()
    if coll is None:
        return None
    query = {"project_id": project_id}
    if keywords:
        query["$text"] = {"$search": " ".join(keywords)}
    try:
        cursor = coll.find(query).limit(top_k)
        return [
            {
                "id": d.get("id") or str(d.get("_id")),
                "title": d.get("title", ""),
                "description": d.get("description", ""),
                "type": d.get("type", "Positive"),
            }
            for d in cursor
        ]
    except Exception:
        return None


def get_by_id(test_case_id: str) -> dict | None:
    coll = _collection()
    if coll is None:
        return None
    try:
        d = coll.find_one({"id": test_case_id})
        if not d:
            return None
        return {
            "id": d.get("id"),
            "title": d.get("title", ""),
            "description": d.get("description", ""),
            "type": d.get("type", "Positive"),
        }
    except Exception:
        return None
