# CLAUDE.md — Test Case Creation Agent

Project context for Claude Code (and teammates). Read this first.

## What this is

A **LangGraph agent** that turns a user story + acceptance criteria into
reviewed, coverage-aware test cases. Autonomy level **L2 · Supervised**:
deterministic routing + two blocking human-in-the-loop (HITL) gates; **a human
approves every write** to the test system.

- **Source of truth for design:** `test-case-creation-agent (updated).md` (the spec).
- **Roadmap / next steps:** `Build_Plan.md` (phase-wise plan incl. frontend).
- **Architecture & how-to:** `README.md`.

## Current status

- ✅ Backend agent **complete and tested**, runs END-to-END **offline** (no API key).
- ✅ `python demo.py` → verdict PASS. `python -m pytest -q` → **15 passed** (11 agent + 4 service).
- ✅ **Phase 2 done:** FastAPI + WebSocket service (`app/main.py`, `app/api/`). Drives a run
  and round-trips both HITL gates; verified live against uvicorn with `ws_demo_client.py`.
- ✅ **Phase 3 done:** React + TS + Vite frontend in `frontend/`. `npm run build` passes;
  dev-server proxies REST + WS to the backend. Renders trace timeline + GenUI; both HITL
  gates are interactive modals (`PlanReviewModal`, `TestCaseEditor`); 👍/👎 feedback on result.
- ✅ **Phase 4 done:** integration clients in `tools/clients/` (Neo4j/ADO, Mongo, vector, test-mgmt),
  wired real-first with stub fallback; Jira webhook `POST /webhooks/jira`. Activate via `.env`.
- ✅ **Phase 5 done:** governance — `app/governance/` (per-project feature flags → 403, version pins,
  observability/LangSmith). Dockerfiles + `docker-compose.yml` + `.github/workflows/ci.yml`.
- ✅ **Phase 6 done:** `app/improvement/` — feedback + run log (JSONL), `GET /metrics/summary` drift,
  golden regression set + `scripts/build_regression_set.py`.
- ✅ **Full suite: 22 passed** (agent + service + phases 4–6). Frontend build green.
- ⛔ Live LLM blocked on Azure OpenAI **API-key authorization** — runtime only; implementation complete.
- ⬜ Remaining: expand autonomy (L2→L3→L4) deliberately; swap JSONL stores for a DB in prod;
  PostgresSaver checkpointer + shared run registry for multi-worker.

## Frontend (Phase 3)

`frontend/` — React 18 + TypeScript + Vite. Run: `cd frontend ; npm install ; npm run dev`
(backend must be up on :8000; Vite proxies `/runs` + `/health`). Event/domain types in
`src/types.ts` mirror `models.py` and the WS protocol. Socket lifecycle in
`src/hooks/useRunSocket.ts`. One component per GenUI component; HITL gates are blocking modals.
Keep `src/types.ts` in sync if backend models or the event protocol change.

## How to run

```powershell
# venv (one-time create, then activate each session)
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python demo.py                       # full graph, offline, both HITL gates auto-approved
pip install pytest pytest-asyncio
python -m pytest -q                  # 11 tests across all layers
python check_llm.py                  # validates Azure creds once .env is set (live path)
```

## Project layout

```
backend-ai/app/agents/test_case_creation_langgraph/
├── agent.py        # build_workflow() graph wiring · build_initial_state() · run()
├── settings.py     # Settings + per-worker LLMSlot (input to build_llm)
├── state.py        # TestCaseCreationState TypedDict (the whole run lives here)
├── models.py       # Pydantic models (Appendix A of the spec)
├── routing.py      # the 3 deterministic edge functions (NO LLM coordinator)
├── nodes.py        # the 8 node functions
├── prompts.py      # one system prompt per worker / LLM tool
├── react.py        # create_react_agent worker builders (live path)
├── events.py       # trace / genui / hitl event emitter (sink injected by transport)
└── tools/          # context · coverage · analysis · generation · persistence(guarded) · review
backend-ai/app/
├── main.py            # FastAPI app (CORS, /health, logging, routers)
├── api/
│   ├── schemas.py     # RunRequest (mirrors §1.4) · RunCreated · HitlResponse
│   ├── runs.py        # POST /runs · WS /runs/{run_id}/stream + thread-bridge driver + run logging
│   ├── webhooks.py    # POST /webhooks/jira (Phase 4 — ADF/plain mapping)
│   └── feedback.py    # POST /runs/{id}/feedback · GET /metrics/summary (Phase 6)
├── governance/        # Phase 5: feature_flags · observability · version pins
├── improvement/       # Phase 6: feedback (JSONL) · metrics (drift) · regression + golden_stories.json
└── agents/.../tools/clients/   # Phase 4: requirement_store · suite_store · vector_index · test_management
demo.py · check_llm.py · ws_demo_client.py · scripts/build_regression_set.py
tests/{test_agent.py, test_service.py, test_phase456.py}
```

## Integrations (Phase 4) — real-first, stub-fallback

Tools call `clients.<x>.available()`; if unconfigured they fall back to the synthetic stub.
NEVER remove the fallback — it's what keeps the agent implementable/testable with no live systems
or API key. Add a new system by adding a client with `available()` + the call, then branch in the tool.

## Governance (Phase 5) & Improvement (Phase 6)

- Feature flag: `app/governance/feature_flags.py`; `POST /runs` + webhook call `ensure_enabled()` → 403.
- Every run is logged to `RUN_LOG_PATH`; Gate-#2 edits + missed ACs + 👍/👎 to `FEEDBACK_PATH` (JSONL).
  `GET /metrics/summary` aggregates drift. These paths are runtime artifacts (gitignored `data/`).

## Service (Phase 2) — how the WebSocket driver works

The graph is **synchronous** and pauses at each gate via `interrupt()`. The WS
handler (`api/runs.py`) runs it on a worker thread (`asyncio.to_thread`) so the
loop stays free to stream events and receive gate replies concurrently:
- Events flow node → sink → `call_soon_threadsafe` → async queue → socket.
- The sink **drops `hitl` events**; the server sends the authoritative gate
  prompt from the interrupt payload so each gate appears **exactly once** (the
  node re-runs on resume and would otherwise emit a duplicate). Don't "fix" this
  by forwarding the sink's hitl — it reintroduces the duplicate.
- A `ReplyBridge` (threading.Event) hands the client's `hitl_response` from the
  async receive task back to the blocked worker thread.

Run: `cd backend-ai && uvicorn app.main:app --port 8000` then `python ws_demo_client.py`.

## The graph (must match `Project_Flow_State_Diagram.html` and the spec)

```
START → input_guard → planner → plan_review(HITL#1)
        plan_review: approve → executor ; revise → planner
        executor: retry_count==0 → test_review(HITL#2) ; retry_count>0 → reviewer
        test_review → reviewer
        reviewer: PASS/ESCALATE → format_output ; FAIL & <2 retries → executor ; FAIL & ≥2 → format_output (best-effort)
        format_output → persist → END
```

## Conventions & important facts (don't break these)

- **Deterministic routing only.** Routing lives in `routing.py` as plain functions
  over state. There is intentionally **no LLM coordinator** — this is what makes it
  L2 and testable. Don't introduce model-driven routing without a deliberate
  autonomy-level change (see spec Phase 5.3).
- **Two HITL gates are the product, not overhead.** Gate #1 approves the *plan*,
  Gate #2 approves/edits the *cases*. Self-correction retries (`retry_count > 0`)
  **skip Gate #2** by design — never re-ask the human inside the approved boundary.
- **Writes are guarded.** Only `persist_node` writes, and only the human-approved
  set. `persistence_tools.py` is the only module that touches the external test system.
- **Provider is config, not code.** Each worker resolves its model from a settings
  slot via `build_llm()`. Never hard-code a provider in node/tool code. Swap
  Azure/Anthropic/Google by changing `LLM_PROVIDER` + creds in `.env`.
- **Offline stub.** When `LLM_OFFLINE_STUB=true` (or no API key is set),
  `build_llm()` returns a deterministic stub and tools fall back to heuristics, so
  the whole graph runs without network. Tools branch on `using_stub(slot)`. Keep
  this property — it powers the demo and the tests.
- **Azure gotcha:** `LLM_*_MODEL` must be the **deployment name** from Azure, not
  the model id. Empty `AZURE_OPENAI_API_KEY` silently falls back to stub mode.
- **External tools degrade gracefully.** The context/persistence tools return
  synthetic-but-structured data when the backing system is absent. When wiring real
  clients (Build_Plan Phase 4), preserve the fallback.
- **Windows console:** force UTF-8 before printing unicode (see top of `demo.py`),
  or cp1252 will crash on the ↪/▣ glyphs.

## Event protocol (server → client; see events.py)

```jsonc
{ "type": "trace", "node": "...", "message": "...", "status": "running|complete" }
{ "type": "genui", "component": "test-case-table|scenario-list|coverage-map|review-report", "data": ... }
{ "type": "hitl",  "prompt": "...", "options": [...], "gate": "plan_review|test_review" }
{ "type": "done",  "written": { "created": N, "updated": N, "skipped": N } }
```
Client answers a `hitl` pause with `{ "choice": "...", "test_cases_edited"?: [...] }`,
delivered to `run(..., responder=...)`.

## Testing

`tests/test_agent.py` mirrors the spec's Phase 3 §3.5 strategy: node unit · tool ·
routing · graph integration · HITL · chaos/edge. Run offline; no keys needed.
**Add a test for any new node/tool/route.** Keep `route_after_*` fully covered
(every verdict × retry combination).

## What to work on next

See `Build_Plan.md`. Short version:
1. Unblock Phase 1 (API key) — or use Anthropic to proceed.
2. Phase 2 — FastAPI + WebSocket service wrapping `run()`.
3. Phase 3 — React/TS frontend (can start now against the offline stub).
