"""Manual end-to-end client for the Phase 2 service.

Starts nothing itself — run the server first in another terminal:

    cd backend-ai
    uvicorn app.main:app --port 8000

Then in this folder:

    python ws_demo_client.py

It POSTs a run, opens the WebSocket, prints every streamed event, and
auto-answers both HITL gates (approve the plan, then approve the cases).
"""

from __future__ import annotations

import asyncio
import io
import json
import sys

import httpx
import websockets

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"

PAYLOAD = {
    "userStory": "As a registered user, I want to reset my password via an email "
                 "link so that I can regain access if I forget it.",
    "acceptanceCriteria": "AC-1: A logged-out user can request a reset by email.\n"
                          "AC-2: The reset link expires after 30 minutes.\n"
                          "AC-3: An unregistered email shows a generic message.",
    "projectId": "WS-DEMO",
    "trigger_type": "manual",
    "options": {"priority": "High", "includeEdgeCases": True},
}


async def main() -> None:
    async with httpx.AsyncClient() as http:
        r = await http.post(f"{BASE}/runs", json=PAYLOAD)
        r.raise_for_status()
        run = r.json()
    run_id = run["run_id"]
    print(f"created run {run_id}\n")

    async with websockets.connect(f"{WS_BASE}{run['stream_url']}") as ws:
        async for raw in ws:
            ev = json.loads(raw)
            t = ev["type"]
            if t == "trace":
                print(f"  trace  {ev['node']}: {ev['message']} ({ev['status']})")
            elif t == "genui":
                n = len(ev["data"]) if isinstance(ev["data"], list) else 1
                print(f"  genui  {ev['component']} ({n})")
            elif t == "hitl":
                print(f"  HITL   [{ev['gate']}] {ev['prompt']}")
                choice = ("Yes, generate the test cases"
                          if ev["gate"] == "plan_review" else "Approve")
                await ws.send(json.dumps({"type": "hitl_response", "choice": choice}))
                print(f"         -> replied: {choice}")
            elif t == "done":
                print(f"  done   {ev.get('written')}")
            elif t == "result":
                d = ev["data"]
                print(f"\nRESULT  verdict={d['verdict']} grade={d['grade']} "
                      f"completeness={d['completeness']}% correctness={d['correctness']}")
                print(f"        plan: {d['plan']}")
                for tc in d["test_cases"]:
                    print(f"        [{tc['decision']}] {tc['id']} {tc['title']}")
                break
            elif t == "error":
                print(f"  ERROR  {ev['message']}")
                break


if __name__ == "__main__":
    asyncio.run(main())
