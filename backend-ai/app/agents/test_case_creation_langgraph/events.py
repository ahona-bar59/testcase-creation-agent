"""Event emission (Phase 3 §3.3, §3.6).

Nodes and tools emit ``trace`` / ``genui`` / ``hitl`` events; the transport
(WebSocket in production, a list collector in tests/demo) is injected via a
context variable so the emitting code stays decoupled from delivery.
"""

from __future__ import annotations

import contextvars
from typing import Any, Callable

# Sink signature: (event: dict) -> None
_SINK: contextvars.ContextVar[Callable[[dict], None] | None] = contextvars.ContextVar(
    "event_sink", default=None
)


def set_sink(sink: Callable[[dict], None] | None) -> None:
    _SINK.set(sink)


def _emit(event: dict) -> None:
    sink = _SINK.get()
    if sink is not None:
        sink(event)


def emit_trace(node: str, message: str, status: str = "running", **extra: Any) -> None:
    _emit({"type": "trace", "node": node, "message": message, "status": status, **extra})


def emit_genui(component: str, data: Any) -> None:
    _emit({"type": "genui", "component": component, "data": data})


def emit_hitl(prompt: str, options: list[str] | None = None, **extra: Any) -> None:
    _emit({"type": "hitl", "prompt": prompt, "options": options or [], **extra})


def emit_done(**extra: Any) -> None:
    _emit({"type": "done", **extra})


class CollectingSink:
    """Default sink for tests/demo — records every event in order."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def __call__(self, event: dict) -> None:
        self.events.append(event)

    def of_type(self, t: str) -> list[dict]:
        return [e for e in self.events if e.get("type") == t]
