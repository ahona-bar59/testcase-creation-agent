"""Requirement store client — Neo4j or Azure DevOps (Phase 4).

Loads a story + acceptance criteria for `api` / `webhook` triggers. Returns a
SourceRequirement-shaped dict, or ``None`` when not configured (caller falls
back to reading from the input payload).
"""

from __future__ import annotations

from ...settings import settings


def available() -> bool:
    return bool(settings.neo4j_uri and settings.neo4j_password) or bool(
        settings.ado_org_url and settings.ado_pat
    )


def fetch(jira_story_id: str | None, project_id: str) -> dict | None:
    if not jira_story_id or not available():
        return None
    if settings.neo4j_uri and settings.neo4j_password:
        return _fetch_neo4j(jira_story_id, project_id)
    return _fetch_ado(jira_story_id, project_id)


def _fetch_neo4j(story_id: str, project_id: str) -> dict | None:
    try:
        from neo4j import GraphDatabase  # type: ignore
    except Exception:
        return None
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            rec = session.run(
                """
                MATCH (s:Story {jira_id: $sid})-[:HAS_AC]->(ac:AcceptanceCriterion)
                WHERE s.project_id = $pid
                RETURN s.title AS title, s.text AS text,
                       collect({criterion_id: ac.id, criterion_text: ac.text}) AS acs
                """,
                sid=story_id,
                pid=project_id,
            ).single()
        if not rec:
            return None
        return {
            "jira_story_id": story_id,
            "story_title": rec["title"],
            "story_text": rec["text"],
            "acceptance_criteria": rec["acs"],
            "source_type": "jira",
            "project_id": project_id,
        }
    finally:
        driver.close()


def _fetch_ado(story_id: str, project_id: str) -> dict | None:
    """Azure DevOps work-item fetch via REST (PAT auth)."""
    try:
        import base64

        import httpx
    except Exception:
        return None
    url = f"{settings.ado_org_url}/{settings.ado_project}/_apis/wit/workitems/{story_id}?api-version=7.0"
    token = base64.b64encode(f":{settings.ado_pat}".encode()).decode()
    try:
        resp = httpx.get(url, headers={"Authorization": f"Basic {token}"}, timeout=15)
        resp.raise_for_status()
        f = resp.json().get("fields", {})
    except Exception:
        return None
    return {
        "jira_story_id": story_id,
        "story_title": f.get("System.Title", f"Story {story_id}"),
        "story_text": f.get("System.Description", ""),
        "acceptance_criteria": _split_acs(f.get("Microsoft.VSTS.Common.AcceptanceCriteria", "")),
        "source_type": "jira",
        "project_id": project_id,
    }


def _split_acs(raw: str) -> list[dict]:
    import re

    lines = [ln.strip(" -*\t") for ln in re.sub(r"<[^>]+>", "\n", raw or "").splitlines() if ln.strip()]
    return [{"criterion_id": f"AC-{i}", "criterion_text": ln} for i, ln in enumerate(lines, 1)]
