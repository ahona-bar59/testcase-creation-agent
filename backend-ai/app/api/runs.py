"""Run routes: create a run (REST) and drive it (WebSocket).

## How the bridge works

The compiled LangGraph runs **synchronously** and pauses at each HITL gate by
raising an interrupt. We drive it on a background thread (`asyncio.to_thread`)
so the asyncio event loop stays free to stream events and receive the client's
gate replies concurrently.

- **Events → client.** Nodes/tools emit `trace` / `genui` / `done` via the
  agent's event sink. The sink hands each event to the loop with
  `call_soon_threadsafe`, and a pump task forwards them over the socket. The
  sink **drops `hitl` events** — the server sends the *authoritative* gate
  prompt from the interrupt payload instead, so each gate is shown exactly once
  (the node re-runs on resume and would otherwise emit a duplicate).
- **Gate reply ← client.** When the graph pauses, the worker thread blocks on a
  `ReplyBridge`; the receive task unblocks it with the client's `hitl_response`.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langgraph.types import Command

from ..agents.test_case_creation_langgraph import events
from ..agents.test_case_creation_langgraph.agent import build_initial_state, build_workflow
from ..governance.observability import run_trace
from ..improvement import feedback
from .schemas import RunCreated, RunRequest

router = APIRouter()

# One compiled graph reused across runs; per-run isolation is by thread_id.
_GRAPH = build_workflow()

# Pending runs: run_id -> payload (consumed when the WebSocket connects).
_RUNS: dict[str, dict] = {}

_SENTINEL = object()


class ReplyBridge:
    """Hands a HITL reply from the async receive task to the blocked worker thread."""

    def __init__(self) -> None:
        self._ev = threading.Event()
        self._val: dict | None = None
        self._aborted = False

    def wait_for_reply(self) -> dict:
        self._ev.wait()
        self._ev.clear()
        if self._aborted:
            raise RuntimeError("client disconnected before answering a HITL gate")
        return self._val or {}

    def provide(self, value: dict) -> None:
        self._val = value
        self._ev.set()

    def abort(self) -> None:
        self._aborted = True
        self._ev.set()


def register_run(payload: dict) -> str:
    """Register a pending run and return its id (shared by REST + webhook)."""
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    payload["run_id"] = run_id
    _RUNS[run_id] = payload
    return run_id


@router.post("/runs", response_model=RunCreated)
def create_run(req: RunRequest) -> RunCreated:
    from ..governance.feature_flags import ensure_enabled  # local import avoids cycle

    ensure_enabled(req.projectId)
    run_id = register_run(req.to_payload())
    return RunCreated(run_id=run_id, stream_url=f"/runs/{run_id}/stream")


def _result_summary(final: dict) -> dict:
    review = final.get("review_results") or {}
    plan = final.get("test_plan") or {}
    results = final.get("execution_results") or {}
    return {
        "verdict": review.get("verdict"),
        "grade": review.get("grade"),
        "quality_score_pct": review.get("quality_score_pct"),
        "completeness": review.get("completeness"),
        "correctness": review.get("correctness"),
        "correctness_gate": review.get("correctness_gate"),
        "plan": {
            "to_create": plan.get("to_create"),
            "to_update": plan.get("to_update"),
            "to_skip": plan.get("to_skip"),
            "work_avoided_pct": plan.get("work_avoided_pct"),
        },
        "test_cases": results.get("test_cases", []),
        "review_report": review,
        "errors": final.get("errors", []),
        "is_best_effort": final.get("is_best_effort", False),
    }


@router.websocket("/runs/{run_id}/stream")
async def stream_run(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    payload = _RUNS.pop(run_id, None)
    if payload is None:
        await ws.send_json({"type": "error", "message": f"unknown or already-started run_id {run_id}"})
        await ws.close()
        return

    loop = asyncio.get_running_loop()
    out_q: asyncio.Queue = asyncio.Queue()
    bridge = ReplyBridge()

    def sink(event: dict) -> None:
        # Server synthesizes the authoritative hitl from the interrupt payload.
        if event.get("type") == "hitl":
            return
        loop.call_soon_threadsafe(out_q.put_nowait, event)

    def push(event: object) -> None:
        loop.call_soon_threadsafe(out_q.put_nowait, event)

    def worker() -> None:
        """Drive the graph synchronously on a thread, pausing at each gate."""
        events.set_sink(sink)
        config = {"configurable": {"thread_id": run_id}}
        ts = datetime.now(timezone.utc).isoformat()
        gate2_original: list[dict] | None = None
        gate2_edited = False
        try:
            with run_trace(run_id):
                state = build_initial_state(payload)
                result = _GRAPH.invoke(state, config=config)
                while "__interrupt__" in result:
                    gate = result["__interrupt__"][0].value
                    if gate.get("gate") == "test_review":
                        gate2_original = gate.get("test_cases") or []
                    push({"type": "hitl", **gate})  # authoritative — sent once per pause
                    reply = bridge.wait_for_reply()
                    if gate.get("gate") == "test_review" and reply.get("test_cases_edited"):
                        gate2_edited = True
                        feedback.record_run_signals(
                            run_id, gate2_original or [], reply["test_cases_edited"], ts
                        )
                    result = _GRAPH.invoke(Command(resume=reply), config=config)

            # Phase 6: log the outcome + auto-capture signals for the drift loop.
            result["_gate2_edited"] = gate2_edited
            feedback.log_run(run_id, payload.get("projectId", ""), result, ts)
            feedback.record_missed_acs(
                run_id, (result.get("review_results") or {}).get("missing_acs", []), ts
            )
            push({"type": "result", "data": _result_summary(result)})
        except Exception as exc:  # never leave the socket hanging
            push({"type": "error", "message": str(exc)})
        finally:
            push(_SENTINEL)

    worker_task = asyncio.create_task(asyncio.to_thread(worker))

    async def receive_loop() -> None:
        try:
            while True:
                msg = await ws.receive_json()
                if msg.get("type") == "hitl_response":
                    bridge.provide({
                        "choice": msg.get("choice", ""),
                        "test_cases_edited": msg.get("test_cases_edited"),
                    })
        except (WebSocketDisconnect, RuntimeError):
            bridge.abort()

    recv_task = asyncio.create_task(receive_loop())

    try:
        while True:
            event = await out_q.get()
            if event is _SENTINEL:
                break
            await ws.send_json(event)
    except WebSocketDisconnect:
        bridge.abort()
    finally:
        recv_task.cancel()
        await worker_task
        try:
            await ws.close()
        except RuntimeError:
            pass
