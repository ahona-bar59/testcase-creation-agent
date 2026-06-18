"""Requirement-analysis tool (Planner).

``analyze_requirement`` extracts the structured signal the planner needs to
build a good plan: components touched, risks, complexity, and a suggested
priority.
"""

from __future__ import annotations

from ..prompts import ANALYZE_REQUIREMENT_PROMPT
from ..settings import settings
from .shared import call_llm, keywords_from, parse_json, using_stub


def analyze_requirement(requirement: str) -> dict:
    """Return ``{components, risks, complexity, priority, summary}``."""
    slot = settings.llm_planner
    if not using_stub(slot):
        parsed = parse_json(call_llm(slot, ANALYZE_REQUIREMENT_PROMPT, requirement))
        if isinstance(parsed, dict) and parsed:
            return parsed

    kw = keywords_from(requirement, limit=6)
    text = requirement.lower()
    risks: list[str] = []
    if any(w in text for w in ("payment", "money", "transfer", "checkout")):
        risks.append("financial transaction integrity")
    if any(w in text for w in ("login", "auth", "password", "token", "session")):
        risks.append("authentication / session security")
    if any(w in text for w in ("delete", "remove", "purge")):
        risks.append("irreversible data loss")
    if not risks:
        risks.append("standard functional regression risk")

    word_count = len(requirement.split())
    complexity = "High" if word_count > 250 else "Medium" if word_count > 80 else "Low"
    priority = "High" if "security" in " ".join(risks) or "financial" in " ".join(risks) else "Medium"

    return {
        "components": kw or ["application"],
        "risks": risks,
        "complexity": complexity,
        "priority": priority,
        "summary": requirement[:200],
    }
