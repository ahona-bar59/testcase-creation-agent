"""Shared tool helpers: the ``build_llm()`` factory + small utilities.

``build_llm(slot)`` is the single place that turns a settings slot into a
LangChain chat model. Provider and temperature are baked into the slot, so node
and tool code never names a provider directly.

For local dev / tests / the offline demo, a slot may carry ``offline_stub=True``
(set automatically when no API key is configured). In that mode ``build_llm``
returns a deterministic stub so the *entire graph* can run START → END without
any network access. Tools detect the stub via ``using_stub(slot)`` and produce
heuristic output instead of calling a model.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..settings import LLMSlot


# ── Workspace cache ───────────────────────────────────────────────────────
# A tiny in-process cache shared across tools within a run (e.g. fetched
# requirement, existing-suite snapshots). Keyed by project_id where relevant.
_WORKSPACE_CACHE: dict[str, Any] = {}


def cache_get(key: str, default: Any = None) -> Any:
    return _WORKSPACE_CACHE.get(key, default)


def cache_set(key: str, value: Any) -> None:
    _WORKSPACE_CACHE[key] = value


# ── LLM factory ───────────────────────────────────────────────────────────
def using_stub(slot: LLMSlot) -> bool:
    return slot.offline_stub


_TRUSTSTORE_DONE = False


def _ensure_truststore() -> None:
    """Make Python's TLS use the OS (Windows) trust store.

    Corporate networks often do TLS inspection with an internal root CA that
    Windows trusts but Python's bundled `certifi` does not — causing
    CERTIFICATE_VERIFY_FAILED on outbound LLM calls. `truststore` redirects
    verification to the OS store (which already trusts the corporate CA), the
    secure fix. No-op if `truststore` isn't installed.
    """
    global _TRUSTSTORE_DONE
    if _TRUSTSTORE_DONE:
        return
    _TRUSTSTORE_DONE = True
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass  # not installed / not needed — fall back to certifi


def build_llm(slot: LLMSlot):
    """Resolve a settings slot into a chat model.

    Returns a real LangChain chat model for the configured provider, or a
    deterministic offline stub when ``slot.offline_stub`` is set.
    """
    if slot.offline_stub:
        return _StubChatModel(slot)

    _ensure_truststore()  # corporate TLS: trust the OS store before any live call
    provider = slot.provider
    # Fail fast on provider errors so the graceful fallback in call_llm engages
    # quickly instead of waiting through SDK retry/backoff (e.g. 429 retryDelay).
    if provider in ("azure_openai", "openai"):
        if provider == "azure_openai":
            from langchain_openai import AzureChatOpenAI

            return AzureChatOpenAI(
                azure_deployment=slot.model,
                api_key=slot.api_key,
                azure_endpoint=slot.endpoint,
                api_version=slot.api_version,
                temperature=slot.temperature,
                max_retries=0,
            )
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=slot.model, api_key=slot.api_key, temperature=slot.temperature, max_retries=0
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=slot.model, api_key=slot.api_key, temperature=slot.temperature, max_retries=0
        )

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=slot.model,
            google_api_key=slot.api_key,
            temperature=slot.temperature,
            max_retries=0,
        )

    raise ValueError(f"Unknown LLM provider: {provider!r}")


class _StubChatModel:
    """Minimal offline chat model. Echoes a marker so any accidental real use
    is obvious; tools should branch on ``using_stub`` and not rely on this."""

    def __init__(self, slot: LLMSlot):
        self.slot = slot

    def invoke(self, messages, **_: Any):
        from langchain_core.messages import AIMessage

        return AIMessage(content="[offline-stub] no live model configured")


def call_llm(slot: LLMSlot, system: str, user: str) -> str:
    """Invoke a real model and return its text content.

    On ANY provider error (quota/429, auth, network, TLS), this returns ``""``
    instead of raising, so the calling tool falls back to its offline heuristic
    and the run still completes. A one-line notice is emitted to the event
    stream + log so the degradation is never silent. Not valid for stubs —
    callers must branch on ``using_stub(slot)`` first.
    """
    if using_stub(slot):
        raise RuntimeError("call_llm used with an offline stub slot")
    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        llm = build_llm(slot)
        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return resp.content if hasattr(resp, "content") else str(resp)
    except Exception as exc:  # graceful degrade — never crash the run
        _notify_llm_fallback(slot, exc)
        return ""


def _notify_llm_fallback(slot: LLMSlot, exc: Exception) -> None:
    reason = _short_reason(str(exc))
    try:
        from ..events import emit_trace

        emit_trace(
            "llm",
            f"{slot.provider} call failed ({reason}); using offline fallback for this step",
            status="complete",
        )
    except Exception:
        pass
    try:
        import logging

        logging.getLogger("test_case_agent").warning(
            "LLM provider '%s' model '%s' failed (%s); offline fallback engaged",
            slot.provider, slot.model, reason,
        )
    except Exception:
        pass


def _short_reason(msg: str) -> str:
    low = msg.lower()
    if "resource_exhausted" in low or "429" in low or "quota" in low:
        return "quota/rate limit"
    if "certificate" in low or "ssl" in low:
        return "TLS/certificate"
    if "permission" in low or "api key" in low or "401" in low or "403" in low:
        return "auth/API key"
    return msg[:80]


# ── JSON helpers ──────────────────────────────────────────────────────────
_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


def parse_json(text: str, default: Any = None) -> Any:
    """Best-effort JSON extraction from a model response."""
    try:
        return json.loads(text)
    except Exception:
        pass
    m = _JSON_BLOCK.search(text or "")
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return default


def keywords_from(text: str, limit: int = 12) -> list[str]:
    """Cheap keyword extraction used by search + stub heuristics."""
    stop = {
        "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
        "as", "is", "are", "be", "should", "must", "can", "will", "that", "this",
        "user", "story", "able", "want", "so", "when", "then", "given", "i",
    }
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", (text or "").lower())
    seen: dict[str, int] = {}
    for w in words:
        if w in stop:
            continue
        seen[w] = seen.get(w, 0) + 1
    ranked = sorted(seen, key=lambda w: (-seen[w], w))
    return ranked[:limit]
